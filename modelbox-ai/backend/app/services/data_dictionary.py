"""The data dictionary: what the model holds, field by field, in four formats.

Sprint 8 Step 4a built it from the fields the model stored, structural fields
first (read from DDL and reconciled), then the fields a person supplies, so a
reader meets what the source proves before what someone asserted. Step 4b adds the fields a person supplies (business name, permissible
values, unit, classification, critical data element, authoritative source; at
table level business name, owners and authoritative source) and each field's
status: **verified** only where its attestation says so, otherwise **pending
review** or **recorded** (a value with no recorded provenance). The header
states "N of M fields verified, K pending review", where M counts every field
that holds a value and K = M - N.

One structured document is built once (:func:`build`) and each format renders
it, so the formats cannot disagree about a field or its status.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)

RECONCILIATION_TEXT = {
    "reconciled": "Imported from a DDL file, and reconciled: the file's own counts of tables, columns, keys, "
                  "constraints and descriptions match what was imported.",
    "unreconciled": "Imported from a DDL file, and NOT reconciled: the file's own counts differ from what was "
                    "imported, or statements could not be imported. Read the import report before relying on "
                    "this dictionary.",
    None: "Not imported from a DDL file: there is no reconciliation status.",
}


@dataclass(frozen=True)
class _Column:
    """Everything one column's fields are read from."""

    entity: EntitySchema
    column: ColumnSchema
    position: int
    relationships: list[RelationshipSchema]
    # The workspace's classification levels by id, for their names.
    levels: Mapping[uuid.UUID, str] = field(default_factory=dict)


def _side(entity: str, columns: list[str]) -> str:
    if len(columns) == 1:
        return f"{entity}.{columns[0]}"
    return f"{entity}({', '.join(columns)})" if columns else entity


def _primary_key(c: _Column) -> int | None:
    key = c.entity.primary_key
    return key.index(c.column.name) + 1 if c.column.name in key else None


def _unique(c: _Column) -> list[list[str]]:
    return [u.columns for u in c.entity.unique_constraints if c.column.name in u.columns]


def _foreign_key(c: _Column) -> list[str]:
    targets = []
    for rel in c.relationships:
        if rel.from_ref == c.entity.entity_name and rel.resolved and c.column.name in rel.from_columns:
            targets.append(_side(rel.to_ref, rel.to_columns) if len(rel.from_columns) > 1
                           else f"{rel.to_ref}.{rel.to_columns[0]}")
    return targets


def _checks(c: _Column) -> list[str]:
    return [k.expression for k in c.entity.check_constraints if c.column.name in k.columns]


def _pii(c: _Column) -> str | None:
    if not c.column.is_pii:
        return None
    pii_type = c.column.pii_type
    return str(getattr(pii_type, "value", pii_type)) if pii_type else "PII"


def _validation_rules(c: _Column) -> dict[str, Any]:
    rules: dict[str, Any] = {}
    if c.column.min_value is not None:
        rules["min"] = c.column.min_value
    if c.column.max_value is not None:
        rules["max"] = c.column.max_value
    if c.column.regex_pattern:
        rules["regex"] = c.column.regex_pattern
    return rules


def _classification(c: _Column) -> str | None:
    level = c.column.classification_level_id
    return c.levels.get(level, str(level)) if level else None


@dataclass(frozen=True)
class Field:
    """One dictionary field: its JSON key, its label, and how it is read.

    ``raw`` is the value a status refers to, when it differs from the shown
    one: a classification is attested by its level's id, so renaming the level
    renames every use without changing the value.
    """

    key: str
    label: str
    value: Callable[[_Column], Any]
    raw: Callable[[_Column], Any] | None = None

    def raw_value(self, c: _Column) -> Any:
        return (self.raw or self.value)(c)


