"""Source-to-target mapping: completeness, drift, proposals, exports and lineage.

Sprint 9 Step 3. A mapping document maps the columns of a source model to the
columns of a target model. Three kinds of record are kept apart, and this
module never lets one stand in for another:

* **observed fact**: the two models, read live every time;
* **inference**: a proposal, with its name-similarity and type-compatibility
  scores and a confidence (``propose``), which counts as nothing;
* **human decision**: an entry a person accepted, edited, wrote or declared
  unmapped. Only entries count.

Columns are referenced by name with their ``stable_id`` beside it, never by a
database key, because saving a model deletes the row of a column it no longer
has and a key would take the mapping with it. So everything here is resolved
against the live models on each read: an entry whose column is gone is
flagged as drift and kept, never dropped.

Completeness over the target model's M columns (owner, H3, 2026-09-30):

* **mapped (N):** an entry of kind ``mapped`` whose target and every source
  resolve;
* **explicitly unmapped (K):** an entry of kind ``constant``, ``derived`` or
  ``not_yet_mapped``;
* **pending (P):** no entry, only pending proposals;
* **silent (S):** no entry, no proposal and no explicit unmapped marker, an
  error the document reports, never an empty row;
* **in drift (D):** an entry of kind ``mapped`` that no longer resolves.

The document is complete when P = 0 and S = 0, and D = 0: a drifted entry is
not a mapping of anything that exists.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel

ENTRY_KINDS = ("mapped", "constant", "derived", "not_yet_mapped")
UNMAPPED_KINDS = ("constant", "derived", "not_yet_mapped")
# OpenLineage's column-lineage subtypes, the only specified typing: the first
# three are DIRECT, the rest INDIRECT.
TRANSFORMATION_TYPES = ("IDENTITY", "TRANSFORMATION", "AGGREGATION", "JOIN", "GROUP_BY", "FILTER", "SORT",
                        "WINDOW", "CONDITIONAL")
DIRECT_TYPES = ("IDENTITY", "TRANSFORMATION", "AGGREGATION")
STEP_KINDS = ("manual", "automated")
PROPOSAL_STATUSES = ("pending", "accepted", "edited", "rejected", "superseded")
DECISIONS = ("accepted", "edited", "rejected", "authored", "declared_unmapped", "changed", "removed",
             "document_approved")

# The person-supplied fields of an entry, in R2's STTM order after the
# identifying ones. Each is free text unless typed below.
ENTRY_FIELDS = ("transformation_type", "rule_description", "logic", "join_filter", "lookup",
                "default_null_handling", "scd_type", "step_kind", "control_rule",
                "reconciliation_control_total", "reconciliation_compared_with", "reconciliation_differences",
                "masking")

PROPOSER_METHOD = "name-type"
PROPOSER_VERSION = "1"
# Weights and floor of the proposer, stated with every proposal it makes.
NAME_WEIGHT, TYPE_WEIGHT = 0.7, 0.3
PROPOSAL_FLOOR = 0.6
PROPOSALS_PER_COLUMN = 3


@dataclass(frozen=True)
class ColumnRef:
    entity: str
    column: str
    stable_id: int | None = None


@dataclass
class Entry:
    """An accepted human decision about one target column."""

    mapping_key: str
    kind: str
    target: ColumnRef
    sources: list[ColumnRef] = field(default_factory=list)
    fields: dict[str, object] = field(default_factory=dict)
    revision: int = 1
    entry_id: str | None = None
    provenance_by: str | None = None
    provenance_at: str | None = None


@dataclass
class Proposal:
    """A candidate mapping: inference, never a mapping until a person decides."""

    target: ColumnRef
    sources: list[ColumnRef]
    name_similarity: float
    type_compatibility: float
    confidence: float
    method: str = PROPOSER_METHOD
    method_version: str = PROPOSER_VERSION
    status: str = "pending"
    proposal_id: str | None = None


class MappingError(ValueError):
    """A request the mapping rules refuse, with the reason."""


# ---------------------------------------------------------------------------
# Reading the live models
# ---------------------------------------------------------------------------
def _columns(model: SynthesizedModel | None) -> dict[tuple[str, str], tuple[EntitySchema, ColumnSchema]]:
    if model is None:
        return {}
    return {(e.entity_name, c.name): (e, c) for e in model.entities for c in e.columns}


def _by_stable_id(model: SynthesizedModel | None) -> dict[tuple[str, int], str]:
    if model is None:
        return {}
    return {(e.entity_name, c.stable_id): c.name for e in model.entities for c in e.columns
            if c.stable_id is not None}


def _key(entity: EntitySchema, column: ColumnSchema, model: SynthesizedModel) -> str:
    """PK, FK, both, or empty, as the model states it."""
    parts = []
    if column.name in entity.primary_key:
        parts.append("PK")
    if any(r.from_ref == entity.entity_name and column.name in r.from_columns for r in model.relationships):
        parts.append("FK")
    return "+".join(parts)


def snapshot(model: SynthesizedModel | None, ref: ColumnRef) -> dict[str, object]:
    """A column as the model holds it now: what a decision's evidence records."""
    found = _columns(model).get((ref.entity, ref.column))
    if found is None or model is None:
        return {"entity": ref.entity, "column": ref.column, "stable_id": ref.stable_id, "exists": False}
    entity, column = found
    return {"entity": ref.entity, "column": ref.column, "stable_id": column.stable_id, "exists": True,
            "type": column.data_type, "nullable": column.is_nullable, "key": _key(entity, column, model)}


