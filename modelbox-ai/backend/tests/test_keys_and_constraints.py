"""Keys and constraints have one source, and a saved model reopens exactly as saved.

Sprint 8 Step 3 (owner decisions): an entity's primary key, UNIQUE and CHECK
constraints are lists on the entity, and a relationship carries its column
lists; the column flags are derived from those. This file holds:

* the IR's rules — lists derive flags, flags alone (the older form) build the
  lists, and a payload that states both and disagrees is refused;
* save and reopen through the real persistence path, compared as the **whole
  graph** (every entity, column, constraint and relationship, in order), with
  negative controls that break each part of the storage;
* a provider response that omits ``entity_type``, round-tripped;
* what storage holds, read by raw SQL rather than through the ORM.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.metadata_store import Base, DataModel, Workspace
from app.schemas.data_model import (
    GraphUpdateRequest,
    RelationshipSchema,
    SynthesizedModel,
    SynthesizeRequest,
)
from app.services.graph_repository import GraphRepository
from app.services.synthesis_engine import SynthesisEngine
from tests._test_db import make_test_engine

# A graph using everything the representation holds, in the new form.
GRAPH: dict[str, Any] = {
    "entities": [
        {"entity_name": "orders", "entity_type": "FACT",
         "columns": [{"name": "order_id", "data_type": "INTEGER"},
                     {"name": "region", "data_type": "VARCHAR(8)"},
                     {"name": "placed_at", "data_type": "TIMESTAMP"}],
         "primary_key": ["order_id", "region"],
         "unique_constraints": [{"name": "uq_orders_placed", "columns": ["placed_at", "region"]}],
         "check_constraints": [{"name": "ck_region", "expression": "region IN ('EU', 'US')",
                                "columns": ["region"]}]},
        {"entity_name": "order_line", "entity_type": "TABLE",
         "columns": [{"name": "order_id", "data_type": "INTEGER"},
                     {"name": "region", "data_type": "VARCHAR(8)"},
                     {"name": "line_no", "data_type": "INTEGER"},
                     {"name": "qty", "data_type": "INTEGER", "description": "Units."},
                     {"name": "max_qty", "data_type": "INTEGER"}],
         "primary_key": ["order_id", "region", "line_no"],
         "check_constraints": [{"expression": "qty > 0", "columns": ["qty"]},
                               {"name": "ck_qty_cap", "expression": "qty <= max_qty",
                                "columns": ["qty", "max_qty"]}]},
        {"entity_name": "audit_note", "entity_type": "TABLE",
         "columns": [{"name": "note_id", "data_type": "INTEGER"}], "primary_key": ["note_id"]},
    ],
    "relationships": [
        {"from": "order_line", "from_columns": ["order_id", "region"], "to": "orders",
         "to_columns": ["order_id", "region"], "name": "fk_line_order", "cardinality": "N:1"},
        # Drawn before columns could be chosen: kept, unresolved.
        {"from": "audit_note", "to": "orders", "cardinality": "N:1"},
    ],
}


def _graph() -> GraphUpdateRequest:
    return GraphUpdateRequest.model_validate(json.loads(json.dumps(GRAPH)))


# --- The IR ------------------------------------------------------------------------

def test_the_lists_derive_the_column_flags() -> None:
    line = _graph().entities[1]
    flags = {c.name: (c.is_primary_key, c.is_nullable, c.check_expression, c.is_foreign_key, c.references)
             for c in line.columns}
    assert flags == {
        "order_id": (True, False, None, True, "orders.order_id"),
        "region": (True, False, None, True, "orders.region"),
        "line_no": (True, False, None, False, None),
        "qty": (False, True, "qty > 0", False, None),
        "max_qty": (False, True, None, False, None),
    }


def test_the_older_form_builds_the_lists_from_the_flags() -> None:
    model = SynthesizedModel.model_validate({
        "paradigm": "3NF",
        "entities": [
            {"entity_name": "a", "columns": [
                {"name": "id", "data_type": "INT", "is_primary_key": True},
                {"name": "email", "data_type": "TEXT", "is_unique": True, "check_expression": "email LIKE '%@%'"},
                {"name": "b_id", "data_type": "INT", "references": "b.id"}]},
            {"entity_name": "b", "columns": [{"name": "id", "data_type": "INT", "is_primary_key": True}]},
        ],
        "relationships": [],
    })
    a = model.entities[0]
    assert a.primary_key == ["id"]
    assert [u.columns for u in a.unique_constraints] == [["email"]]
    assert [(k.expression, k.columns) for k in a.check_constraints] == [("email LIKE '%@%'", ["email"])]
    # An older-form reference is the relationship it describes.
    assert [(r.from_ref, r.from_columns, r.to_ref, r.to_columns) for r in model.relationships] == [
        ("a", ["b_id"], "b", ["id"])]


@pytest.mark.parametrize(("where", "flag", "value"), [
    (("entities", 1, "columns", 4), "is_primary_key", True),
    (("entities", 0, "columns", 2), "is_unique", True),
    (("entities", 1, "columns", 3), "check_expression", "qty > 1"),
    (("entities", 1, "columns", 2), "is_foreign_key", True),
    (("entities", 1, "columns", 0), "references", "orders.region"),
])
def test_a_flag_that_contradicts_the_lists_is_refused(where: tuple[Any, ...], flag: str, value: object) -> None:
    payload = json.loads(json.dumps(GRAPH))
    target = payload
    for step in where:
        target = target[step]
    target[flag] = value
    with pytest.raises(ValidationError, match="contradicts"):
        GraphUpdateRequest.model_validate(payload)


def test_negative_control_an_agreeing_flag_is_accepted() -> None:
    payload = json.loads(json.dumps(GRAPH))
    payload["entities"][1]["columns"][2]["is_primary_key"] = True
    payload["entities"][1]["columns"][0]["references"] = "orders.order_id"
    GraphUpdateRequest.model_validate(payload)


def test_a_relationship_nested_in_a_model_keeps_its_older_form() -> None:
    """Pydantic re-runs a nested model's after-validator when an instance is
    placed in a parent. A dotted ref split on the first run must not look like
    stated column lists on the second, or an older-form payload would be held
    to the newer form's contradiction rule. Found building this step."""
    rel = RelationshipSchema.model_validate({"from": "a.b_id", "to": "b.id", "cardinality": "N:1"})
    model = SynthesizedModel.model_validate({
        "paradigm": "3NF",
        "entities": [{"entity_name": "a", "columns": [{"name": "b_id", "data_type": "INT",
                                                        "is_foreign_key": False}]},
                     {"entity_name": "b", "columns": [{"name": "id", "data_type": "INT"}]}],
        "relationships": [rel],
    })
    assert model.relationships[0]._stated_no_columns is True
    assert model.entities[0].columns[0].is_foreign_key is True