# The field order, structural fields first: name and ordinal; type; nullable;
# default; primary key (and position), unique; foreign key target; checks;
# source comment / definition; then what a person supplies: business name;
# permissible values; unit; classification and PII type; critical data
# element; authoritative source; validation rules.
COLUMN_FIELDS: tuple[Field, ...] = (
    Field("name", "Column", lambda c: c.column.name),
    Field("position", "Position", lambda c: c.position),
    Field("data_type", "Type", lambda c: c.column.data_type),
    Field("declared_type", "Declared type", lambda c: c.column.source_data_type),
    Field("nullable", "Nullable", lambda c: c.column.is_nullable),
    Field("default", "Default", lambda c: c.column.source_default_value or c.column.default_value),
    Field("primary_key", "Primary key", _primary_key),
    Field("unique", "Unique", _unique),
    Field("foreign_key", "Foreign key", _foreign_key),
    Field("check", "Check", _checks),
    Field("description", "Description", lambda c: c.column.description),
    Field("business_name", "Business name", lambda c: c.column.business_name),
    Field("permissible_values", "Permissible values", lambda c: c.column.permissible_values),
    Field("unit", "Unit", lambda c: c.column.unit),
    Field("classification", "Classification", _classification,
          raw=lambda c: str(c.column.classification_level_id) if c.column.classification_level_id else None),
    Field("pii", "PII", _pii),
    Field("critical_data_element", "Critical data element", lambda c: c.column.critical_data_element),
    Field("authoritative_source", "Authoritative source", lambda c: c.column.authoritative_source),
    Field("validation_rules", "Validation rules", _validation_rules),
)

# Name and position identify a column; every other field is attested.
IDENTITY_FIELDS = frozenset({"name", "position"})
ATTESTED_COLUMN_FIELDS = tuple(f for f in COLUMN_FIELDS if f.key not in IDENTITY_FIELDS)


@dataclass(frozen=True)
class TableField:
    key: str
    label: str
    value: Callable[[EntitySchema], Any]


TABLE_FIELDS_R2: tuple[TableField, ...] = (
    TableField("name", "Table", lambda e: e.entity_name),
    TableField("business_name", "Business name", lambda e: e.business_name),
    TableField("description", "Description", lambda e: e.description),
    TableField("grain", "Grain", lambda e: e.grain),
    TableField("entity_type", "Type", lambda e: str(getattr(e.entity_type, "value", e.entity_type))),
    TableField("business_owner", "Business owner", lambda e: e.business_owner),
    TableField("it_steward", "IT steward", lambda e: e.it_steward),
    TableField("authoritative_source", "Authoritative source", lambda e: e.authoritative_source),
)
ATTESTED_TABLE_FIELDS = tuple(f for f in TABLE_FIELDS_R2 if f.key != "name")

#: How each status reads in a rendered dictionary.
STATUS_TEXT = {"verified": "verified", "pending": "pending review", "recorded": "recorded"}

#: (entity name, column name or None for a table field, field key).
FieldKey = tuple[str, str | None, str]


def holds_value(value: Any) -> bool:
    """A field counts, and can be attested, only when it holds something.
    ``False`` is a value (not nullable; assessed as not critical)."""
    return value is not None and value != "" and value != [] and value != {}


def column_context(entity: EntitySchema, index: int, column: ColumnSchema, relationships: list[RelationshipSchema],
                   levels: Mapping[uuid.UUID, str] | None = None) -> _Column:
    position = (column.ordinal_position if column.ordinal_position is not None else index) + 1
    return _Column(entity, column, position, relationships, levels or {})


def verification_statement(verified: int, fields: int) -> str:
    return f"{verified} of {fields} fields verified, {fields - verified} pending review"


def _text(value: Any, field: Field | TableField) -> str:
    """A field's value as a cell of text."""
    if value is None or value == [] or value == {}:
        return ""
    if field.key in ("nullable", "critical_data_element"):
        return "yes" if value else "no"
    if field.key == "unique":
        return "; ".join("yes" if len(cols) == 1 else f"({', '.join(cols)})" for cols in value)
    if field.key == "validation_rules":
        return "; ".join(f"{k} {v}" for k, v in value.items())
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def build(model: SynthesizedModel, dataset: str, reconciliation: str | None,
          statuses: Mapping[FieldKey, str] | None = None,
          levels: Mapping[uuid.UUID, str] | None = None) -> dict[str, Any]:
    """The dictionary as one structured document; every format renders this.

    ``statuses`` holds each attested field's status by :data:`FieldKey`. A
    field holding a value with no status there is ``recorded``: nothing
    records where its value came from. Nothing else can make a field
    verified.
    """
    statuses = statuses or {}
    counted = verified = 0

    def status_of(key: FieldKey) -> str:
        nonlocal counted, verified
        status = statuses.get(key, "recorded")
        counted += 1
        verified += status == "verified"
        return status

    entities = []
    for entity in model.entities:
        columns = []
        for index, column in enumerate(entity.columns):
            context = column_context(entity, index, column, model.relationships, levels)
            values = {f.key: f.value(context) for f in COLUMN_FIELDS}
            values["status"] = {f.key: status_of((entity.entity_name, column.name, f.key))
                                for f in COLUMN_FIELDS
                                if f.key not in IDENTITY_FIELDS and holds_value(values[f.key])}
            columns.append(values)
        table = {f.key: f.value(entity) for f in TABLE_FIELDS_R2}
        table["status"] = {f.key: status_of((entity.entity_name, None, f.key))
                           for f in ATTESTED_TABLE_FIELDS if holds_value(table[f.key])}
        entities.append({**table, "columns": columns})
    relationships = [{
        "from": rel.from_ref, "from_columns": rel.from_columns,
        "to": rel.to_ref, "to_columns": rel.to_columns,
        "cardinality": str(getattr(rel.cardinality, "value", rel.cardinality)),
        "name": rel.name,
        "resolved": rel.resolved,
    } for rel in model.relationships]
    return {
        "dataset": dataset,
        "generated_by": "ModelBox AI",
        "source": {"reconciliation": reconciliation, "statement": RECONCILIATION_TEXT[reconciliation]},
        "verification": {"verified": verified, "fields": counted, "pending_review": counted - verified,
                         "statement": verification_statement(verified, counted)},
        "paradigm": str(getattr(model.paradigm, "value", model.paradigm)),
        "entities": entities,
        "relationships": relationships,
    }