def ref_for(model: SynthesizedModel, entity: str, column: str) -> ColumnRef:
    """A reference to a column the model has, with its stable_id; refused otherwise."""
    found = _columns(model).get((entity, column))
    if found is None:
        raise MappingError(f"{entity}.{column} is not a column of the model")
    return ColumnRef(entity, column, found[1].stable_id)


# ---------------------------------------------------------------------------
# Drift and completeness
# ---------------------------------------------------------------------------
def drift(entry: Entry, source: SynthesizedModel | None, target: SynthesizedModel | None,
          source_deleted: bool = False) -> list[str]:
    """Why an entry no longer resolves, one flag per reason; empty if it does."""
    flags: list[str] = []
    targets, target_ids = _columns(target), _by_stable_id(target)
    if (entry.target.entity, entry.target.column) not in targets:
        flags.append(f"target column missing: {entry.target.entity}.{entry.target.column}"
                     + _renamed(entry.target, target_ids))
    if entry.kind != "mapped":
        return flags
    if source_deleted:
        flags.append("source model deleted")
        return flags
    sources, source_ids = _columns(source), _by_stable_id(source)
    for ref in entry.sources:
        if (ref.entity, ref.column) not in sources:
            flags.append(f"source column missing: {ref.entity}.{ref.column}" + _renamed(ref, source_ids))
    return flags


def _renamed(ref: ColumnRef, ids: Mapping[tuple[str, int], str]) -> str:
    if ref.stable_id is None:
        return ""
    now = ids.get((ref.entity, ref.stable_id))
    return f" (renamed to {now}?)" if now is not None and now != ref.column else ""


@dataclass
class Row:
    """One target column of the document, or an entry whose target is gone."""

    target: dict[str, object]
    status: str  # mapped, constant, derived, not_yet_mapped, drift, pending, silent
    entry: Entry | None
    sources: list[dict[str, object]]
    proposals: list[Proposal]
    drift: list[str]


