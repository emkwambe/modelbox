"""Introspection reads physical constraints truthfully (Task 3, H4).

A brownfield model must carry what the warehouse actually says. The hazard runs
both ways: marking a column nullable when the source declares NOT NULL is a
lost constraint, and marking one unique or non-nullable when the source never
said so is a **fabricated** constraint that Sprint 3 will export into a data
contract as fact.

``build_graph`` is a pure function of the metadata dictionaries, so these run
without a database — which is also the point: they test the mapping, not the
driver.
"""

from __future__ import annotations

import pytest

from app.services.introspection import IntrospectionService, _as_default, _as_nullable


def _columns(*specs: dict[str, object]) -> list[dict[str, object]]:
    out = []
    for index, spec in enumerate(specs, start=1):
        out.append({"table": "t", "ordinal": index, "data_type": "text", **spec})
    return out


def _graph(columns, **kw):
    return IntrospectionService.build_graph(
        ["t"], columns, set(), [], **kw
    ).entities[0]


# ---------------------------------------------------------------------------
# Nullability
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ("NO", False), ("no", False), ("N", False), (False, False),
        ("YES", True), ("yes", True), (True, True),
        (None, True),  # the engine did not say -> SQL default
    ],
)
def test_nullability_normalisation(reported: object, expected: bool) -> None:
    assert _as_nullable(reported) is expected


def test_not_null_from_the_source_is_preserved() -> None:
    entity = _graph(_columns(
        {"column": "required", "is_nullable": "NO"},
        {"column": "optional", "is_nullable": "YES"},
    ))
    by_name = {c.name: c for c in entity.columns}
    assert by_name["required"].is_nullable is False
    assert by_name["optional"].is_nullable is True


def test_an_engine_that_says_nothing_yields_the_sql_default() -> None:
    """Absent is not the same as NOT NULL. Never invent a constraint."""
    entity = _graph(_columns({"column": "unknown"}))
    assert entity.columns[0].is_nullable is True


def test_a_primary_key_is_non_nullable_even_if_the_source_omits_it() -> None:
    model = IntrospectionService.build_graph(
        ["t"],
        _columns({"column": "id", "data_type": "integer"}),
        {("t", "id")},
        [],
    )
    assert model.entities[0].columns[0].is_nullable is False


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        ("nextval('t_id_seq'::regclass)", "nextval('t_id_seq'::regclass)"),
        ("'pending'::text", "'pending'::text"),
        ("  0  ", "0"),
        (None, None),
        ("", None),
        ("NULL", None),  # the engine's way of saying "no default"
    ],
)
def test_default_normalisation(reported: object, expected: str | None) -> None:
    assert _as_default(reported) == expected


def test_default_is_carried_onto_the_column() -> None:
    entity = _graph(_columns({"column": "status", "default": "'pending'::text"}))
    assert entity.columns[0].default_value == "'pending'::text"


# ---------------------------------------------------------------------------
# Uniqueness and checks — present only where the catalogue supports them
# ---------------------------------------------------------------------------
def test_unique_and_check_are_applied_where_reported() -> None:
    entity = _graph(
        _columns({"column": "email"}, {"column": "age", "data_type": "integer"}),
        unique_columns={("t", "email")},
        check_expressions={("t", "age"): "age >= 0"},
    )
    by_name = {c.name: c for c in entity.columns}
    assert by_name["email"].is_unique is True
    assert by_name["age"].check_expression == "age >= 0"
    assert by_name["age"].is_unique is False
    assert by_name["email"].check_expression is None


def test_an_engine_without_a_constraint_catalogue_claims_nothing() -> None:
    """BigQuery has no UNIQUE or CHECK. The model must not invent them.

    `is_unique` is False here because the concept does not exist in the source,
    which is a truthful answer rather than an assumed one; `check_expression`
    stays None because "unknown" and "none" are distinguishable for it.
    """
    entity = _graph(_columns({"column": "a"}, {"column": "b"}))
    assert all(c.is_unique is False for c in entity.columns)
    assert all(c.check_expression is None for c in entity.columns)


