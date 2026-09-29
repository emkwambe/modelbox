"""Genuine export fixtures import with zero gaps against their catalog manifests.

The manifests' counts come from each source database's catalog views
(`tests/fixtures/ddl/`), so they are independent of both the importer and the
counter it reconciles against. Three agreements are asserted for each genuine
fixture, totals and table by table:

* the import reconciles: no failures, no gaps against the file-level counter;
* the counter agrees with the catalog, so its counts deserve to be the
  reconciliation's ground truth;
* what was imported agrees with the catalog.

Partitions are metadata of their parent: Pagila reconciles as 15 tables and
55 partitions, not 70 tables, and the model has 15 entities.

AdventureWorks, scripted by SMO, is also read off the model itself (keys,
defaults and descriptions against the catalog), in every encoding SSMS can
save. Every column in every genuine fixture keeps its declared type verbatim.

The documentation-derived Snowflake fixture is held to a different standard:
the pinned parser does not understand its HYBRID TABLE, and the import must
say so by name and be saved as unreconciled, not report success without it.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from app.services.ddl_import import counter
from app.services.ddl_import.importer import ImportResult, import_ddl

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
GENUINE = [("oracle", "hr"), ("oracle", "co"), ("postgres", "pagila"), ("tsql", "adventureworks")]


def _manifest(dialect: str, stem: str) -> dict[str, Any]:
    return json.loads((DDL / dialect / f"{stem}.manifest.json").read_text(encoding="utf-8"))


def _catalog_totals(manifest: dict[str, Any]) -> dict[str, dict[str, int]]:
    out = {bucket: {"count": 0, **dict.fromkeys(counter.KINDS, 0)} for bucket in ("tables", "partitions")}
    for table in manifest["tables"]:
        bucket = out["partitions" if table.get("partition_of") else "tables"]
        bucket["count"] += 1
        for kind in counter.KINDS:
            bucket[kind] += int(table[kind])
    return out


_RESULTS: dict[tuple[str, str], ImportResult] = {}


def _import(dialect: str, stem: str) -> ImportResult:
    if (dialect, stem) not in _RESULTS:
        raw = (DDL / dialect / f"{stem}.sql").read_bytes()
        _RESULTS[(dialect, stem)] = import_ddl(raw, dialect, f"{stem}.sql")
    return _RESULTS[(dialect, stem)]


@pytest.mark.parametrize(("dialect", "stem"), GENUINE, ids=[s for _, s in GENUINE])
def test_the_import_reconciles_with_no_failures_and_no_gaps(dialect: str, stem: str) -> None:
    result = _import(dialect, stem)
    assert result.report["failures"] == []
    assert result.report["reconciliation"]["gaps"] == []
    assert result.status == "reconciled"


@pytest.mark.parametrize(("dialect", "stem"), GENUINE, ids=[s for _, s in GENUINE])
def test_the_independent_counter_agrees_with_the_catalog(dialect: str, stem: str) -> None:
    manifest = _manifest(dialect, stem)
    per_table = counter.count((DDL / dialect / f"{stem}.sql").read_text(encoding="utf-8"), dialect)
    assert counter.totals(per_table) == _catalog_totals(manifest)
    for table in manifest["tables"]:
        # SQL Server's catalog names a table Schema.Table; the counter keys by the bare name.
        bare = table["name"].split(".")[-1]
        assert per_table[bare].counts == {k: int(table[k]) for k in counter.KINDS}, table["name"]


@pytest.mark.parametrize(("dialect", "stem"), GENUINE, ids=[s for _, s in GENUINE])
def test_what_was_imported_agrees_with_the_catalog(dialect: str, stem: str) -> None:
    assert _import(dialect, stem).report["reconciliation"]["imported"] == _catalog_totals(_manifest(dialect, stem))


def test_pagila_is_15_tables_and_55_partitions_not_70_tables() -> None:
    result = _import("postgres", "pagila")
    imported = result.report["reconciliation"]["imported"]
    assert (imported["tables"]["count"], imported["partitions"]["count"]) == (15, 55)
    assert result.model is not None and len(result.model.entities) == 15
    assert not any(e.entity_name.startswith("payment_p") for e in result.model.entities)
    partitions = result.report["held"]["payment"]["partitions"]
    assert len(partitions) == 55
    assert all(p["bound"].startswith("FOR VALUES FROM") for p in partitions)
    assert result.report["held"]["payment"]["partitioning"].upper().startswith("PARTITION BY")


def test_postgres_nullability_matches_the_catalog_table_by_table() -> None:
    """attnotnull, from the catalog, against the model's columns."""
    catalog = {t["name"]: t["not_null_columns"] for t in _manifest("postgres", "pagila")["tables"]}
    model = _import("postgres", "pagila").model
    assert model is not None
    got = {e.entity_name: sum(1 for c in e.columns if not c.is_nullable) for e in model.entities}
    assert got == {name: catalog[name] for name in got}


@pytest.mark.parametrize("stem", ["hr", "co"])
def test_oracle_nullability_is_bounded_by_the_catalog(stem: str) -> None:
    """The catalog counts NOT NULL constraints, which Oracle declares on key
    columns only sometimes, so it lies between the model's non-nullable
    non-key columns and all its non-nullable columns. A NOT NULL lost in
    normalization falls below the lower bound."""
    catalog = {t["name"]: t["not_null_constraints"] for t in _manifest("oracle", stem)["tables"]}
    model = _import("oracle", stem).model
    assert model is not None
    for entity in model.entities:
        non_key = sum(1 for c in entity.columns if not c.is_nullable and not c.is_primary_key)
        every = sum(1 for c in entity.columns if not c.is_nullable)
        assert non_key <= catalog[entity.entity_name] <= every, entity.entity_name