@dataclass
class Report:
    rows: list[Row]
    total: int  # M: the target model's columns
    mapped: int  # N
    unmapped: int  # K
    pending: int  # P
    silent: int  # S
    in_drift: int  # D, entries whose target still exists; orphaned entries are listed too
    orphaned: int  # entries whose target column no longer exists
    accepted: int  # entries: human decisions
    pending_proposals: int

    @property
    def complete(self) -> bool:
        return self.pending == 0 and self.silent == 0 and self.in_drift == 0 and self.orphaned == 0

    def summary(self) -> str:
        return (f"{self.mapped} of {self.total} target columns mapped, {self.unmapped} explicitly unmapped, "
                f"{self.silent} silent; {self.pending} pending review ({self.pending_proposals} proposals), "
                f"{self.in_drift + self.orphaned} in drift; {self.accepted} accepted entries")


def report(entries: Sequence[Entry], proposals: Sequence[Proposal], source: SynthesizedModel | None,
           target: SynthesizedModel, source_deleted: bool = False) -> Report:
    """Every target column accounted for: an entry, a pending proposal, or silent."""
    by_target = {(e.target.entity, e.target.column): e for e in entries}
    pending = [p for p in proposals if p.status == "pending"]
    proposals_for: dict[tuple[str, str], list[Proposal]] = {}
    for p in pending:
        proposals_for.setdefault((p.target.entity, p.target.column), []).append(p)
    rows: list[Row] = []
    counts = {"mapped": 0, "unmapped": 0, "pending": 0, "silent": 0, "drift": 0}
    for entity in target.entities:
        for column in entity.columns:
            key = (entity.entity_name, column.name)
            ref = ColumnRef(entity.entity_name, column.name, column.stable_id)
            entry = by_target.pop(key, None)
            offered = sorted(proposals_for.get(key, []), key=lambda p: -p.confidence)
            if entry is not None:
                flags = drift(entry, source, target, source_deleted)
                status = "drift" if flags else entry.kind
                counts["drift" if flags else ("mapped" if entry.kind == "mapped" else "unmapped")] += 1
                sources = [snapshot(source, s) for s in entry.sources]
                rows.append(Row(snapshot(target, ref), status, entry, sources, offered, flags))
            elif offered:
                counts["pending"] += 1
                rows.append(Row(snapshot(target, ref), "pending", None, [], offered, []))
            else:
                counts["silent"] += 1
                rows.append(Row(snapshot(target, ref), "silent", None, [], [], []))
    # Entries whose target column is gone: flagged, never dropped.
    for entry in by_target.values():
        rows.append(Row(snapshot(target, entry.target), "drift", entry,
                        [snapshot(source, s) for s in entry.sources], [],
                        drift(entry, source, target, source_deleted)))
    total = sum(len(e.columns) for e in target.entities)
    return Report(rows=rows, total=total, mapped=counts["mapped"], unmapped=counts["unmapped"],
                  pending=counts["pending"], silent=counts["silent"], in_drift=counts["drift"],
                  orphaned=len(by_target), accepted=len(entries), pending_proposals=len(pending))


# ---------------------------------------------------------------------------
# Validation of what a person submits
# ---------------------------------------------------------------------------
def validate_entry(kind: str, sources: Sequence[ColumnRef], fields: Mapping[str, object]) -> dict[str, object]:
    """The entry's fields, checked; refused with the reason otherwise."""
    if kind not in ENTRY_KINDS:
        raise MappingError(f"kind must be one of {', '.join(ENTRY_KINDS)}")
    if kind == "mapped" and not sources:
        raise MappingError("a mapped entry names at least one source column")
    if kind != "mapped" and sources:
        raise MappingError(f"a {kind} entry has no source column; that is what makes it explicitly unmapped")
    unknown = set(fields) - set(ENTRY_FIELDS)
    if unknown:
        raise MappingError(f"unknown fields: {', '.join(sorted(unknown))}")
    clean = {k: v for k, v in fields.items() if v not in (None, "")}
    if "transformation_type" in clean and clean["transformation_type"] not in TRANSFORMATION_TYPES:
        raise MappingError(f"transformation_type must be one of {', '.join(TRANSFORMATION_TYPES)}")
    if "step_kind" in clean and clean["step_kind"] not in STEP_KINDS:
        raise MappingError("step_kind must be manual or automated")
    if "scd_type" in clean:
        value = clean["scd_type"]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 6:
            raise MappingError("scd_type must be a whole number from 0 to 6")
    if "masking" in clean and not isinstance(clean["masking"], bool):
        raise MappingError("masking must be true or false")
    for name, value in clean.items():
        if name not in ("scd_type", "masking") and not isinstance(value, str):
            raise MappingError(f"{name} must be text")
    if kind == "mapped" and len(sources) > 1 and not clean.get("rule_description") and not clean.get("logic"):
        raise MappingError("a many-to-one entry states its transformation (rule_description or logic)")
    return clean


