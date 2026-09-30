"""Which numeric columns the semantic exports sum, and which they do not (Sprint 9 Step 5a.1).

Two rules, one per defect found in Step 4:

* **Money is numeric.** The exporters decided "numeric" from a list of
  substrings that did not include SQL Server's `money`, so an amount was
  written as a label: a categorical dimension in MetricFlow, a `string` in
  Cube, and no measure in LookML. They now read the shared type family
  (`app.schemas.data_model.type_family`).
* **Codes are not summed.** Keys, foreign keys, and integers that read as
  codes (permissible values, a CHECK allowing few values, a name such as
  `Status` or `RevisionNumber`) are dimensions, and every such choice is listed
  in the export's `EXPORT_NOTES.md`.

The evidence is AdventureWorks' SalesOrderHeader with OrderDate as its time
column. Negative controls: with money taken out of the numeric family,
SubTotal is categorical again; with the code rule taken out, Status is summed
again; each makes the check fail.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

from app.schemas import data_model
from app.schemas.data_model import (
    CheckConstraintSchema,
    ColumnSchema,
    EntitySchema,
    SynthesizedModel,
)
from app.services import exporter_service
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService

DDL = Path(__file__).parent / "fixtures" / "ddl"
MONEY = ("SubTotal", "TaxAmt", "Freight")
CODES = ("Status", "RevisionNumber")


@pytest.fixture(scope="module")
def adventureworks() -> SynthesizedModel:
    model = import_ddl((DDL / "tsql" / "adventureworks.sql").read_bytes(), "tsql", "adventureworks.sql").model
    header = next(e for e in model.entities if e.entity_name == "SalesOrderHeader")
    header.agg_time_column = "OrderDate"  # confirmed by a person, as Step 4 lets them
    return model


def _metricflow(model: SynthesizedModel) -> tuple[dict, str]:
    files = ExporterService().export_semantic_layer(model, "metricflow")
    document = yaml.safe_load(files["semantic_models.yml"])
    # MetricFlow names are lower snake case; each expr is the column's own name.
    header = next(m for m in document["semantic_models"] if m["name"] == "sales_order_header")
    return header, files.get("EXPORT_NOTES.md", "")


def _check_metricflow(model: SynthesizedModel) -> None:
    """The owner's evidence, on MetricFlow."""
    header, notes = _metricflow(model)
    measures = {m["expr"]: m["agg"] for m in header.get("measures", [])}
    dimensions = {d["expr"]: d["type"] for d in header.get("dimensions", [])}
    for column in MONEY:
        assert measures.get(column) == "sum", f"{column} is not a sum measure: measures {measures}"
    for column in CODES:
        assert column not in measures, f"{column} is summed"
        assert dimensions.get(column) == "categorical", f"{column} is not a dimension"
        assert f"SalesOrderHeader.{column} (TINYINT): not summed as a measure" in notes, f"{column} not in the notes"


def _cube(model: SynthesizedModel) -> tuple[str, str]:
    exporter = ExporterService()
    files = exporter.export_semantic_layer(model, "cube")
    return files[f"schema/{exporter._to_pascal_case('SalesOrderHeader')}.js"], files.get("EXPORT_NOTES.md", "")


def _cube_measures(block: str) -> dict[str, str]:
    """{column: aggregation} for every measure over a column."""
    return {column: agg for column, agg in re.findall(r"sql: `(\w+)`,\n\s+type: `(sum|avg|min|max|count)`", block)}


def _check_cube(model: SynthesizedModel) -> None:
    block, notes = _cube(model)
    measures = _cube_measures(block)
    for column in MONEY:
        assert measures.get(column) == "sum", f"{column} is not a sum measure in Cube: {measures}"
        assert re.search(rf"sql: `{column}`,\n\s+type: `number`", block), f"{column} is not a number dimension"
    for column in CODES:
        assert column not in measures, f"{column} is summed in Cube"
        assert f"SalesOrderHeader.{column} (TINYINT): not summed as a measure" in notes


def test_money_amounts_are_sum_measures_and_codes_are_dimensions_in_metricflow(adventureworks) -> None:
    _check_metricflow(adventureworks)


def test_money_amounts_are_sum_measures_and_codes_are_dimensions_in_cube(adventureworks) -> None:
    _check_cube(adventureworks)


def test_lookml_sums_the_amounts_and_not_the_codes_or_keys(adventureworks) -> None:
    files = ExporterService().export_semantic_layer(adventureworks, "lookml")
    view = files["SalesOrderHeader.view.lkml"]
    summed = set(re.findall(r"measure: total_(\w+)", view))
    assert summed == set(MONEY), f"LookML sums {sorted(summed)}"
    assert "SalesOrderHeader.Status (TINYINT)" in files["EXPORT_NOTES.md"]


