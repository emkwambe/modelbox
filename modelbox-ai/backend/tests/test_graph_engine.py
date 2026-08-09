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
def col(name: str, *, pk: bool = False, fk: bool = False) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type="VARCHAR(64)",
        is_primary_key=pk,
        is_foreign_key=fk,
    )


def entity(
    name: str,
    columns: list[ColumnSchema],
    entity_type: str = "TABLE",
) -> EntitySchema:
    return EntitySchema(
        entity_name=name,
        entity_type=entity_type,  # type: ignore[arg-type]
        columns=columns,
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