def digest(entry: Entry) -> str:
    """SHA-256 of what an entry says, so a decision records the content it saw."""
    body = {"kind": entry.kind, "target": asdict(entry.target), "sources": [asdict(s) for s in entry.sources],
            "fields": entry.fields}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Proposals: name similarity and type compatibility
# ---------------------------------------------------------------------------
_FAMILIES = (
    ("boolean", re.compile(r"\bBOOL|^BIT\b")),
    ("temporal", re.compile(r"DATE|TIME|INTERVAL")),
    ("numeric", re.compile(r"INT|NUMERIC|NUMBER|DECIMAL|FLOAT|DOUBLE|REAL|MONEY|SERIAL")),
    ("binary", re.compile(r"BLOB|BINARY|BYTEA|RAW\b|IMAGE")),
    ("text", re.compile(r"CHAR|TEXT|CLOB|STRING|UUID|UNIQUEIDENTIFIER|XML|JSON")),
)


def type_family(data_type: str) -> str:
    upper = data_type.upper()
    for name, pattern in _FAMILIES:
        if pattern.search(upper):
            return name
    return "other"


def type_compatibility(source_type: str, target_type: str) -> float:
    """1 for the same family; 0.5 where the source converts to the target
    without loss of meaning (a number or a date into text); 0 otherwise."""
    source, target = type_family(source_type), type_family(target_type)
    if source == target and source != "other":
        return 1.0
    if target == "text" and source in ("numeric", "temporal", "boolean"):
        return 0.5
    return 0.0


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def name_similarity(source: ColumnRef, target: ColumnRef) -> float:
    """Similarity of the column names, case and separators ignored; a match of
    the entity names as well lifts it, since EMPLOYEES.EMAIL to dim_employee.email
    is stronger than to dim_store.email."""
    column = SequenceMatcher(None, _normal(source.column), _normal(target.column)).ratio()
    entity = SequenceMatcher(None, _normal(source.entity), _normal(target.entity)).ratio()
    return round(min(1.0, column * 0.85 + entity * 0.15), 4)


def propose(source: SynthesizedModel, target: SynthesizedModel, entries: Iterable[Entry],
            existing: Iterable[Proposal] = ()) -> list[Proposal]:
    """Candidates for every target column that has no entry and no pending
    proposal yet, best first, each with both scores and a confidence."""
    decided = {(e.target.entity, e.target.column) for e in entries}
    offered = {(p.target.entity, p.target.column) for p in existing if p.status == "pending"}
    out: list[Proposal] = []
    for t_entity in target.entities:
        for t_column in t_entity.columns:
            if (t_entity.entity_name, t_column.name) in decided | offered:
                continue
            t_ref = ColumnRef(t_entity.entity_name, t_column.name, t_column.stable_id)
            scored = []
            for s_entity in source.entities:
                for s_column in s_entity.columns:
                    s_ref = ColumnRef(s_entity.entity_name, s_column.name, s_column.stable_id)
                    names = name_similarity(s_ref, t_ref)
                    types = type_compatibility(s_column.data_type, t_column.data_type)
                    confidence = round(NAME_WEIGHT * names + TYPE_WEIGHT * types, 4)
                    if confidence >= PROPOSAL_FLOOR:
                        scored.append(Proposal(t_ref, [s_ref], names, types, confidence))
            scored.sort(key=lambda p: (-p.confidence, p.sources[0].entity, p.sources[0].column))
            out.extend(scored[:PROPOSALS_PER_COLUMN])
    return out