def test_the_metricflow_file_points_to_its_notes(adventureworks) -> None:
    files = ExporterService().export_semantic_layer(adventureworks, "metricflow")
    lines = files["semantic_models.yml"].splitlines()
    header = lines[:next(i for i, line in enumerate(lines) if not line.startswith("#"))]
    assert any(re.fullmatch(r"# Export notes \(\d+\): columns written as dimensions rather than summed, or "
                            r"renamed; see EXPORT_NOTES\.md\.", line) for line in header), header[-3:]


def test_the_cube_export_route_carries_the_notes_too(adventureworks) -> None:
    assert "EXPORT_NOTES.md" in ExporterService().export(adventureworks, "cube")


# --- the negative controls ----------------------------------------------------


def test_negative_control_without_money_in_the_numeric_family_subtotal_is_categorical_again(
        adventureworks, monkeypatch: pytest.MonkeyPatch) -> None:
    real = data_model.type_family
    monkeypatch.setattr(exporter_service, "type_family",
                        lambda t: "other" if "MONEY" in t.upper() else real(t))
    header, _ = _metricflow(adventureworks)
    assert {"name": "sub_total", "type": "categorical", "expr": "SubTotal"} in header["dimensions"]
    with pytest.raises(AssertionError, match="SubTotal is not a sum measure"):
        _check_metricflow(adventureworks)
    with pytest.raises(AssertionError, match="SubTotal is not a sum measure in Cube"):
        _check_cube(adventureworks)


def test_negative_control_without_the_code_rule_status_is_summed_again(
        adventureworks, monkeypatch: pytest.MonkeyPatch) -> None:
    real = ExporterService.dimension_reason.__func__  # type: ignore[attr-defined]

    def keys_only(cls, col, entity, model):  # type: ignore[no-untyped-def]
        reason = real(cls, col, entity, model)
        return reason if reason in ("a primary-key column", "a foreign-key column") else None

    monkeypatch.setattr(ExporterService, "dimension_reason", classmethod(keys_only))
    header, _ = _metricflow(adventureworks)
    assert {"name": "total_status", "agg": "sum", "expr": "Status"} in header["measures"]
    with pytest.raises(AssertionError, match="Status is summed"):
        _check_metricflow(adventureworks)
    with pytest.raises(AssertionError, match="Status is summed in Cube"):
        _check_cube(adventureworks)


# --- one name, one kind of element (dbt parse, owner 2026-09-30) ---------------


def _names_of_two_kinds(model: SynthesizedModel) -> set[str]:
    """Names used as an entity in one semantic model and a dimension in another:
    the manifest check `dbt parse` makes once there are measures."""
    document = yaml.safe_load(ExporterService().export_semantic_layer(model, "metricflow")["semantic_models.yml"])
    entities = {e["name"] for sm in document["semantic_models"] for e in sm.get("entities", [])}
    dimensions = {d["name"] for sm in document["semantic_models"] for d in sm.get("dimensions", [])}
    return entities & dimensions


def test_no_name_is_both_an_entity_and_a_dimension(adventureworks) -> None:
    assert _names_of_two_kinds(adventureworks) == set()


def test_a_composite_key_column_named_as_an_entity_elsewhere_is_renamed_and_noted(adventureworks) -> None:
    files = ExporterService().export_semantic_layer(adventureworks, "metricflow")
    document = yaml.safe_load(files["semantic_models.yml"])
    detail = next(sm for sm in document["semantic_models"] if sm["name"] == "sales_order_detail")
    assert {"name": "sales_order_detail_product_id", "type": "categorical", "expr": "ProductID"} \
        in detail["dimensions"]
    assert ("sales_order_detail.ProductID: dimension named 'sales_order_detail_product_id', because 'product_id' "
            "is an entity elsewhere in the semantic model") in files["EXPORT_NOTES.md"]


def test_negative_control_without_the_rename_productid_is_two_kinds_again(
        adventureworks, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ExporterService, "_rename_dimensions_named_as_entities", staticmethod(lambda models: []))
    assert {"product_id", "special_offer_id"} <= _names_of_two_kinds(adventureworks)


def test_every_name_is_one_metricflow_accepts_and_the_notes_say_so(adventureworks) -> None:
    files = ExporterService().export_semantic_layer(adventureworks, "metricflow")
    document = yaml.safe_load(files["semantic_models.yml"])
    names = [sm["name"] for sm in document["semantic_models"]]
    names += [item["name"] for sm in document["semantic_models"] for block in ("entities", "dimensions", "measures")
              for item in sm.get(block, [])]
    names += [m["name"] for m in document.get("metrics", [])]
    refused = [n for n in names if not re.fullmatch(r"[a-z](?!.*__)[a-z0-9_]*[a-z0-9]", n)]
    assert refused == []
    assert "names are written in lower snake case, as MetricFlow requires" in files["EXPORT_NOTES.md"]
    # expr is untouched: the column's own name, as the staging model has it.
    assert {"name": "total_sub_total", "agg": "sum", "expr": "SubTotal"} in _metricflow(adventureworks)[0]["measures"]


