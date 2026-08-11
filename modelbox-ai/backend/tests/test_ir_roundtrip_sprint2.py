"""Round-trip proofs for the Sprint 2 IR fields (Task 9, register C1 and C3).

Every field added this sprint must survive save → reload with no loss, and
``stable_id`` must additionally hold two properties that nothing else enforces:

* **immutable across a reorder** — a canvas drag moves ``ordinal_position``,
  never identity;
* **never reused after a delete** — the property the whole design exists for.

The no-reuse proof is written against the sequence a plausible-but-wrong
implementation passes right up until the last step: delete the *highest*
column, save, add a new one, save. An implementation deriving ids as
``max(existing) + 1`` looks correct through every earlier assertion and hands
the deleted id straight to the new column — reissuing a Protobuf field tag that
a deployed consumer still associates with the old field, which is exactly
finding H6.

These run on SQLite through the existing async fixtures rather than against
Postgres: the properties under test are allocation logic, not database
behaviour, so they gate every push instead of one job. The migration's backfill
*is* database behaviour and is verified separately against real Postgres in
``test_migration_0013_populated.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.metadata_store import Base, DataModel, ModelEntity, Workspace
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)
from app.services.graph_repository import GraphRepository
from app.services.synthesis_engine import SynthesisEngine


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def model_id(session: AsyncSession) -> uuid.UUID:
    workspace = Workspace(name="roundtrip")
    session.add(workspace)
    await session.flush()
    row = DataModel(
        workspace_id=workspace.workspace_id,
        title="roundtrip",
        current_paradigm="KIMBALL",
        target_dialect="postgres",
    )
    session.add(row)
    await session.flush()
    return row.model_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def col(name: str, data_type: str = "VARCHAR(64)", **kw: object) -> ColumnSchema:
    return ColumnSchema(name=name, data_type=data_type, **kw)  # type: ignore[arg-type]


def entity(name: str, columns: list[ColumnSchema], **kw: object) -> EntitySchema:
    return EntitySchema(
        entity_name=name, entity_type="TABLE", columns=columns, **kw  # type: ignore[arg-type]
    )


async def save(
    session: AsyncSession,
    model_id: uuid.UUID,
    entities: list[EntitySchema],
    relationships: list[RelationshipSchema] | None = None,
) -> None:
    await GraphRepository(session).replace_graph(
        model_id, entities, relationships or []
    )


async def reload(session: AsyncSession, model_id: uuid.UUID) -> SynthesizedModel:
    response = await SynthesisEngine(session, None).get_model(model_id)
    assert response is not None
    return SynthesizedModel(
        paradigm=response.paradigm,
        entities=response.entities,
        relationships=response.relationships,
    )


def ids_by_name(model: SynthesizedModel, entity_name: str) -> dict[str, int]:
    target = next(e for e in model.entities if e.entity_name == entity_name)
    return {c.name: c.stable_id for c in target.columns}  # type: ignore[misc]


async def watermark(session: AsyncSession, model_id: uuid.UUID, name: str) -> int:
    """Read the high-water mark directly, not through the IR.

    Register verification standard: checking allocation through the layer that
    performs it would let a mapping bug satisfy the assertion.
    """
    row = (
        await session.execute(
            select(ModelEntity).where(
                ModelEntity.model_id == model_id, ModelEntity.entity_name == name
            )
        )
    ).scalar_one()
    return row.next_stable_id


# ---------------------------------------------------------------------------
# stable_id — identity
# ---------------------------------------------------------------------------
async def test_stable_ids_are_allocated_from_one(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    await save(session, model_id, [entity("t", [col("a"), col("b"), col("c")])])
    assert ids_by_name(await reload(session, model_id), "t") == {"a": 1, "b": 2, "c": 3}
    assert await watermark(session, model_id, "t") == 4


async def test_stable_id_is_immutable_across_reorder(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """A canvas drag moves ordinal_position; identity must not follow it."""
    await save(session, model_id, [entity("t", [col("a"), col("b"), col("c")])])
    before = ids_by_name(await reload(session, model_id), "t")

    reloaded = await reload(session, model_id)
    reversed_columns = list(reversed(reloaded.entities[0].columns))
    for position, column in enumerate(reversed_columns):
        column.ordinal_position = position
    await save(session, model_id, [entity("t", reversed_columns)])

    after_model = await reload(session, model_id)
    assert ids_by_name(after_model, "t") == before, "reorder changed stable_id"
    assert [c.name for c in after_model.entities[0].columns] == ["c", "b", "a"], (
        "the reorder itself did not persist"
    )


async def test_stable_id_survives_a_rename(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """Renaming a column keeps its identity — the basis of Sprint 4's C4."""
    await save(session, model_id, [entity("t", [col("a"), col("b")])])
    reloaded = await reload(session, model_id)
    original = ids_by_name(reloaded, "t")

    renamed = reloaded.entities[0].columns
    renamed[0].name = "a_renamed"
    await save(session, model_id, [entity("t", renamed)])

    after = ids_by_name(await reload(session, model_id), "t")
    assert after == {"a_renamed": original["a"], "b": original["b"]}