# ---------------------------------------------------------------------------
# Exports: CSV, Markdown, HTML, JSON
# ---------------------------------------------------------------------------
# R2's STTM columns, in order. Approver and approval date are the document's,
# unused until document approval exists (owner, H3, 2026-09-30).
EXPORT_COLUMNS = (
    "Mapping ID", "Version", "Status", "Approver", "Approval date", "Last decision",
    "Target system", "Target table", "Target column", "Target type", "Target nullable", "Target key",
    "Source system", "Source schema", "Source table", "Source column", "Source type",
    "Transformation type", "Rule", "Logic", "Join and filter", "Lookup", "Default and null handling",
    "SCD type", "Manual or automated", "Control or validation rule",
    "Reconciliation control total", "Reconciliation compared with", "Reconciliation differences",
    "Masking", "Classification", "CDE", "Drift", "Pending proposals",
)


@dataclass
class DocumentInfo:
    title: str
    source_title: str
    target_title: str
    source_system: str | None = None
    target_system: str | None = None
    version: int = 1
    status: str = "draft"
    approved_by: str | None = None
    approved_at: str | None = None


def _status_text(row: Row) -> str:
    return {"mapped": "mapped", "constant": "explicitly unmapped: constant",
            "derived": "explicitly unmapped: derived", "not_yet_mapped": "explicitly unmapped: not yet mapped",
            "drift": "in drift", "pending": "pending review: not mapped",
            "silent": "SILENT: no entry (error)"}[row.status]


def _yes_no(value: object) -> str:
    return "" if value is None else ("yes" if value else "no")


def export_rows(doc: DocumentInfo, rep: Report, source: SynthesizedModel | None,
                last_decisions: Mapping[str, str] | None = None,
                classification_names: Mapping[str, str] | None = None) -> list[dict[str, str]]:
    """One row per target column (and per orphaned entry), R2's columns in order."""
    last_decisions = last_decisions or {}
    classification_names = classification_names or {}
    source_columns = _columns(source)
    out = []
    for row in rep.rows:
        entry, fields = row.entry, (row.entry.fields if row.entry else {})
        found = [source_columns.get((s["entity"], s["column"])) for s in row.sources]  # type: ignore[arg-type]
        kind = str(fields.get("transformation_type") or "")
        out.append({
            "Mapping ID": entry.mapping_key if entry else "",
            "Version": str(entry.revision) if entry else "",
            "Status": _status_text(row),
            "Approver": doc.approved_by or "",
            "Approval date": doc.approved_at or "",
            "Last decision": last_decisions.get(entry.mapping_key, "") if entry else "",
            "Target system": doc.target_system or "",
            "Target table": str(row.target["entity"]),
            "Target column": str(row.target["column"]),
            "Target type": str(row.target.get("type", "")),
            "Target nullable": _yes_no(row.target.get("nullable")),
            "Target key": str(row.target.get("key", "")),
            "Source system": doc.source_system or "",
            "Source schema": "",
            "Source table": "; ".join(str(s["entity"]) for s in row.sources),
            "Source column": "; ".join(str(s["column"]) for s in row.sources),
            "Source type": "; ".join(str(s.get("type", "missing")) for s in row.sources),
            "Transformation type": (f"{'DIRECT' if kind in DIRECT_TYPES else 'INDIRECT'} {kind}" if kind else ""),
            "Rule": str(fields.get("rule_description") or ""),
            "Logic": str(fields.get("logic") or ""),
            "Join and filter": str(fields.get("join_filter") or ""),
            "Lookup": str(fields.get("lookup") or ""),
            "Default and null handling": str(fields.get("default_null_handling") or ""),
            "SCD type": "" if fields.get("scd_type") is None else str(fields["scd_type"]),
            "Manual or automated": str(fields.get("step_kind") or ""),
            "Control or validation rule": str(fields.get("control_rule") or ""),
            "Reconciliation control total": str(fields.get("reconciliation_control_total") or ""),
            "Reconciliation compared with": str(fields.get("reconciliation_compared_with") or ""),
            "Reconciliation differences": str(fields.get("reconciliation_differences") or ""),
            "Masking": _yes_no(fields.get("masking")),
            # Carried from the dictionary: the source columns' own fields.
            "Classification": "; ".join(sorted({classification_names.get(str(c.classification_level_id), "")
                                                for _, c in filter(None, found)
                                                if c.classification_level_id} - {""})),
            "CDE": "; ".join(sorted({_yes_no(c.critical_data_element) for _, c in filter(None, found)
                                     if c.critical_data_element is not None})),
            "Drift": "; ".join(row.drift),
            "Pending proposals": "; ".join(
                f"{', '.join(f'{s.entity}.{s.column}' for s in p.sources)} (name {p.name_similarity:.2f}, "
                f"type {p.type_compatibility:.2f}, confidence {p.confidence:.2f})" for p in row.proposals),
        })
    return out