def test_mismatched_column_lists_are_refused() -> None:
    with pytest.raises(ValidationError, match="referencing columns"):
        RelationshipSchema.model_validate({"from": "a", "from_columns": ["x", "y"], "to": "b",
                                           "to_columns": ["x"], "cardinality": "N:1"})


# --- Save and reopen --------------------------------------------------------------

@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def _new_model(session: AsyncSession) -> DataModel:
    workspace = Workspace(name="keys")
    session.add(workspace)
    await session.flush()
    row = DataModel(workspace_id=workspace.workspace_id, title="keys", target_dialect="postgres")
    session.add(row)
    await session.flush()
    return row


async def _save_and_reopen(session: AsyncSession, graph: GraphUpdateRequest) -> dict[str, Any]:
    row = await _new_model(session)
    await GraphRepository(session).replace_graph(row.model_id, graph.entities, graph.relationships)
    await session.commit()
    reopened = await SynthesisEngine(session, None).get_model(row.model_id)  # type: ignore[arg-type]
    assert reopened is not None
    return _whole(GraphUpdateRequest(entities=reopened.entities, relationships=reopened.relationships))


def _whole(graph: GraphUpdateRequest) -> dict[str, Any]:
    """The whole graph, minus the one server-assigned field (stable_id)."""
    dumped = graph.model_dump(by_alias=True)
    for entity in dumped["entities"]:
        for column in entity["columns"]:
            column.pop("stable_id")
            column.pop("ordinal_position")
    return dumped


async def test_a_saved_model_reopens_exactly_as_saved(session: AsyncSession) -> None:
    graph = _graph()
    assert await _save_and_reopen(session, graph) == _whole(graph)


async def test_saving_what_was_reopened_changes_nothing(session: AsyncSession) -> None:
    row = await _new_model(session)
    engine = SynthesisEngine(session, None)  # type: ignore[arg-type]
    await GraphRepository(session).replace_graph(row.model_id, _graph().entities, _graph().relationships)
    first = await engine.get_model(row.model_id)
    assert first is not None
    # As the canvas would send it: the JSON the server returned, flags and all.
    echoed = GraphUpdateRequest.model_validate(json.loads(first.model_dump_json(by_alias=True)))
    await GraphRepository(session).replace_graph(row.model_id, echoed.entities, echoed.relationships)
    second = await engine.get_model(row.model_id)
    assert second is not None
    assert second.model_dump(by_alias=True)["entities"] == first.model_dump(by_alias=True)["entities"]
    assert second.relationships == first.relationships


