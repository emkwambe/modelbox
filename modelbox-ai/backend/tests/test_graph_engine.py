"""Unit tests for the pure NetworkX graph engine.

No Postgres/Redis/LLM dependencies — exercises GraphEngine in isolation against
the QA test matrix (TRD §2.5): topological ordering, cyclic-FK detection, and
structural lint diagnostics.
"""

from __future__ import annotations

import pytest

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
)
from app.services.graph_engine import GraphEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def col(
    name: str,
    *,
    pk: bool = False,
    fk: bool = False,
    pii: bool = False,
    desc: str | None = "documented",
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type="VARCHAR(64)",
        is_primary_key=pk,
        is_foreign_key=fk,
        is_pii=pii,
        description=desc,
    )


def entity(
    name: str,
    columns: list[ColumnSchema],
    entity_type: str = "TABLE",
    *,
    desc: str | None = "documented",
    grain: str | None = None,
) -> EntitySchema:
    return EntitySchema(
        entity_name=name,
        entity_type=entity_type,  # type: ignore[arg-type]
        columns=columns,
        description=desc,
        grain=grain,
    )


def rel(from_ref: str, to_ref: str, cardinality: str = "1:N") -> RelationshipSchema:
    return RelationshipSchema.model_validate(
        {"from": from_ref, "to": to_ref, "cardinality": cardinality}
    )


@pytest.fixture()
def engine() -> GraphEngine:
    return GraphEngine()


# ---------------------------------------------------------------------------
# TS-01 — Topological sorting & dependency-layer ordering
# ---------------------------------------------------------------------------
def test_topological_layers(engine: GraphEngine) -> None:
    """A clean chain (line_item -> order -> customer) orders parents first."""
    entities = [
        entity("customer", [col("id", pk=True)]),
        entity("order", [col("id", pk=True), col("customer_id", fk=True)]),
        entity("line_item", [col("id", pk=True), col("order_id", fk=True)]),
    ]
    relationships = [
        rel("order.customer_id", "customer.id"),
        rel("line_item.order_id", "order.id"),
    ]
    graph = engine.build_graph(entities, relationships)

    # No cycles in a clean chain.
    assert engine.detect_cycles(graph) == []

    order = engine.topological_order(graph)
    assert order.index("customer") < order.index("order")
    assert order.index("order") < order.index("line_item")

    layers = engine.dependency_layers(graph)
    assert layers == [["customer"], ["order"], ["line_item"]]


# ---------------------------------------------------------------------------
# TS-02 — Circular foreign-key detection
# ---------------------------------------------------------------------------
def test_cyclic_fk_detection(engine: GraphEngine) -> None:
    """A ↔ B mutual references are flagged as a cycle and invalidate the model."""
    entities = [
        entity("a", [col("id", pk=True), col("b_id", fk=True)]),
        entity("b", [col("id", pk=True), col("a_id", fk=True)]),
    ]
    relationships = [
        rel("a.b_id", "b.id"),
        rel("b.a_id", "a.id"),
    ]
    graph = engine.build_graph(entities, relationships)

    cycles = engine.detect_cycles(graph)
    assert len(cycles) >= 1
    assert {"a", "b"}.issubset({node for cycle in cycles for node in cycle})

    report = engine.validate(entities, relationships)
    assert report.is_valid is False
    assert any(issue.code == "CYCLIC_FK" for issue in report.issues)


# ---------------------------------------------------------------------------
# TS-03 — Missing primary key & dangling reference lints
# ---------------------------------------------------------------------------
def test_lint_diagnostics(engine: GraphEngine) -> None:
    """Missing PK -> warning; dangling relationship -> error (invalid model)."""
    entities = [
        entity("orders", [col("order_id")]),  # no PK
    ]
    relationships = [
        rel("orders.customer_id", "customer.id"),  # 'customer' does not exist
    ]
    report = engine.validate(entities, relationships)

    codes = {issue.code for issue in report.issues}
    assert "MISSING_PK" in codes
    assert "DANGLING_REF" in codes

    missing_pk = next(i for i in report.issues if i.code == "MISSING_PK")
    assert missing_pk.severity == "warning"

    dangling = next(i for i in report.issues if i.code == "DANGLING_REF")
    assert dangling.severity == "error"
    # Source metadata pinpoints the offending FK column for canvas marking.
    assert dangling.entity_name == "orders"
    assert dangling.column_name == "customer_id"

    # A dangling reference is an error, so the overall model is invalid.
    assert report.is_valid is False


def test_valid_model_passes(engine: GraphEngine) -> None:
    """A well-formed model with PKs and resolvable refs validates clean."""
    entities = [
        entity("customer", [col("id", pk=True)]),
        entity("order", [col("id", pk=True), col("customer_id", fk=True)]),
    ]
    relationships = [rel("order.customer_id", "customer.id")]
    report = engine.validate(entities, relationships)

    assert report.is_valid is True
    assert report.issues == []


# ---------------------------------------------------------------------------
# Governance lint pack (Pick 1) — NAMING / GRAIN / DESCRIPTION / PII / ORPHAN
# ---------------------------------------------------------------------------
def _codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def test_naming_convention_non_snake_case(engine: GraphEngine) -> None:
    report = engine.validate([entity("Orders", [col("id", pk=True)])], [])
    assert "NAMING_CONVENTION" in _codes(report)


