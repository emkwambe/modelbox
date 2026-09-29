"""The drift report: a saved model (the documented design) against a freshly
imported DDL file of the deployed schema (Sprint 8 Step 5).

Built on the schema-diff engine's one comparison core
(``diff_engine.compare``), pairing columns **by name only**: a saved model and
an imported file share no column identity, so a renamed column is reported as
a removal and an addition. Where a removed and an added column of the same
table have the same normalized type and the same position, a "possible
rename" hint names the pair; it is never counted as a rename, and both drifts
stand.

Every drift is classified by the written rules in ``drift_rules`` (breaking,
non-breaking or informational), and one that touches a field the saved
model's dictionary holds as verified is flagged "verified field affected by
drift". The header names both sources, the saved model's version, the
import's time and both reconciliation statuses; an unreconciled import says
so first.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from app.services import drift_rules
from app.services.data_dictionary import FieldKey
from app.services.diff_engine import Change, compare

VERIFIED_FLAG = "verified field affected by drift"

RECONCILIATION = {
    "reconciled": "reconciled: the file's own counts match what was imported",
    "unreconciled": "NOT reconciled: the file's own counts differ from what was imported",
    None: "not imported from a DDL file: no reconciliation status",
}

# The dictionary fields each kind of drift touches, on the drift's column (or
# on each member column of a constraint).
_FIELDS_BY_KIND = {
    "type_changed": ("data_type", "declared_type"),
    "declared_type_changed": ("declared_type",),
    "nullability_changed": ("nullable",),
    "default_changed": ("default",),
    "description_changed": ("description",),
    "primary_key_changed": ("primary_key",),
    "unique_added": ("unique",),
    "unique_removed": ("unique",),
    "check_added": ("check",),
    "check_removed": ("check",),
    "foreign_key_added": ("foreign_key",),
    "foreign_key_removed": ("foreign_key",),
}


@dataclass(frozen=True)
class Source:
    """One side of the comparison, as the header states it."""

    label: str
    name: str
    reconciliation: str | None
    version: int | None = None
    imported_at: str | None = None
    dialect: str | None = None
    model_id: str | None = None


def _column_view(column: ColumnSchema) -> dict[str, Any]:
    return {"type": column.data_type, "declared_type": column.source_data_type, "nullable": column.is_nullable,
            "default": column.source_default_value or column.default_value}


def _value(value: Any) -> Any:
    if isinstance(value, ColumnSchema):
        return _column_view(value)
    if isinstance(value, EntitySchema):
        return {"columns": [c.name for c in value.columns]}
    return value


def _affected(change: Change, statuses: Mapping[FieldKey, str]) -> list[str]:
    """The verified dictionary fields this drift touches, as 'table.column.field'."""
    if change.kind in ("table_added", "column_added"):
        return []  # not in the design: nothing there was verified
    if change.kind == "table_removed":
        keys = [k for k in statuses if k[0] == change.table]
    elif change.kind == "column_removed":
        keys = [k for k in statuses if k[0] == change.table and k[1] == change.column]
    else:
        fields = _FIELDS_BY_KIND.get(change.kind, ())
        if change.kind == "primary_key_changed":
            members = sorted(set(change.before or []) | set(change.after or []))
        elif change.columns:
            members = list(change.columns)
        else:
            members = [change.column]  # a column, or None for a table description
        keys = [(change.table, member, f) for member in members for f in fields]
    return [f"{t}.{c}.{f}" if c else f"{t}.{f}" for t, c, f in keys if statuses.get((t, c, f)) == "verified"]


def _possible_renames(design: SynthesizedModel, deployed: SynthesizedModel,
                      changes: list[Change]) -> list[dict[str, Any]]:
    """A removed and an added column of one table, same normalized type, same position."""
    positions: dict[str, dict[tuple[str, str | None], tuple[int, str]]] = {
        side: {(e.entity_name, c.name): (i, c.data_type.strip().upper()) for e in model.entities
               for i, c in enumerate(e.columns)}
        for side, model in (("design", design), ("deployed", deployed))
    }
    hints = []
    for removed in (c for c in changes if c.kind == "column_removed"):
        for added in (c for c in changes if c.kind == "column_added" and c.table == removed.table):
            before = positions["design"][(removed.table, removed.column)]
            after = positions["deployed"][(added.table, added.column)]
            if before == after:
                hints.append({"table": removed.table, "removed": removed.column, "added": added.column,
                              "type": added.after.data_type, "position": before[0] + 1})
    return hints


def build(design: SynthesizedModel, deployed: SynthesizedModel, design_source: Source, deployed_source: Source,
          statuses: Mapping[FieldKey, str] | None = None, dialect: str = "") -> dict[str, Any]:
    """The report as one document; every format renders it."""
    statuses = statuses or {}
    changes = compare(design, deployed, identity=False)
    drifts = []
    for change in changes:
        rule = drift_rules.classify(change, dialect)
        affected = _affected(change, statuses)
        drifts.append({
            "kind": change.kind, "table": change.table, "column": change.column, "columns": list(change.columns),
            "before": _value(change.before), "after": _value(change.after), "detail": change.detail,
            "class": rule.cls, "rule": rule.id, "rule_text": rule.text,
            "verified_fields_affected": affected, "flag": VERIFIED_FLAG if affected else None,
        })
    warnings = [f"{side.label} is an unreconciled import: {RECONCILIATION['unreconciled']}. Read its import "
                "report before relying on this comparison."
                for side in (deployed_source, design_source) if side.reconciliation == "unreconciled"]
    counts = {cls: sum(1 for d in drifts if d["class"] == cls) for cls in drift_rules.CLASSES}
    return {
        "report": "Drift report",
        "warnings": warnings,
        "design": _source(design_source),
        "deployed": _source(deployed_source),
        "summary": {**counts, "total": len(drifts),
                    "verified_fields_affected": sum(1 for d in drifts if d["flag"])},
        "drifts": drifts,
        "possible_renames": _possible_renames(design, deployed, changes),
    }


def _source(source: Source) -> dict[str, Any]:
    return {"label": source.label, "name": source.name, "model_id": source.model_id, "version": source.version,
            "imported_at": source.imported_at, "dialect": source.dialect,
            "reconciliation": source.reconciliation, "statement": RECONCILIATION[source.reconciliation]}


# -- rendering ------------------------------------------------------------------
def _where(d: dict[str, Any]) -> str:
    if d["column"]:
        return f"{d['table']}.{d['column']}"
    if d["columns"]:
        return f"{d['table']}({', '.join(d['columns'])})"
    return d["table"]


def _short(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, dict):
        if "type" in value:
            parts = [value["type"]]
            if value.get("declared_type"):
                parts.append(f"declared {value['declared_type']}")
            parts.append("nullable" if value["nullable"] else "NOT NULL")
            if value.get("default"):
                parts.append(f"default {value['default']}")
            return ", ".join(parts)
        return f"{len(value.get('columns', []))} columns"
    if isinstance(value, list):
        return "(" + ", ".join(value) + ")" if value else "none"
    if isinstance(value, bool):
        return "nullable" if value else "NOT NULL"
    return str(value)


def _change_text(d: dict[str, Any]) -> tuple[str, str]:
    before, after = _short(d["before"]), _short(d["after"])
    if d["kind"] == "type_changed":
        declared = d["detail"]
        before += f" (declared {declared.get('declared_before') or '—'})"
        after += f" (declared {declared.get('declared_after') or '—'})"
    if d["kind"].startswith("foreign_key"):
        target = f"→ {d['detail']['to']}({', '.join(d['detail']['to_columns'])})"
        before, after = (target, "—") if d["kind"].endswith("removed") else ("—", target)
    return before, after


def _source_line(s: dict[str, Any]) -> str:
    parts = [f"{s['label']}: {s['name']}"]
    if s["version"] is not None:
        parts.append(f"version {s['version']}")
    if s["imported_at"]:
        parts.append(f"imported {s['imported_at']}")
    if s["dialect"]:
        parts.append(s["dialect"])
    return ", ".join(parts) + f" — {s['statement']}"


def _counts(s: dict[str, Any]) -> str:
    return (f"{s['total']} — {s['breaking']} breaking, {s['non-breaking']} non-breaking, "
            f"{s['informational']} informational; {s['verified_fields_affected']} touch a verified field")


_MATCHING = "Columns are matched by name: a renamed column is a removal and an addition."


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def to_markdown(doc: dict[str, Any]) -> str:
    lines = [f"# {doc['report']}", ""]
    lines += [f"> **Unreconciled import.** {w}" for w in doc["warnings"]]
    if doc["warnings"]:
        lines.append("")
    s = doc["summary"]
    lines += [
        f"- **Design:** {_source_line(doc['design'])}",
        f"- **Deployed:** {_source_line(doc['deployed'])}",
        f"- **Drifts:** {_counts(s)}",
        "",
        f"_{_MATCHING} Each drift is classified by the rule named beside it (see the user guide)._",
        "",
    ]
    if doc["drifts"]:
        lines += ["| Class | Rule | Drift | Where | Design | Deployed | Flag |", "|---|---|---|---|---|---|---|"]
        for d in doc["drifts"]:
            before, after = _change_text(d)
            flag = f"{d['flag']}: {', '.join(d['verified_fields_affected'])}" if d["flag"] else ""
            lines.append(f"| {d['class']} | {d['rule']} | {d['kind'].replace('_', ' ')} | {_md(_where(d))} | "
                         f"{_md(before)} | {_md(after)} | {_md(flag)} |")
        lines.append("")
    else:
        lines += ["No drift: the deployed schema matches the design.", ""]
    if doc["possible_renames"]:
        lines += ["## Possible renames (hints, not counted as renames)", ""]
        lines += [f"- {h['table']}: `{h['removed']}` removed and `{h['added']}` added, same type ({h['type']}) "
                  f"at position {h['position']}. Both are reported above as a removal and an addition."
                  for h in doc["possible_renames"]]
        lines.append("")
    return "\n".join(lines)


_STYLE = (
    "<style>body{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#0f172a}"
    "table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}"
    "th,td{border:1px solid #e2e8f0;padding:6px 10px;text-align:left;font-size:14px}"
    "th{background:#f8fafc}.muted{color:#64748b}.warning{border:2px solid #b45309;padding:.75rem;"
    "background:#fffbeb}.breaking{color:#be123c;font-weight:600}.flag{color:#b45309;font-weight:600}"
    "</style></head><body>"
)


def _esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_html(doc: dict[str, Any]) -> str:
    s = doc["summary"]
    parts = ["<!DOCTYPE html>", '<html lang="en"><head><meta charset="utf-8">',
             f"<title>{_esc(doc['report'])}</title>", _STYLE, f"<h1>{_esc(doc['report'])}</h1>"]
    parts += [f'<p class="warning" role="alert"><strong>Unreconciled import.</strong> {_esc(w)}</p>'
              for w in doc["warnings"]]
    parts += [
        f"<p><strong>Design:</strong> {_esc(_source_line(doc['design']))}</p>",
        f"<p><strong>Deployed:</strong> {_esc(_source_line(doc['deployed']))}</p>",
        f"<p><strong>Drifts:</strong> {_esc(_counts(s))}</p>",
        f'<p class="muted">{_MATCHING}</p>',
    ]
    if doc["drifts"]:
        parts.append("<table><thead><tr><th>Class</th><th>Rule</th><th>Drift</th><th>Where</th><th>Design</th>"
                     "<th>Deployed</th><th>Flag</th></tr></thead><tbody>")
        for d in doc["drifts"]:
            before, after = _change_text(d)
            flag = f"{d['flag']}: {', '.join(d['verified_fields_affected'])}" if d["flag"] else ""
            css = ' class="breaking"' if d["class"] == drift_rules.BREAKING else ""
            parts.append(f"<tr><td{css}>{_esc(d['class'])}</td><td>{_esc(d['rule'])}</td>"
                         f"<td>{_esc(d['kind'].replace('_', ' '))}</td><td><code>{_esc(_where(d))}</code></td>"
                         f"<td>{_esc(before)}</td><td>{_esc(after)}</td>"
                         f'<td class="flag">{_esc(flag)}</td></tr>')
        parts.append("</tbody></table>")
    else:
        parts.append("<p>No drift: the deployed schema matches the design.</p>")
    if doc["possible_renames"]:
        parts.append("<h2>Possible renames (hints, not counted as renames)</h2><ul>")
        parts += [f"<li>{_esc(h['table'])}: <code>{_esc(h['removed'])}</code> removed and "
                  f"<code>{_esc(h['added'])}</code> added, same type ({_esc(h['type'])}) at position "
                  f"{h['position']}.</li>" for h in doc["possible_renames"]]
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def to_json(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, default=str)


FORMATS = {"markdown": ("drift_report.md", to_markdown), "html": ("drift_report.html", to_html),
           "json": ("drift_report.json", to_json)}


def render(doc: dict[str, Any], fmt: str) -> dict[str, str]:
    name, renderer = FORMATS[fmt]
    return {name: renderer(doc)}
