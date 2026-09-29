"""Keys the MetricFlow semantic model cannot state are named gaps (Sprint 8 Step 6, A2).

A MetricFlow entity is one expression and has one type, so a composite
foreign key is no join, a composite primary key no primary entity, and a
one-column key that is also a foreign key cannot carry its join. Each was left
out of the semantic model without a word; now each is an export gap, listed
by relationship or table, at the head of ``semantic_models.yml`` and in
``EXPORT_GAPS.md``.

Evidence on genuine imports: every composite foreign key and composite
primary key of AdventureWorks and Oracle HR is named (HR has no composite
foreign key; its JOB_HISTORY key is composite). Negative control: with the
gap emission removed, the same assertions fail.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import yaml

from app.schemas.data_model import SynthesizedModel
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
IMPORTS = [("oracle", "hr"), ("tsql", "adventureworks")]


def _imported(dialect: str, stem: str) -> SynthesizedModel:
    result = import_ddl((FIXTURES / "ddl" / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert result.model is not None
    return result.model


def _synthetic() -> SynthesizedModel:
    raw = json.loads((FIXTURES / "synthetic" / "composite_keys.json").read_text(encoding="utf-8"))
    return SynthesizedModel.model_validate({k: raw[k] for k in ("paradigm", "entities", "relationships")})


def _files(model: SynthesizedModel) -> dict[str, str]:
    return ExporterService().export_semantic_layer(model, "metricflow")


def _expected(model: SynthesizedModel) -> list[str]:
    """What must be named, read off the model: every composite FK and composite PK."""
    composite_fks = [f"{r.from_ref}({', '.join(r.from_columns)}) -> {r.to_ref}({', '.join(r.to_columns)})"
                     for r in model.relationships if len(r.from_columns) > 1]
    composite_pks = [f"{e.entity_name}({', '.join(e.primary_key)})" for e in model.entities
                     if len(e.primary_key) > 1]
    return composite_fks + composite_pks


def _check(files: dict[str, str], expected: list[str]) -> None:
    head = files["semantic_models.yml"].split("semantic_models:")[0]
    listed = files.get("EXPORT_GAPS.md", "")
    missing = [key for key in expected if key not in head or key not in listed]
    assert not missing, f"not named as gaps: {missing}"


@pytest.mark.parametrize(("dialect", "stem"), IMPORTS, ids=[s for _, s in IMPORTS])
def test_every_composite_key_of_a_genuine_import_is_a_named_gap(dialect: str, stem: str) -> None:
    model = _imported(dialect, stem)
    expected = _expected(model)
    assert expected, "fixture sanity: the model has composite keys"
    _check(_files(model), expected)


def test_the_counts_are_the_imports() -> None:
    """HR: no composite FK, one composite PK; AdventureWorks: one composite FK."""
    hr = _imported("oracle", "hr")
    aw = _imported("tsql", "adventureworks")
    assert [e.entity_name for e in hr.entities if len(e.primary_key) > 1] == ["JOB_HISTORY"]
    assert not [r for r in hr.relationships if len(r.from_columns) > 1]
    assert [(r.from_ref, r.to_ref) for r in aw.relationships if len(r.from_columns) > 1] == [
        ("SalesOrderDetail", "SpecialOfferProduct")]


@pytest.mark.parametrize(("dialect", "stem"), IMPORTS, ids=[s for _, s in IMPORTS])
def test_negative_control_without_the_gaps_the_check_fails(dialect: str, stem: str,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    model = _imported(dialect, stem)
    monkeypatch.setattr(ExporterService, "metricflow_export_gaps", staticmethod(lambda _model: []))
    with pytest.raises(AssertionError, match="not named as gaps"):
        _check(_files(model), _expected(model))


def test_a_composite_key_is_a_primary_entity_and_its_foreign_key_a_join() -> None:
    doc = yaml.safe_load(_files(_synthetic())["semantic_models.yml"])
    by_name = {m["name"]: m for m in doc["semantic_models"]}
    line = by_name["order_line"]
    assert line["primary_entity"] == "order_line"
    assert [e["type"] for e in line["entities"]].count("primary") == 0, "no primary entity per key column"
    foreign = {e["expr"]: e["name"] for e in line["entities"] if e["type"] == "foreign"}
    assert foreign == {"order_id": "order_id", "product_id": "product_id"}, \
        "a key column that is a one-column foreign key keeps its join"
    assert {"name": "line_no", "type": "categorical", "expr": "line_no"} in line["dimensions"]
    assert not line.get("measures"), "a key column is never summed"


def test_the_synthetic_model_names_each_kind_of_gap() -> None:
    gaps = ExporterService.metricflow_export_gaps(_synthetic())
    one_expression = "a MetricFlow entity is one expression"
    assert gaps == [
        ("order_line(promo_id, product_id) -> promotion_product(promo_id, product_id): composite foreign key; "
         f"{one_expression}, so this join is not in the semantic model"),
        ("product_detail.product_id -> product: the primary key is also a foreign key; an entity has one type, "
         "so it is the primary entity and this join is not in the semantic model"),
        (f"promotion_product(promo_id, product_id): composite primary key; {one_expression}, so the semantic "
         "model declares primary_entity 'promotion_product' and nothing joins to it by this key"),
        (f"order_line(order_id, line_no): composite primary key; {one_expression}, so the semantic model "
         "declares primary_entity 'order_line' and nothing joins to it by this key"),
    ]


def test_a_model_with_no_such_key_has_no_gap_file() -> None:
    model = SynthesizedModel.model_validate({"paradigm": "3NF", "entities": [
        {"entity_name": "t", "columns": [{"name": "id", "data_type": "INTEGER"}], "primary_key": ["id"]}]})
    files = _files(model)
    assert "EXPORT_GAPS.md" not in files and not files["semantic_models.yml"].startswith("# Export gaps")
