"""The data dictionary: what the model holds, field by field, in four formats.

Sprint 8 Step 4a. The fields are the ones the model already stores, in the
order the R2 field study lists them (tier S, read from DDL, then the tier H
fields the model holds). Fields the model does not store yet (business name,
owner, critical data element, permissible values, review status,
classification) are left out, not shown blank. PII and validation rules are
shown as recorded: nothing in this dictionary has been checked against a
source beyond the import's reconciliation, whose status heads every format.

One structured document is built once (:func:`build`) and each format renders
it, so the formats cannot disagree about a field.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Field:
    """One dictionary field: its JSON key, its label, and how it is read."""

    key: str
    label: str
    value: Callable[[_Column], Any]


# R2_DICTIONARY_STTM_FIELDS.md, R2-2: name and ordinal; type; nullable;
# default; primary key (and position), unique; foreign key target; checks;
# source comment / definition; PII type; validation rules.
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
    Field("pii", "PII (as recorded)", _pii),
    Field("validation_rules", "Validation rules (as recorded)", _validation_rules),
)


def _text(value: Any, field: Field) -> str:
    """A field's value as a cell of text."""
    if value is None or value == [] or value == {}:
        return ""
    if field.key == "nullable":
        return "yes" if value else "no"
    if field.key == "unique":
        return "; ".join("yes" if len(cols) == 1 else f"({', '.join(cols)})" for cols in value)
    if field.key == "validation_rules":
        return "; ".join(f"{k} {v}" for k, v in value.items())
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def build(model: SynthesizedModel, dataset: str, reconciliation: str | None) -> dict[str, Any]:
    """The dictionary as one structured document; every format renders this."""
    entities = []
    for entity in model.entities:
        columns = []
        for index, column in enumerate(entity.columns):
            position = (column.ordinal_position if column.ordinal_position is not None else index) + 1
            context = _Column(entity, column, position, model.relationships)
            columns.append({f.key: f.value(context) for f in COLUMN_FIELDS})
        entities.append({
            "name": entity.entity_name,
            "description": entity.description,
            "grain": entity.grain,
            "entity_type": str(getattr(entity.entity_type, "value", entity.entity_type)),
            "columns": columns,
        })
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
        "paradigm": str(getattr(model.paradigm, "value", model.paradigm)),
        "entities": entities,
        "relationships": relationships,
    }


def _pairs(rel: dict[str, Any]) -> str:
    if not rel["resolved"]:
        return "UNRESOLVED: columns not chosen"
    return ", ".join(f"{f} → {t}" for f, t in zip(rel["from_columns"], rel["to_columns"], strict=True))


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def to_markdown(doc: dict[str, Any]) -> str:
    lines = [f"# Data Dictionary — {doc['dataset']}", ""]
    if doc["source"]["reconciliation"] == "unreconciled":
        lines += [f"> **Unreconciled import.** {doc['source']['statement']}", ""]
    lines += [
        f"- **Source:** {doc['source']['statement']}",
        f"- **Paradigm:** {doc['paradigm']}",
        f"- **Entities:** {len(doc['entities'])}",
        "",
        "_Generated by ModelBox AI. PII and validation rules are shown as recorded in the model._",
        "",
        "## Entities",
        "",
    ]
    for entity in doc["entities"]:
        lines.append(f"### {entity['name']} ({entity['entity_type']})")
        if entity["description"]:
            lines += ["", _md(entity["description"])]
        if entity["grain"]:
            lines += ["", f"**Grain:** {_md(entity['grain'])}"]
        lines += ["", "| " + " | ".join(f.label for f in COLUMN_FIELDS) + " |",
                  "|" + "---|" * len(COLUMN_FIELDS)]
        for column in entity["columns"]:
            lines.append("| " + " | ".join(_md(_text(column[f.key], f)) for f in COLUMN_FIELDS) + " |")
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
        (f'<p class="muted">Generated by ModelBox AI · paradigm {_esc(doc["paradigm"])} · '
         f"{len(doc['entities'])} entities. PII and validation rules are shown as recorded in the model.</p>"),
    ]
    for entity in doc["entities"]:
        parts.append(f"<h2>{_esc(entity['name'])} <span class=\"muted\">({_esc(entity['entity_type'])})</span></h2>")
        if entity["description"]:
            parts.append(f"<p>{_esc(entity['description'])}</p>")
        if entity["grain"]:
            parts.append(f"<p><strong>Grain:</strong> {_esc(entity['grain'])}</p>")
        parts.append("<table><thead><tr>" + "".join(f"<th>{_esc(f.label)}</th>" for f in COLUMN_FIELDS)
                     + "</tr></thead><tbody>")
        for column in entity["columns"]:
            parts.append("<tr>" + "".join(f"<td>{_esc(_text(column[f.key], f))}</td>" for f in COLUMN_FIELDS)
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


TABLE_FIELDS = (("table", "name"), ("table_description", "description"), ("grain", "grain"),
                ("entity_type", "entity_type"))


def to_csv(doc: dict[str, Any]) -> dict[str, str]:
    """Two files: one row per column, and one row per relationship.

    CSV has no header block, so the source's reconciliation status is the
    first column of every row.
    """
    columns = io.StringIO()
    writer = csv.writer(columns, lineterminator="\n")
    writer.writerow(["source_reconciliation", *(key for key, _ in TABLE_FIELDS), *(f.key for f in COLUMN_FIELDS)])
    status = doc["source"]["reconciliation"] or "not imported"
    for entity in doc["entities"]:
        for column in entity["columns"]:
            writer.writerow([status, *(entity[source] or "" for _, source in TABLE_FIELDS),
                             *(_text(column[f.key], f) for f in COLUMN_FIELDS)])
    relationships = io.StringIO()
    writer = csv.writer(relationships, lineterminator="\n")
    writer.writerow(["source_reconciliation", "from", "from_columns", "to", "to_columns", "cardinality", "name",
                     "resolved"])
    for rel in doc["relationships"]:
        writer.writerow([status, rel["from"], ";".join(rel["from_columns"]), rel["to"], ";".join(rel["to_columns"]),
                         rel["cardinality"], rel["name"] or "", "yes" if rel["resolved"] else "no: columns not chosen"])
    return {"data_dictionary.csv": columns.getvalue(), "data_dictionary_relationships.csv": relationships.getvalue()}
