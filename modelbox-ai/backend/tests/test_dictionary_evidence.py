"""The dictionary agrees with the source database's catalog (Sprint 8 Step 4a, item 6).

For Oracle HR and AdventureWorks, the dictionary built from the imported model
is read back — its JSON and its CSV, the two machine-readable formats — and,
table by table, its column count, primary-key and foreign-key memberships,
UNIQUE and CHECK constraints, and table and column descriptions are compared
with the catalog manifest, which the source database's own catalog views
produced. The dictionary is not asked what it thinks the counts are; they are
counted from its rows.

A negative control drops one field (the column description) from the export,
and the comparison then fails.
"""

from __future__ import annotations

import csv
import io
import json
import logging

import pytest

from app.services import data_dictionary
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService
from tests.test_ddl_round_trip import DDL

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

FIXTURES = [("oracle", "hr"), ("tsql", "adventureworks")]
KINDS = ("columns", "primary_keys", "foreign_keys", "unique_constraints", "check_constraints",
         "table_descriptions", "column_descriptions")


def _catalog(dialect: str, stem: str) -> dict[str, dict[str, int]]:
    manifest = json.loads((DDL / dialect / f"{stem}.manifest.json").read_text(encoding="utf-8"))
    return {t["name"].split(".")[-1]: {k: int(t[k]) for k in KINDS} for t in manifest["tables"]}


def _files(dialect: str, stem: str, fmt: str) -> dict[str, str]:
    result = import_ddl((DDL / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert result.status == "reconciled" and result.model is not None
    return ExporterService(source_dialect=dialect).export_data_dictionary(result.model, fmt, stem, result.status)


def _from_json(dialect: str, stem: str) -> dict[str, dict[str, int]]:
    doc = json.loads(_files(dialect, stem, "json")["data_dictionary.json"])
    counts: dict[str, dict[str, int]] = {}
    for entity in doc["entities"]:
        columns = entity["columns"]
        fks = {(r["to"], tuple(r["from_columns"])) for r in doc["relationships"]
               if r["from"] == entity["name"] and r["resolved"]}
        counts[entity["name"]] = {
            "columns": len(columns),
            "primary_keys": 1 if any(c.get("primary_key") for c in columns) else 0,
            "foreign_keys": len(fks),
            "unique_constraints": len({tuple(u) for c in columns for u in c.get("unique") or []}),
            "check_constraints": len({k for c in columns for k in c.get("check") or []}),
            "table_descriptions": 1 if entity["description"] else 0,
            "column_descriptions": sum(1 for c in columns if c.get("description")),
        }
    return counts


def _from_csv(dialect: str, stem: str) -> dict[str, dict[str, int]]:
    """The CSV's columns, keys and descriptions, counted from its rows."""
    rows = list(csv.DictReader(io.StringIO(_files(dialect, stem, "csv")["data_dictionary.csv"])))
    assert rows and all(r["source_reconciliation"] == "reconciled" for r in rows)
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        table = counts.setdefault(row["table"], {"columns": 0, "primary_keys": 0, "table_descriptions": 0,
                                                 "column_descriptions": 0})
        table["columns"] += 1
        table["primary_keys"] = 1 if row.get("primary_key") or table["primary_keys"] else 0
        table["table_descriptions"] = 1 if row["table_description"] else 0
        table["column_descriptions"] += 1 if row.get("description") else 0
    return counts


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[s for _, s in FIXTURES])
def test_the_dictionary_json_matches_the_catalog_table_by_table(dialect: str, stem: str) -> None:
    assert _from_json(dialect, stem) == _catalog(dialect, stem)


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[s for _, s in FIXTURES])
def test_the_dictionary_csv_matches_the_catalog_table_by_table(dialect: str, stem: str) -> None:
    catalog = _catalog(dialect, stem)
    kinds = ("columns", "primary_keys", "table_descriptions", "column_descriptions")
    assert _from_csv(dialect, stem) == {t: {k: c[k] for k in kinds} for t, c in catalog.items()}


def test_adventureworks_totals_are_the_catalogs() -> None:
    """The headline: 71 tables, 486 columns, 90 foreign keys, 89 checks, 556 descriptions."""
    counts = _from_json("tsql", "adventureworks")
    total = {k: sum(t[k] for t in counts.values()) for k in KINDS}
    assert (len(counts), total["columns"], total["foreign_keys"], total["check_constraints"],
            total["table_descriptions"] + total["column_descriptions"]) == (71, 486, 90, 89, 556)


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[s for _, s in FIXTURES])
def test_negative_control_a_dictionary_missing_one_field_fails(
    dialect: str, stem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(data_dictionary, "COLUMN_FIELDS",
                        tuple(f for f in data_dictionary.COLUMN_FIELDS if f.key != "description"))
    assert _from_json(dialect, stem) != _catalog(dialect, stem)