def _cell(item: dict[str, Any], field: Field | TableField) -> str:
    """A field's text followed by its status, when it holds a value."""
    text = _text(item[field.key], field)
    status = item["status"].get(field.key)
    return f"{text} [{STATUS_TEXT[status]}]" if status else text


def _pairs(rel: dict[str, Any]) -> str:
    if not rel["resolved"]:
        return "UNRESOLVED: columns not chosen"
    return ", ".join(f"{f} → {t}" for f, t in zip(rel["from_columns"], rel["to_columns"], strict=True))


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


_LEGEND = ("Each field that holds a value shows its status: verified, pending review, or recorded (no "
           "provenance is recorded for its value).")


def to_markdown(doc: dict[str, Any]) -> str:
    lines = [f"# Data Dictionary — {doc['dataset']}", ""]
    if doc["source"]["reconciliation"] == "unreconciled":
        lines += [f"> **Unreconciled import.** {doc['source']['statement']}", ""]
    lines += [
        f"- **Source:** {doc['source']['statement']}",
        f"- **Status:** {doc['verification']['statement']}",
        f"- **Paradigm:** {doc['paradigm']}",
        f"- **Entities:** {len(doc['entities'])}",
        "",
        f"_Generated by ModelBox AI. {_LEGEND}_",
        "",
        "## Entities",
        "",
    ]
    for entity in doc["entities"]:
        lines.append(f"### {entity['name']}")
        lines.append("")
        for f in ATTESTED_TABLE_FIELDS:
            if holds_value(entity[f.key]):
                lines.append(f"- **{f.label}:** {_md(_cell(entity, f))}")
        lines += ["", "| " + " | ".join(f.label for f in COLUMN_FIELDS) + " |",
                  "|" + "---|" * len(COLUMN_FIELDS)]
        for column in entity["columns"]:
            lines.append("| " + " | ".join(_md(_cell(column, f)) for f in COLUMN_FIELDS) + " |")
        lines.append("")
    if doc["relationships"]:
        lines += ["## Relationships", "", "| From | To | Column pairs | Cardinality | Name |", "|---|---|---|---|---|"]
        for rel in doc["relationships"]:
            lines.append(f"| {_md(rel['from'])} | {_md(rel['to'])} | {_md(_pairs(rel))} | {rel['cardinality']} "
                         f"| {_md(rel['name'] or '')} |")
        lines.append("")
    return "\n".join(lines)


_STYLE = (
    "<style>body{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#0f172a}"
    "h1{margin-bottom:0}h2{margin-top:2rem;border-bottom:1px solid #e2e8f0}"
    "table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}"
    "th,td{border:1px solid #e2e8f0;padding:6px 10px;text-align:left;font-size:14px}"
    "th{background:#f8fafc}.muted{color:#64748b}.warning{border:2px solid #b45309;padding:.75rem;"
    "background:#fffbeb}code{background:#f1f5f9;padding:1px 4px;border-radius:4px}</style></head><body>"
)


