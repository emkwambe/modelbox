"""Tests for the schema diff engine + /model/diff endpoint (FR-2.2).

Pure-unit coverage of DiffEngine plus one ASGI integration test that diffs two
persisted models over an in-memory SQLite session with a mocked gateway.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.models.metadata_store import Base, User, Workspace, WorkspaceMember
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SuggestedMetric,
    SynthesizedModel,
    SynthesizeRequest,
)
from app.services.diff_engine import DiffEngine
from app.services.synthesis_engine import SynthesisEngine


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _col(
    name: str,
    dtype: str = "VARCHAR(64)",
    *,
    pk: bool = False,
    metric: bool = False,
    agg: str | None = None,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type=dtype,
        is_primary_key=pk,
        is_metric=metric,
        aggregation=agg,
    )


def _entity(name: str, cols: list[ColumnSchema], etype: str = "TABLE") -> EntitySchema:
    return EntitySchema(entity_name=name, entity_type=etype, columns=cols)  # type: ignore[arg-type]


def _rel(from_ref: str, to_ref: str, cardinality: str = "N:1") -> RelationshipSchema:
    return RelationshipSchema.model_validate(
        {"from": from_ref, "to": to_ref, "cardinality": cardinality}
    )


def _model(
    entities: list[EntitySchema],
    rels: list[RelationshipSchema] | None = None,
    metrics: list[SuggestedMetric] | None = None,
) -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=entities,
        relationships=rels or [],
        suggested_metrics=metrics or [],
    )


def _identified(entity: EntitySchema, start: int = 1) -> EntitySchema:
    """Assign stable_ids the way persistence does — one per column, in order.

    Rename detection is only possible on a model that has been saved, because
    `stable_id` is allocated by the repository. A model straight from synthesis
    carries None on every column and must fall back to matching by name.
    """
    return entity.model_copy(
        update={
            "columns": [
                col.model_copy(update={"stable_id": start + i})
                for i, col in enumerate(entity.columns)
            ]
        }
    )


def _joined(statements: list[str]) -> str:
    return "\n".join(statements).upper()


# ---------------------------------------------------------------------------
# Identity, relationships and keys — C4, C5, M2
# ---------------------------------------------------------------------------
def test_renamed_column_is_a_rename_not_a_drop_and_add() -> None:
    """A renamed column must preserve its data.

    Asserted as the property rather than the keyword. An implementation that
    emits RENAME *in addition to* the existing DROP and ADD satisfies "output
    contains RENAME" while still destroying the column — and that is precisely
    the smallest change that makes a keyword assertion pass.
    """
    src = _model([_identified(_entity("a", [_col("id", pk=True), _col("cust_email")]))])
    tgt = _model(
        [_identified(_entity("a", [_col("id", pk=True), _col("customer_email")]))]
    )
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    joined = _joined(statements)

    assert "RENAME COLUMN CUST_EMAIL TO CUSTOMER_EMAIL" in joined
    assert "DROP COLUMN CUST_EMAIL" not in joined, "the rename must replace the drop"
    assert "ADD COLUMN CUSTOMER_EMAIL" not in joined, "no re-add; the data stays"
    assert not any("Dropped column" in b for b in breaking), breaking


def test_rename_is_not_inferred_without_identity() -> None:
    """An unsaved model has no identities, so the same edit is a drop and an add.

    The discriminating half of C4. An implementation that pairs columns by
    position, or that treats two None identities as equal, passes the rename
    test above and then reports renames that never happened on every model the
    user has not saved yet.
    """
    src = _model([_entity("a", [_col("id", pk=True), _col("cust_email")])])
    tgt = _model([_entity("a", [_col("id", pk=True), _col("customer_email")])])
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    joined = _joined(statements)

    assert "RENAME COLUMN" not in joined, "a rename was inferred from nothing"
    assert "DROP COLUMN CUST_EMAIL" in joined
    assert any("Dropped column" in b for b in breaking), breaking


def test_removed_foreign_key_is_a_breaking_change() -> None:
    """Dropping an FK relaxes a guarantee downstream consumers rely on."""
    entities = [
        _entity("dim_customer", [_col("customer_id", "INT", pk=True)]),
        _entity(
            "fact_orders",
            [_col("order_id", "INT", pk=True), _col("customer_id", "INT")],
        ),
    ]
    src = _model(
        entities, [_rel("fact_orders.customer_id", "dim_customer.customer_id")]
    )
    tgt = _model(entities, [])
    _, breaking, _ = DiffEngine().diff(src, tgt)
    assert any(
        "fact_orders.customer_id" in b and "dim_customer.customer_id" in b
        for b in breaking
    ), f"FK removal reported nothing: {breaking}"


def test_added_foreign_key_is_not_breaking() -> None:
    """The discriminating half of C5: tightening a constraint is not a break.

    Without this, an implementation that reports every relationship difference
    passes the removal test while crying wolf on every added join.
    """
    entities = [
        _entity("dim_customer", [_col("customer_id", "INT", pk=True)]),
        _entity(
            "fact_orders",
            [_col("order_id", "INT", pk=True), _col("customer_id", "INT")],
        ),
    ]
    src = _model(entities, [])
    tgt = _model(
        entities, [_rel("fact_orders.customer_id", "dim_customer.customer_id")]
    )
    _, breaking, _ = DiffEngine().diff(src, tgt)
    assert not any("customer_id" in b for b in breaking), breaking


def test_changed_primary_key_is_a_breaking_change() -> None:
    """Re-keying a table invalidates every foreign key pointing at it."""
    src = _model(
        [
            _identified(
                _entity("a", [_col("old_key", "INT", pk=True), _col("new_key", "INT")])
            )
        ]
    )
    tgt = _model(
        [
            _identified(
                _entity("a", [_col("old_key", "INT"), _col("new_key", "INT", pk=True)])
            )
        ]
    )
    _, breaking, _ = DiffEngine().diff(src, tgt)
    assert any("primary key" in b.lower() for b in breaking), (
        f"the table was re-keyed and the diff said nothing: {breaking}"
    )


def test_renaming_the_primary_key_column_is_not_a_key_change() -> None:
    """The key still sits on the same column; only its name moved.

    Added because a mutant survived without it. `_key_breaks` compares the PK
    as a set of names, so renaming the PK column reads as "old_key left the key,
    new_key joined it" unless the rename is applied first — and reporting that
    would make every rename destructive again through a second door, after C4
    had just stopped it being destructive through the first.
    """
    src = _model([_identified(_entity("a", [_col("cust_id", "INT", pk=True)]))])
    tgt = _model([_identified(_entity("a", [_col("customer_id", "INT", pk=True)]))])
    statements, breaking, _ = DiffEngine().diff(src, tgt)

    assert "RENAME COLUMN CUST_ID TO CUSTOMER_ID" in _joined(statements)
    assert not any("primary key" in b.lower() for b in breaking), breaking


# ---------------------------------------------------------------------------
# Unit: DiffEngine (pure)
# ---------------------------------------------------------------------------
def test_no_changes_yields_empty_diff() -> None:
    model = _model([_entity("a", [_col("id", pk=True), _col("name")])])
    statements, breaking, _ = DiffEngine().diff(model, model)
    assert statements == []
    assert breaking == []


def test_added_column_emits_add_and_is_non_breaking() -> None:
    src = _model([_entity("a", [_col("id", pk=True), _col("name")])])
    tgt = _model([_entity("a", [_col("id", pk=True), _col("name"), _col("email")])])
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    joined = _joined(statements)
    assert "ADD COLUMN EMAIL" in joined
    assert breaking == []


def test_dropped_column_is_breaking() -> None:
    src = _model([_entity("a", [_col("id", pk=True), _col("email")])])
    tgt = _model([_entity("a", [_col("id", pk=True)])])
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    assert "DROP COLUMN EMAIL" in _joined(statements)
    assert "Dropped column: a.email" in breaking


def test_added_entity_creates_table_non_breaking() -> None:
    src = _model([_entity("a", [_col("id", pk=True)])])
    tgt = _model(
        [_entity("a", [_col("id", pk=True)]), _entity("b", [_col("id", pk=True)])]
    )
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    joined = _joined(statements)
    assert "CREATE TABLE B" in joined
    assert breaking == []


def test_dropped_entity_is_breaking_and_cascades() -> None:
    src = _model(
        [_entity("a", [_col("id", pk=True)]), _entity("b", [_col("id", pk=True)])]
    )
    tgt = _model([_entity("a", [_col("id", pk=True)])])
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    joined = _joined(statements)
    assert "DROP TABLE B CASCADE" in joined
    assert "Dropped table: b" in breaking


def test_type_change_is_breaking() -> None:
    src = _model([_entity("a", [_col("id", "VARCHAR(64)", pk=True)])])
    tgt = _model([_entity("a", [_col("id", "INT", pk=True)])])
    statements, breaking, _ = DiffEngine().diff(src, tgt)
    joined = _joined(statements)
    assert "TYPE INT" in joined
    assert any("Type change: a.id" in b for b in breaking)


def test_statements_are_terminated() -> None:
    src = _model([_entity("a", [_col("id", pk=True), _col("name")])])
    tgt = _model([_entity("a", [_col("id", pk=True), _col("name"), _col("email")])])
    statements, _, _ = DiffEngine().diff(src, tgt)
    assert statements and all(s.strip().endswith(";") for s in statements)


def test_unknown_dialect_falls_back_to_postgres() -> None:
    src = _model([_entity("a", [_col("id", pk=True)])])
    tgt = _model([_entity("a", [_col("id", pk=True)]), _entity("b", [_col("id", pk=True)])])
    # A bogus dialect must not raise — DiffEngine defaults to postgres.
    statements, _, _ = DiffEngine("klingon").diff(src, tgt)
    assert "CREATE TABLE B" in _joined(statements)


# ---------------------------------------------------------------------------
# Semantic breaks (Sprint 3)
# ---------------------------------------------------------------------------
def test_semantic_break_on_dropped_measure() -> None:
    src = _model(
        [_entity("fact", [_col("id", pk=True), _col("amount", "NUMERIC", metric=True, agg="SUM")])]
    )
    tgt = _model([_entity("fact", [_col("id", pk=True)])])  # measure dropped
    _, breaking, semantic = DiffEngine().diff(src, tgt)
    assert any("Dropped column: fact.amount" in b for b in breaking)
    assert any(
        "declared measure" in s and "fact.amount" in s for s in semantic
    )


def test_semantic_break_on_measure_type_change() -> None:
    src = _model(
        [_entity("fact", [_col("id", pk=True), _col("amount", "NUMERIC(12,2)", metric=True)])]
    )
    tgt = _model(
        [_entity("fact", [_col("id", pk=True), _col("amount", "INT", metric=True)])]
    )
    _, _, semantic = DiffEngine().diff(src, tgt)
    assert any("type-changed" in s and "fact.amount" in s for s in semantic)


def test_semantic_break_on_metric_formula_reference() -> None:
    src = _model(
        [_entity("fact_orders", [_col("id", pk=True), _col("total", "NUMERIC")])],
        metrics=[SuggestedMetric(name="Revenue", formula="SUM(fact_orders.total)")],
    )
    tgt = _model([_entity("fact_orders", [_col("id", pk=True)])])  # 'total' dropped
    _, _, semantic = DiffEngine().diff(src, tgt)
    assert any("referenced by metric 'Revenue'" in s for s in semantic)


def test_no_semantic_break_on_safe_change() -> None:
    src = _model([_entity("fact", [_col("id", pk=True), _col("amount", "NUMERIC", metric=True)])])
    tgt = _model(
        [_entity("fact", [_col("id", pk=True), _col("amount", "NUMERIC", metric=True), _col("note")])]
    )
    _, _, semantic = DiffEngine().diff(src, tgt)
    assert semantic == []  # adding a column doesn't break a measure


# ---------------------------------------------------------------------------
# Integration: POST /api/v1/model/diff
# ---------------------------------------------------------------------------
class _StubGateway:
    def __init__(self, model: SynthesizedModel) -> None:
        self._model = model

    async def structured_completion(
        self, task: str, prompt: str, response_model: type[Any], **_: Any
    ) -> SynthesizedModel:
        return self._model


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def _seed_user_workspace(
    session: AsyncSession, email: str
) -> tuple[User, uuid.UUID]:
    user = User(email=email, hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()
    workspace = Workspace(name=f"{email} workspace")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id, user_id=user.user_id, role="OWNER"
        )
    )
    await session.flush()
    return user, workspace.workspace_id


async def _persist(
    session: AsyncSession, workspace_id: uuid.UUID, model: SynthesizedModel
) -> str:
    resp = await SynthesisEngine(session, _StubGateway(model)).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="model",
            target_paradigm="3NF",  # type: ignore[arg-type]
            dialect="postgres",
            workspace_id=workspace_id,
        )
    )
    return str(resp.model_id)


async def test_diff_endpoint_reports_migration_and_breaking(
    session: AsyncSession,
) -> None:
    from app.api.v1.dependencies import get_current_user, get_synthesis_engine
    from app.core.database import get_db_session
    from app.main import create_app

    user, workspace_id = await _seed_user_workspace(session, "owner@example.com")

    v1 = _model(
        [
            _entity("dim_customer", [_col("customer_hk", pk=True), _col("email")]),
            _entity(
                "fact_orders",
                [_col("order_id", pk=True), _col("customer_hk")],
            ),
            _entity("legacy_log", [_col("log_id", pk=True)]),
        ],
        [_rel("fact_orders.customer_hk", "dim_customer.customer_hk")],
    )
    v2 = _model(
        [
            _entity(
                "dim_customer",
                [_col("customer_hk", pk=True), _col("email"), _col("phone")],
            ),
            _entity(
                "fact_orders",
                [_col("order_id", pk=True), _col("customer_hk"), _col("amount")],
            ),
            _entity("audit", [_col("audit_id", pk=True)]),
        ],
        [_rel("fact_orders.customer_hk", "dim_customer.customer_hk")],
    )

    source_id = await _persist(session, workspace_id, v1)
    target_id = await _persist(session, workspace_id, v2)

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_synthesis_engine] = lambda: SynthesisEngine(
        session, _StubGateway(v1)
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/model/diff",
            json={
                "source_model_id": source_id,
                "target_model_id": target_id,
                "dialect": "postgres",
            },
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    joined = "\n".join(body["alter_statements"]).upper()
    assert "DROP TABLE LEGACY_LOG CASCADE" in joined
    assert "CREATE TABLE AUDIT" in joined
    assert "ADD COLUMN PHONE" in joined
    assert "ADD COLUMN AMOUNT" in joined
    assert "Dropped table: legacy_log" in body["breaking_changes"]