async def test_negative_control_without_constraint_storage_the_graph_differs(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(self: Any, entity_row: Any, entity: Any) -> None:
        return None
    monkeypatch.setattr(GraphRepository, "_persist_constraints", nothing)
    assert await _save_and_reopen(session, _graph()) != _whole(_graph())


async def test_negative_control_without_column_pair_storage_the_graph_differs(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GraphRepository, "_persist_pairs", lambda self, rel_row, rel: None)
    assert await _save_and_reopen(session, _graph()) != _whole(_graph())


async def test_the_saved_order_is_what_reopens(session: AsyncSession) -> None:
    """The fixture's entities are not in name order, so the reload's name
    tie-break alone could not reproduce them; and the comparison sees order."""
    names = [e["entity_name"] for e in GRAPH["entities"]]
    assert names != sorted(names), "fixture sanity: saved order must differ from name order"
    reordered = _graph()
    reordered.entities.reverse()
    assert _whole(reordered) != _whole(_graph()), "the comparison must be order-sensitive"
    assert await _save_and_reopen(session, reordered) == _whole(reordered)


async def test_storage_holds_the_lists_by_raw_sql(session: AsyncSession) -> None:
    row = await _new_model(session)
    graph = _graph()
    await GraphRepository(session).replace_graph(row.model_id, graph.entities, graph.relationships)
    await session.commit()
    constraints = (await session.execute(text(
        "SELECT e.entity_name, k.kind, k.name, k.expression, "
        "(SELECT group_concat(m.column_name, ',') FROM (SELECT column_name FROM entity_constraint_columns "
        " WHERE constraint_id = k.constraint_id ORDER BY position) m) AS cols "
        "FROM entity_constraints k JOIN model_entities e ON e.entity_id = k.entity_id "
        "ORDER BY e.position, k.position"))).all()
    assert [tuple(r) for r in constraints] == [
        ("orders", "PRIMARY KEY", None, None, "order_id,region"),
        ("orders", "UNIQUE", "uq_orders_placed", None, "placed_at,region"),
        ("orders", "CHECK", "ck_region", "region IN ('EU', 'US')", "region"),
        ("order_line", "PRIMARY KEY", None, None, "order_id,region,line_no"),
        ("order_line", "CHECK", None, "qty > 0", "qty"),
        ("order_line", "CHECK", "ck_qty_cap", "qty <= max_qty", "qty,max_qty"),
        ("audit_note", "PRIMARY KEY", None, None, "note_id"),
    ]
    pairs = (await session.execute(text(
        "SELECT r.name, p.position, p.from_column_name, p.to_column_name FROM entity_relationships r "
        "LEFT JOIN relationship_columns p ON p.relationship_id = r.relationship_id "
        "ORDER BY r.position, p.position"))).all()
    assert [tuple(r) for r in pairs] == [
        ("fk_line_order", 0, "order_id", "order_id"),
        ("fk_line_order", 1, "region", "region"),
        (None, None, None, None),  # the unresolved relationship: kept, with no pairs
    ]


# --- entity_type omitted by a provider ------------------------------------------

class _Provider:
    """A gateway that returns the provider's JSON, parsed as the real one parses it."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def structured_completion(self, task: str, prompt: str, response_model: type[Any], **_: Any) -> Any:
        return response_model.model_validate(self._payload)


async def test_a_provider_response_without_entity_type_saves_and_reopens(session: AsyncSession) -> None:
    payload = {
        "paradigm": "3NF",
        "entities": [
            {"entity_name": "customer", "columns": [
                {"name": "customer_id", "data_type": "INTEGER", "is_primary_key": True}]},
            {"entity_name": "invoice", "columns": [
                {"name": "invoice_id", "data_type": "INTEGER", "is_primary_key": True},
                {"name": "customer_id", "data_type": "INTEGER"}]},
        ],
        "relationships": [{"from": "invoice.customer_id", "to": "customer.customer_id", "cardinality": "N:1"}],
    }
    assert all("entity_type" not in e for e in payload["entities"]), "fixture sanity"
    workspace = Workspace(name="provider")
    session.add(workspace)
    await session.flush()
    engine = SynthesisEngine(session, _Provider(payload))  # type: ignore[arg-type]
    created = await engine.synthesize(SynthesizeRequest(
        source_type="natural_language", content="billing", target_paradigm="3NF",  # type: ignore[arg-type]
        dialect="postgres", workspace_id=workspace.workspace_id))
    reopened = await engine.get_model(created.model_id)
    assert reopened is not None
    assert [(e.entity_name, e.entity_type) for e in reopened.entities] == [("customer", "TABLE"), ("invoice", "TABLE")]
    expected = SynthesizedModel.model_validate(payload)
    assert _whole(GraphUpdateRequest(entities=reopened.entities, relationships=reopened.relationships)) == \
        _whole(GraphUpdateRequest(entities=expected.entities, relationships=expected.relationships))