def _esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_html(doc: dict[str, Any]) -> str:
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>Data Dictionary — {_esc(doc['dataset'])}</title>",
        _STYLE,
        f"<h1>Data Dictionary — {_esc(doc['dataset'])}</h1>",
    ]
    if doc["source"]["reconciliation"] == "unreconciled":
        parts.append(f'<p class="warning" role="alert"><strong>Unreconciled import.</strong> '
                     f"{_esc(doc['source']['statement'])}</p>")
    parts += [
        f"<p><strong>Source:</strong> {_esc(doc['source']['statement'])}</p>",
        f"<p><strong>Status:</strong> {_esc(doc['verification']['statement'])}</p>",
        (f'<p class="muted">Generated by ModelBox AI · paradigm {_esc(doc["paradigm"])} · '
         f"{len(doc['entities'])} entities. {_esc(_LEGEND)}</p>"),
    ]
    for entity in doc["entities"]:
        parts.append(f"<h2>{_esc(entity['name'])}</h2>")
        rows = [f"<li><strong>{_esc(f.label)}:</strong> {_esc(_cell(entity, f))}</li>"
                for f in ATTESTED_TABLE_FIELDS if holds_value(entity[f.key])]
        if rows:
            parts.append("<ul>" + "".join(rows) + "</ul>")
        parts.append("<table><thead><tr>" + "".join(f"<th>{_esc(f.label)}</th>" for f in COLUMN_FIELDS)
                     + "</tr></thead><tbody>")
        for column in entity["columns"]:
            parts.append("<tr>" + "".join(f"<td>{_esc(_cell(column, f))}</td>" for f in COLUMN_FIELDS)
                         + "</tr>")
        parts.append("</tbody></table>")
    if doc["relationships"]:
        parts.append("<h2>Relationships</h2><table><thead><tr><th>From</th><th>To</th><th>Column pairs</th>"
                     "<th>Cardinality</th><th>Name</th></tr></thead><tbody>")
        for rel in doc["relationships"]:
            parts.append(f"<tr><td><code>{_esc(rel['from'])}</code></td><td><code>{_esc(rel['to'])}</code></td>"
                         f"<td>{_esc(_pairs(rel))}</td><td>{_esc(rel['cardinality'])}</td>"
                         f"<td>{_esc(rel['name'] or '')}</td></tr>")
        parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "\n".join(parts)


def to_json(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2)


def _csv_table_key(key: str) -> str:
    return {"name": "table", "description": "table_description", "business_name": "table_business_name",
            "authoritative_source": "table_authoritative_source"}.get(key, key)


def to_csv(doc: dict[str, Any]) -> dict[str, str]:
    """Two files: one row per column, and one row per relationship.

    CSV has no header block, so the source's reconciliation status and the
    verification count are the first columns of every row, and each attested
    field has a ``<field>_status`` column beside it.
    """
    columns = io.StringIO()
    writer = csv.writer(columns, lineterminator="\n")
    header = ["source_reconciliation", "verification"]
    for tf in TABLE_FIELDS_R2:
        header.append(_csv_table_key(tf.key))
        if tf.key != "name":
            header.append(f"{_csv_table_key(tf.key)}_status")
    for f in COLUMN_FIELDS:
        header.append(f.key)
        if f.key not in IDENTITY_FIELDS:
            header.append(f"{f.key}_status")
    writer.writerow(header)
    status = doc["source"]["reconciliation"] or "not imported"
    verification = doc["verification"]["statement"]
    for entity in doc["entities"]:
        table: list[Any] = []
        for tf in TABLE_FIELDS_R2:
            table.append(_text(entity[tf.key], tf))
            if tf.key != "name":
                table.append(STATUS_TEXT.get(entity["status"].get(tf.key, ""), ""))
        for column in entity["columns"]:
            cells: list[Any] = []
            for f in COLUMN_FIELDS:
                cells.append(_text(column[f.key], f))
                if f.key not in IDENTITY_FIELDS:
                    cells.append(STATUS_TEXT.get(column["status"].get(f.key, ""), ""))
            writer.writerow([status, verification, *table, *cells])
    relationships = io.StringIO()
    writer = csv.writer(relationships, lineterminator="\n")
    writer.writerow(["source_reconciliation", "from", "from_columns", "to", "to_columns", "cardinality", "name",
                     "resolved"])
    for rel in doc["relationships"]:
        writer.writerow([status, rel["from"], ";".join(rel["from_columns"]), rel["to"], ";".join(rel["to_columns"]),
                         rel["cardinality"], rel["name"] or "", "yes" if rel["resolved"] else "no: columns not chosen"])
    return {"data_dictionary.csv": columns.getvalue(), "data_dictionary_relationships.csv": relationships.getvalue()}