def test_a_valid_name_is_left_as_it_is() -> None:
    assert ExporterService._snake("AWBuildVersion") == "aw_build_version"
    entity = EntitySchema(entity_name="order_line", entity_type="TABLE", agg_time_column="shipped_at",
                          columns=[ColumnSchema(name="line_id", data_type="INTEGER", is_primary_key=True),
                                   ColumnSchema(name="address_line2", data_type="TEXT"),
                                   ColumnSchema(name="shipped_at", data_type="DATE")])
    document = yaml.safe_load(ExporterService()._metricflow(SynthesizedModel(paradigm="3NF", entities=[entity])))
    assert "address_line2" in {d["name"] for d in document["semantic_models"][0]["dimensions"]}


# --- the type family ----------------------------------------------------------


@pytest.mark.parametrize(("declared", "family"), [
    ("MONEY", "numeric"), ("SMALLMONEY", "numeric"), ("money", "numeric"),     # SQL Server, PostgreSQL
    ("NUMERIC(19, 4)", "numeric"), ("NUMBER(6,0)", "numeric"), ("TINYINT", "numeric"), ("FLOAT8", "numeric"),
    ("BIT", "boolean"), ("BOOLEAN", "boolean"),
    ("POINT", "other"),                  # holds "INT", and is no number
    # A duration, not a point in time: _is_temporal_type's tokens are points.
    ("INTERVAL", "other"), ("DATETIME2(7)", "temporal"),
    ("NVARCHAR(50)", "text"), ("VARBINARY(MAX)", "binary"),
])
def test_the_type_family_reads_whole_type_names(declared: str, family: str) -> None:
    assert data_model.type_family(declared) == family


@pytest.mark.parametrize(("declared", "integer"), [
    ("TINYINT", True), ("NUMBER(6,0)", True), ("NUMBER(6)", True), ("NUMBER(*,0)", True),
    ("NUMERIC(19, 4)", False), ("MONEY", False), ("NUMBER", False), ("FLOAT", False),
])
def test_an_integer_type_holds_whole_numbers_only(declared: str, integer: bool) -> None:
    assert data_model.is_integer_type(declared) is integer


# --- the code rule, case by case ---------------------------------------------


def _entity(column: ColumnSchema, check: str | None = None) -> EntitySchema:
    return EntitySchema(
        entity_name="t", entity_type="TABLE",
        columns=[ColumnSchema(name="row_id", data_type="INTEGER", is_primary_key=True), column],
        check_constraints=[CheckConstraintSchema(expression=check, columns=[column.name])] if check else [])


@pytest.mark.parametrize(("column", "check", "reason"), [
    (ColumnSchema(name="quantity", data_type="SMALLINT", permissible_values=["1", "2"]), None, "permissible values"),
    (ColumnSchema(name="quantity", data_type="INTEGER"), "quantity IN (1, 2, 3)", "CHECK allows few values"),
    (ColumnSchema(name="quantity", data_type="INTEGER"), "quantity BETWEEN 0 AND 5", "CHECK allows few values"),
    (ColumnSchema(name="OrderStatus", data_type="TINYINT"), None, "name reads as a code ('status')"),
    (ColumnSchema(name="EmployeeNumber", data_type="INTEGER"), None, "name reads as an identifier ('number')"),
    (ColumnSchema(name="quantity", data_type="INTEGER"), None, None),                      # a real quantity
    (ColumnSchema(name="quantity", data_type="INTEGER"), "quantity >= 0", None),           # open-ended
    (ColumnSchema(name="quantity", data_type="INTEGER"), "quantity BETWEEN 0 AND 1000", None),
    (ColumnSchema(name="StatusRate", data_type="NUMERIC(5, 2)"), None, None),              # not an integer
    (ColumnSchema(name="OrderStatus", data_type="TINYINT", is_metric=True), None, None),   # a person said metric
])
def test_the_code_rule(column: ColumnSchema, check: str | None, reason: str | None) -> None:
    entity = _entity(column, check)
    model = SynthesizedModel(paradigm="3NF", entities=[entity])
    found = ExporterService.dimension_reason(entity.columns[1], entity, model)
    assert (found is None) if reason is None else (found is not None and reason in found), found


def test_a_key_is_never_summed_even_when_declared_a_metric() -> None:
    entity = _entity(ColumnSchema(name="x", data_type="INTEGER"))
    key = copy.deepcopy(entity.columns[0])
    key.is_metric = True
    assert ExporterService.dimension_reason(key, entity, SynthesizedModel(paradigm="3NF", entities=[entity])) \
        == "a primary-key column"