# --- AdventureWorks, from SQL Server's own scripting ----------------------------------

def test_adventureworks_manifest_is_the_catalog_the_step_names() -> None:
    """The headline figures, pinned: 71 tables, 486 columns, 90 foreign keys,
    89 checks and 556 descriptions, from sys.* catalog views."""
    counts = _manifest("tsql", "adventureworks")["counts"]
    assert (counts["tables"], counts["columns"], counts["foreign_keys"], counts["check_constraints"],
            counts["table_descriptions"] + counts["column_descriptions"]) == (71, 486, 90, 89, 556)
    assert _catalog_totals(_manifest("tsql", "adventureworks"))["tables"]["count"] == counts["tables"]


def test_adventureworks_model_carries_the_catalogs_keys_defaults_and_descriptions() -> None:
    """Read off the model itself, not the importer's counts: every foreign key
    is a relationship or held by name, every default constraint is a column
    default, and every MS_Description is a description."""
    counts = _manifest("tsql", "adventureworks")["counts"]
    result = _import("tsql", "adventureworks")
    model = result.model
    assert model is not None
    held_fks = sum(len(t.get("foreign_keys", [])) for t in result.report["held"].values())
    assert len(model.relationships) + held_fks == counts["foreign_keys"]
    assert sum(1 for e in model.entities for c in e.columns if c.default_value is not None) \
        == counts["default_constraints"]
    assert sum(1 for e in model.entities if e.description) == counts["table_descriptions"]
    assert sum(1 for e in model.entities for c in e.columns if c.description) == counts["column_descriptions"]


ENCODINGS = [
    pytest.param("utf-8", "UTF-8 without BOM", id="utf-8"),
    pytest.param("utf-8-sig", "UTF-8 with BOM", id="utf-8-bom"),
    pytest.param("utf-16", "UTF-16 LE with BOM", id="utf-16-bom"),
    pytest.param("utf-16-le", "UTF-16-LE without BOM", id="utf-16-le"),
]


@pytest.mark.parametrize(("codec", "label"), ENCODINGS)
def test_adventureworks_imports_identically_in_every_encoding(codec: str, label: str) -> None:
    """SSMS saves scripts as UTF-16 by default; the model must not depend on it."""
    text = (DDL / "tsql" / "adventureworks.sql").read_text(encoding="utf-8")
    result = import_ddl(text.encode(codec), "tsql", "adventureworks.sql")
    baseline = _import("tsql", "adventureworks")
    assert result.encoding == label
    assert result.status == "reconciled"
    assert result.model is not None and baseline.model is not None
    assert result.model.model_dump() == baseline.model.model_dump()
    assert {k: v for k, v in result.report.items() if k != "encoding"} == \
        {k: v for k, v in baseline.report.items() if k != "encoding"}


# --- Original type text ------------------------------------------------------------

_NOT_A_TYPE = re.compile(r"\b(?:NOT|NULL|DEFAULT|CONSTRAINT|IDENTITY|PRIMARY|REFERENCES|COLLATE)\b", re.IGNORECASE)


def _declared_verbatim(text: str, column: str, source: str) -> bool:
    """Whether the file declares ``column`` followed by exactly ``source``: the
    whole type, ending where the declaration's next word or comma begins."""
    if _NOT_A_TYPE.search(source):
        return False
    name = re.escape(column)
    pattern = rf'(?:"{name}"|\[{name}\]|(?<![\w"\[]){name})\s+{re.escape(source)}(?=[\s,)])'
    return re.search(pattern, text) is not None


def test_negative_control_a_truncated_or_overlong_type_is_not_verbatim() -> None:
    text = (DDL / "oracle" / "hr.sql").read_text(encoding="utf-8")
    assert _declared_verbatim(text, "EMAIL", "VARCHAR2(25)")
    assert not _declared_verbatim(text, "EMAIL", "VARCHAR2")
    assert not _declared_verbatim(text, "EMAIL", "VARCHAR2(25) CONSTRAINT")
    assert not _declared_verbatim(text, "EMAIL", "VARCHAR2(2")


@pytest.mark.parametrize(("dialect", "stem"), GENUINE, ids=[s for _, s in GENUINE])
def test_every_column_keeps_its_type_exactly_as_the_file_declares_it(dialect: str, stem: str) -> None:
    text = (DDL / dialect / f"{stem}.sql").read_text(encoding="utf-8")
    model = _import(dialect, stem).model
    assert model is not None
    wrong = []
    for entity in model.entities:
        for column in entity.columns:
            if column.data_type == "COMPUTED":  # declares no type; its expression is held
                assert column.source_data_type is None
                continue
            if column.source_data_type is None or not _declared_verbatim(text, column.name, column.source_data_type):
                wrong.append((entity.entity_name, column.name, column.source_data_type))
    assert wrong == []


def test_the_documentation_derived_snowflake_fixture_fails_by_name_and_is_unreconciled() -> None:
    result = _import("snowflake", "ledger_schema")
    assert result.status == "unreconciled"
    assert [f["head"] for f in result.report["failures"]] == ["create or replace HYBRID TABLE ACCOUNTS"]
    assert "opaque Command" in result.report["failures"][0]["reason"]
    gap = result.report["reconciliation"]["gaps"]
    assert [(g["table"], g["kind"], g["source"], g["imported"]) for g in gap] == [("ACCOUNTS", "table", 1, 0)]
    manifest = _manifest("snowflake", "ledger_schema")
    assert result.report["reconciliation"]["source"]["tables"]["count"] == manifest["counts"]["tables"]