def test_constraints_do_not_leak_between_tables() -> None:
    model = IntrospectionService.build_graph(
        ["orders", "customers"],
        [
            {"table": "orders", "column": "email", "data_type": "text", "ordinal": 1},
            {"table": "customers", "column": "email", "data_type": "text", "ordinal": 1},
        ],
        set(),
        [],
        unique_columns={("customers", "email")},
    )
    by_entity = {e.entity_name: e for e in model.entities}
    assert by_entity["customers"].columns[0].is_unique is True
    assert by_entity["orders"].columns[0].is_unique is False, (
        "a constraint was attributed to the wrong table"
    )


def test_existing_introspection_behaviour_is_unchanged() -> None:
    """Type mapping, key flags and FK topology still work as before."""
    model = IntrospectionService.build_graph(
        ["orders", "customers"],
        [
            {"table": "orders", "column": "id", "data_type": "integer", "ordinal": 1},
            {"table": "orders", "column": "customer_id", "data_type": "integer",
             "ordinal": 2},
            {"table": "customers", "column": "id", "data_type": "integer",
             "ordinal": 1},
        ],
        {("orders", "id"), ("customers", "id")},
        [{"from_table": "orders", "from_column": "customer_id",
          "to_table": "customers", "to_column": "id"}],
    )
    orders = next(e for e in model.entities if e.entity_name == "orders")
    assert orders.columns[0].data_type == "INT"
    assert orders.columns[0].is_primary_key is True
    assert orders.columns[1].is_foreign_key is True
    assert model.relationships[0].cardinality == "N:1"


# ---------------------------------------------------------------------------
# references — the column-level FK target (M6)
# ---------------------------------------------------------------------------
def test_foreign_key_columns_carry_a_qualified_reference() -> None:
    """`references` records the FK target on the column, not only as an edge.

    The relationship list already describes the edge. ODCS v3.1.0's
    property-level `foreignKey` needs it on the property, which is why M6 was
    ruled "wire it" rather than "delete it" (correction C3).
    """
    model = IntrospectionService.build_graph(
        ["orders", "customers"],
        [
            {"table": "orders", "column": "id", "data_type": "integer", "ordinal": 1},
            {"table": "orders", "column": "buyer_id", "data_type": "integer",
             "ordinal": 2},
            {"table": "customers", "column": "id", "data_type": "integer",
             "ordinal": 1},
        ],
        {("orders", "id"), ("customers", "id")},
        [{"from_table": "orders", "from_column": "buyer_id",
          "to_table": "customers", "to_column": "id"}],
    )
    orders = next(e for e in model.entities if e.entity_name == "orders")
    by_name = {c.name: c for c in orders.columns}
    assert by_name["buyer_id"].references == "customers.id"
    assert by_name["id"].references is None, "a primary key is not a reference"

    customers = next(e for e in model.entities if e.entity_name == "customers")
    assert customers.columns[0].references is None, (
        "the referenced column must not claim a reference of its own"
    )


def test_reference_target_names_the_parent_column_not_the_local_one() -> None:
    """Role-playing FKs point at the parent's column, whatever they are called."""
    model = IntrospectionService.build_graph(
        ["shipments", "customers"],
        [
            {"table": "shipments", "column": "ship_to_id", "data_type": "integer",
             "ordinal": 1},
            {"table": "shipments", "column": "bill_to_id", "data_type": "integer",
             "ordinal": 2},
            {"table": "customers", "column": "customer_id", "data_type": "integer",
             "ordinal": 1},
        ],
        {("customers", "customer_id")},
        [
            {"from_table": "shipments", "from_column": "ship_to_id",
             "to_table": "customers", "to_column": "customer_id"},
            {"from_table": "shipments", "from_column": "bill_to_id",
             "to_table": "customers", "to_column": "customer_id"},
        ],
    )
    shipments = next(e for e in model.entities if e.entity_name == "shipments")
    assert [c.references for c in shipments.columns] == [
        "customers.customer_id",
        "customers.customer_id",
    ]

