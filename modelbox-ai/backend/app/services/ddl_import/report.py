"""Render an import's reconciliation report as Markdown or JSON.

The report is an engagement artifact in its own right: it says what was
compared, what matched, and every gap by statement. The JSON form is the
report exactly as stored on the model; the Markdown form is written from it
and adds nothing the JSON does not hold.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.ddl_import.counter import KINDS

_KIND_LABELS = {
    "count": "Tables", "columns": "Columns", "primary_keys": "Primary keys",
    "foreign_keys": "Foreign keys", "unique_constraints": "UNIQUE constraints",
    "check_constraints": "CHECK constraints", "table_descriptions": "Table descriptions",
    "column_descriptions": "Column descriptions",
}


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=False, default=str) + "\n"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def to_markdown(report: dict[str, Any], title: str | None = None) -> str:
    status = report.get("status", "unreconciled")
    lines = [
        f"# DDL import report: {_cell(title or report.get('file', 'upload'))}",
        "",
        f"- **Status:** {status}",
        f"- **File:** {_cell(report.get('file'))}",
        f"- **Dialect:** {_cell(report.get('dialect'))} ({_cell(report.get('evidence', ''))})",
        f"- **Encoding:** {_cell(report.get('encoding'))}",
        "",
    ]
    if status != "reconciled":
        lines += ["**This import is unreconciled.** No dictionary or report built from it may call itself verified.", ""]

    reconciliation = report.get("reconciliation")
    if reconciliation:
        lines += [
            "## Counts",
            "",
            (
                "The source counts are read from the file by a counter that shares no code with the parser. "
                "Partitions are counted apart from tables: a partition is metadata of its parent table."
            ),
            "",
            "| | Tables: source | Tables: imported | Partitions: source | Partitions: imported |",
            "| :-- | --: | --: | --: | --: |",
        ]
        for kind in ("count", *KINDS):
            source, imported = reconciliation["source"], reconciliation["imported"]
            lines.append(
                f"| {_KIND_LABELS[kind]} | {source['tables'][kind]} | {imported['tables'][kind]} "
                f"| {source['partitions'][kind]} | {imported['partitions'][kind]} |"
            )
        lines.append("")
        gaps = reconciliation.get("gaps", [])
        lines += [f"## Gaps ({len(gaps)})", ""]
        if not gaps:
            lines += ["None: every count taken from the file matches what was imported.", ""]
        for gap in gaps:
            statements = ", ".join(f"#{s['index']} (line {s['line']}): {_cell(s['statement'])}"
                                   for s in gap.get("statements", [])) or "no statement names it"
            lines.append(f"- **{_cell(gap['table'])}**, {gap['kind']}: source {gap['source']}, "
                         f"imported {gap['imported']}. Statements: {statements}")
        if gaps:
            lines.append("")

    failures = report.get("failures", [])
    lines += [f"## Failures ({len(failures)})", ""]
    if not failures:
        lines += ["None.", ""]
    for failure in failures:
        where = f"#{failure['statement']} (line {failure.get('line')})" if failure.get("statement") else "the file"
        head = f" `{_cell(failure['head'])}`" if failure.get("head") else ""
        lines.append(f"- {where}{head}: {_cell(failure['reason'])}")
    if failures:
        lines.append("")

    held = report.get("held", {})
    if held:
        lines += ["## Held in this report", "",
                  "Content the model cannot hold yet, kept here rather than lost.", ""]
        for table, items in held.items():
            for key, values in items.items():
                if key == "partitions":
                    lines.append(f"- **{_cell(table)}**: {len(values)} partitions "
                                 f"({', '.join(_cell(p['name']) for p in values[:5])}"
                                 f"{', …' if len(values) > 5 else ''})")
                elif key == "partitioning":
                    lines.append(f"- **{_cell(table)}**: {_cell(values)}")
                else:
                    for value in values:
                        detail = value.get("expression") or ", ".join(value.get("columns", [])) \
                            or value.get("type", "")
                        if value.get("column"):
                            detail = f"{value['column']} {detail}".strip()
                        lines.append(f"- **{_cell(table)}**, {key.replace('_', ' ')}: {_cell(detail)} ({value['reason']})")
        lines.append("")

    not_validated = report.get("not_validated", [])
    if not_validated:
        lines += [f"## Added WITH NOCHECK ({len(not_validated)})", "",
                  "In the model, but not validated against the rows that existed when added.", ""]
        lines += [f"- #{i['index']} {_cell(i['statement'])}" for i in not_validated]
        lines.append("")

    not_imported = report.get("not_imported", [])
    lines += [f"## Not imported ({len(not_imported)} statements)", "",
              "Statements that are not part of a logical model, each skipped by a named rule.", ""]
    by_reason: dict[str, list[dict[str, Any]]] = {}
    for item in not_imported:
        by_reason.setdefault(item["reason"], []).append(item)
    for reason, items in sorted(by_reason.items()):
        lines.append(f"- **{reason}** ({len(items)}): "
                     + "; ".join(f"#{i['index']} {_cell(i['statement'])}" for i in items[:5])
                     + ("; …" if len(items) > 5 else ""))
    if report.get("normalizer"):
        lines += ["", "## Normalizer rules applied", ""]
        lines += [f"- {rule}: {count}" for rule, count in report["normalizer"].items()]
    return "\n".join(lines).rstrip() + "\n"