# ---------------------------------------------------------------------------
# stable_id — the property the design exists for
# ---------------------------------------------------------------------------
async def test_stable_id_is_never_reused_after_delete(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """Deleting the highest column must not free its id for the next one.

    An implementation deriving ids as ``max(existing) + 1`` passes every
    assertion above and fails here — the new column inherits the deleted id and
    a deployed Protobuf consumer misparses the field. That is finding H6.
    """
    await save(session, model_id, [entity("t", [col("a"), col("b"), col("c")])])
    original = ids_by_name(await reload(session, model_id), "t")
    highest_id = original["c"]
    assert highest_id == max(original.values())

    # Delete the highest column and save.
    keep = [c for c in (await reload(session, model_id)).entities[0].columns
            if c.name != "c"]
    await save(session, model_id, [entity("t", keep)])
    assert "c" not in ids_by_name(await reload(session, model_id), "t")
    assert await watermark(session, model_id, "t") == highest_id + 1, (
        "the watermark moved backwards when a column was deleted"
    )

    # Add a new column and save.
    survivors = (await reload(session, model_id)).entities[0].columns
    await save(session, model_id, [entity("t", [*survivors, col("d")])])

    after = ids_by_name(await reload(session, model_id), "t")
    assert after["d"] != highest_id, (
        f"new column 'd' inherited the deleted column's id ({highest_id}) — "
        f"a deployed consumer would misparse it as 'c'. This is H6."
    )
    assert after["d"] == highest_id + 1
    assert after["a"] == original["a"] and after["b"] == original["b"]


async def test_dropping_and_recreating_an_entity_restarts_ids(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """The documented edge case, asserted rather than left implicit.

    An entity's watermark lives on its row, so dropping the entity discards it
    and a recreated entity of the same name starts again at 1. That is correct:
    a dropped and recreated table is a new Protobuf message, and pretending its
    field tags continue would be the wrong kind of stability. Asserted here so
    the behaviour is a decision on the record rather than an accident.
    """
    await save(session, model_id, [entity("t", [col("a"), col("b"), col("c")])])
    assert await watermark(session, model_id, "t") == 4

    # Drop the entity entirely (a save that no longer mentions it).
    await save(session, model_id, [entity("other", [col("x")])])

    # Recreate it under the same name.
    await save(
        session,
        model_id,
        [entity("other", [col("x")]), entity("t", [col("a"), col("b")])],
    )
    assert ids_by_name(await reload(session, model_id), "t") == {"a": 1, "b": 2}
    assert await watermark(session, model_id, "t") == 3


async def test_client_cannot_invent_a_stable_id(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """The server allocates; a payload cannot claim an id above the watermark."""
    await save(session, model_id, [entity("t", [col("a")])])
    await save(
        session,
        model_id,
        [entity("t", [col("a", stable_id=1), col("forged", stable_id=9_999)])],
    )
    after = ids_by_name(await reload(session, model_id), "t")
    assert after["forged"] == 2, "a client-supplied future id was honoured"
    assert await watermark(session, model_id, "t") == 3


# ---------------------------------------------------------------------------
# Constraint fields, references, agg_time_column
# ---------------------------------------------------------------------------
async def test_is_nullable_defaults_true_and_is_forced_false_on_primary_keys(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    await save(
        session,
        model_id,
        [entity("t", [col("id", "INTEGER", is_primary_key=True), col("plain")])],
    )
    columns = {c.name: c for c in (await reload(session, model_id)).entities[0].columns}
    assert columns["id"].is_nullable is False, "a primary key cannot be nullable"
    assert columns["plain"].is_nullable is True, "the SQL default must be preserved"


async def test_every_new_field_survives_a_full_round_trip(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """Register C1: a model with every new field set reloads with zero loss."""
    original = entity(
        "fact_orders",
        [
            col("order_sk", "INTEGER", is_primary_key=True),
            col(
                "customer_sk",
                "INTEGER",
                is_foreign_key=True,
                references="dim_customer.customer_sk",
                is_nullable=False,
            ),
            col(
                "email",
                "VARCHAR(255)",
                is_pii=True,
                pii_type="EMAIL",
                is_unique=True,
                default_value="'unknown@example.com'",
                check_expression="email LIKE '%@%'",
                description="Contact address.",
            ),
            col("amount", "NUMERIC(18,2)", is_metric=True, aggregation="sum",
                min_value=0.0, max_value=1_000_000.0),
            col("ordered_at", "TIMESTAMP"),
        ],
        grain="One row per order.",
        agg_time_column="ordered_at",
    )
    await save(session, model_id, [original])

    reloaded = (await reload(session, model_id)).entities[0]
    assert reloaded.agg_time_column == "ordered_at"
    assert reloaded.grain == "One row per order."

    by_name = {c.name: c for c in reloaded.columns}
    assert by_name["customer_sk"].references == "dim_customer.customer_sk"
    assert by_name["customer_sk"].is_nullable is False
    assert by_name["email"].is_unique is True
    assert by_name["email"].default_value == "'unknown@example.com'"
    assert by_name["email"].check_expression == "email LIKE '%@%'"
    assert by_name["amount"].min_value == 0.0
    assert by_name["amount"].max_value == 1_000_000.0
    assert all(c.stable_id is not None for c in reloaded.columns)

    # Idempotence: saving what was just read back must change nothing.
    await save(session, model_id, [reloaded])
    again = (await reload(session, model_id)).entities[0]
    assert again.model_dump() == reloaded.model_dump(), (
        "a save-reload cycle is not idempotent"
    )


async def test_agg_time_column_must_name_a_temporal_column_on_the_entity(
    session: AsyncSession, model_id: uuid.UUID
) -> None:
    """Invalid semantic models are rejected at the IR, not inside dbt parse."""
    with pytest.raises(ValueError, match="not a column of entity"):
        entity("t", [col("a")], agg_time_column="missing")
    with pytest.raises(ValueError, match="not a date or time type"):
        entity("t", [col("a", "INTEGER")], agg_time_column="a")