def test_naming_convention_missing_type_prefix(engine: GraphEngine) -> None:
    # A FACT entity should be prefixed 'fact_'.
    report = engine.validate(
        [entity("sales", [col("sale_id", pk=True)], "FACT", grain="per sale")], []
    )
    assert any(
        i.code == "NAMING_CONVENTION" and "prefix" in i.message for i in report.issues
    )


def test_naming_convention_bad_pk_suffix(engine: GraphEngine) -> None:
    report = engine.validate(
        [entity("dim_customer", [col("customer", pk=True)], "DIMENSION")], []
    )
    assert any(
        i.code == "NAMING_CONVENTION" and i.column_name == "customer"
        for i in report.issues
    )


def test_naming_convention_clean(engine: GraphEngine) -> None:
    report = engine.validate(
        [entity("dim_customer", [col("customer_sk", pk=True)], "DIMENSION")], []
    )
    assert "NAMING_CONVENTION" not in _codes(report)


def test_missing_grain_on_fact(engine: GraphEngine) -> None:
    report = engine.validate(
        [entity("fact_orders", [col("order_id", pk=True)], "FACT")], []
    )
    assert "MISSING_GRAIN" in _codes(report)


def test_grain_present_is_clean(engine: GraphEngine) -> None:
    report = engine.validate(
        [
            entity(
                "fact_orders",
                [col("order_id", pk=True)],
                "FACT",
                grain="one row per order",
            )
        ],
        [],
    )
    assert "MISSING_GRAIN" not in _codes(report)


def test_missing_description_flags_undocumented(engine: GraphEngine) -> None:
    report = engine.validate(
        [
            entity(
                "dim_customer",
                [col("customer_sk", pk=True, desc=None)],
                "DIMENSION",
                desc=None,
            )
        ],
        [],
    )
    # Both the entity and its column are undocumented.
    desc_issues = [i for i in report.issues if i.code == "MISSING_DESCRIPTION"]
    assert len(desc_issues) >= 2


def test_documented_entity_is_clean(engine: GraphEngine) -> None:
    report = engine.validate(
        [entity("dim_customer", [col("customer_sk", pk=True)], "DIMENSION")], []
    )
    assert "MISSING_DESCRIPTION" not in _codes(report)


def test_pii_exposure_untagged(engine: GraphEngine) -> None:
    report = engine.validate(
        [
            entity(
                "dim_customer",
                [col("customer_sk", pk=True), col("email")],
                "DIMENSION",
            )
        ],
        [],
    )
    assert any(
        i.code == "PII_EXPOSURE" and i.column_name == "email" for i in report.issues
    )


def test_pii_exposure_flags_unclassified_ip_address(engine: GraphEngine) -> None:
    report = engine.validate(
        [
            entity(
                "sessions",
                [col("id", pk=True), col("ip_address")],  # not tagged is_pii
            )
        ],
        [],
    )
    assert any(
        i.code == "PII_EXPOSURE" and i.column_name == "ip_address"
        for i in report.issues
    )


def test_pii_exposure_no_false_positive_on_ip_substrings(engine: GraphEngine) -> None:
    # "ip" appears inside zip/shipping/description/recipient — must NOT flag.
    report = engine.validate(
        [
            entity(
                "orders",
                [
                    col("id", pk=True),
                    col("zip_code"),
                    col("shipping_status"),
                    col("description"),
                    col("recipient_count"),
                ],
            )
        ],
        [],
    )
    assert "PII_EXPOSURE" not in _codes(report)


def test_pii_classified_is_clean(engine: GraphEngine) -> None:
    # A correctly classified PII column must NOT be flagged (no false positives).
    report = engine.validate(
        [
            entity(
                "dim_customer",
                [col("customer_sk", pk=True), col("email", pii=True)],
                "DIMENSION",
            )
        ],
        [],
    )
    assert "PII_EXPOSURE" not in _codes(report)


def test_orphan_entity_flagged(engine: GraphEngine) -> None:
    report = engine.validate(
        [
            entity("dim_a", [col("a_sk", pk=True)], "DIMENSION"),
            entity("dim_b", [col("b_sk", pk=True)], "DIMENSION"),
        ],
        [],  # no relationships -> both orphaned
    )
    assert "ORPHAN_ENTITY" in _codes(report)


def test_single_entity_is_not_orphan(engine: GraphEngine) -> None:
    # A one-table model (e.g. OBT) is legitimately relationship-free.
    report = engine.validate([entity("obt_events", [col("event_id", pk=True)])], [])
    assert "ORPHAN_ENTITY" not in _codes(report)


def test_governance_issues_are_warnings_only(engine: GraphEngine) -> None:
    # Multiple governance violations, but none invalidate the model.
    report = engine.validate(
        [entity("Orders", [col("id", pk=True)], "FACT", desc=None)], []
    )
    governance = {"NAMING_CONVENTION", "MISSING_GRAIN", "MISSING_DESCRIPTION"}
    gov_issues = [i for i in report.issues if i.code in governance]
    assert gov_issues
    assert all(i.severity == "warning" for i in gov_issues)
    assert report.is_valid is True