def _heading(doc: DocumentInfo, rep: Report) -> list[str]:
    return [f"Mapping: {doc.title}", f"From {doc.source_title} to {doc.target_title}, version {doc.version}",
            rep.summary(), "Complete." if rep.complete else "Not complete: pending, silent and drifted "
            "columns must be resolved by a person."]


def to_csv(doc: DocumentInfo, rep: Report, rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    # The heading as comment lines, written raw so each starts with '#'.
    for line in _heading(doc, rep):
        buffer.write("# " + " ".join(line.split()) + "\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow([row[c] for c in EXPORT_COLUMNS])
    return buffer.getvalue()


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def to_markdown(doc: DocumentInfo, rep: Report, rows: list[dict[str, str]]) -> str:
    lines = [f"# {_md(doc.title)}", "", *(f"{_md(line)}  " for line in _heading(doc, rep)[1:]), "",
             "| " + " | ".join(EXPORT_COLUMNS) + " |", "|" + "---|" * len(EXPORT_COLUMNS)]
    lines += ["| " + " | ".join(_md(row[c]) for c in EXPORT_COLUMNS) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def to_html(doc: DocumentInfo, rep: Report, rows: list[dict[str, str]]) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in EXPORT_COLUMNS)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(row[c])}</td>" for c in EXPORT_COLUMNS) + "</tr>"
                   for row in rows)
    lines = "".join(f"<p>{html.escape(line)}</p>" for line in _heading(doc, rep)[1:])
    return (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{html.escape(doc.title)}</title></head>"
            f"<body><h1>{html.escape(doc.title)}</h1>{lines}<table><thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table></body></html>\n")


def to_json(doc: DocumentInfo, rep: Report, rows: list[dict[str, str]]) -> str:
    return json.dumps({
        "document": asdict(doc),
        "completeness": {"total": rep.total, "mapped": rep.mapped, "explicitly_unmapped": rep.unmapped,
                         "pending": rep.pending, "silent": rep.silent, "in_drift": rep.in_drift,
                         "orphaned": rep.orphaned, "accepted_entries": rep.accepted,
                         "pending_proposals": rep.pending_proposals, "complete": rep.complete,
                         "summary": rep.summary()},
        "columns": list(EXPORT_COLUMNS),
        "rows": rows,
    }, indent=2) + "\n"


EXPORTERS = {"csv": to_csv, "markdown": to_markdown, "html": to_html, "json": to_json}


def lineage(rep: Report, entity: str, column: str) -> Row:
    """The row for one target column: its entry, sources as they stand and drift."""
    for row in rep.rows:
        if row.target["entity"] == entity and row.target["column"] == column:
            return row
    raise MappingError(f"{entity}.{column} is not a target column of this mapping")
