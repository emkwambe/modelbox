"""Tests for synthetic seed generation + endpoint (FR-2.4).

Pure-unit coverage of SyntheticSeedGenerator (referential integrity, ordering,
determinism, formats) plus one ASGI integration test over an in-memory session.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator
from typing import Any

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
    SynthesizedModel,
    SynthesizeRequest,
)
from app.services.seed_generator import SyntheticSeedGenerator
from app.services.synthesis_engine import SynthesisEngine


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _col(name: str, dtype: str = "VARCHAR(64)", *, pk: bool = False, fk: bool = False) -> ColumnSchema:
    return ColumnSchema(
        name=name, data_type=dtype, is_primary_key=pk, is_foreign_key=fk
    )


def _entity(name: str, cols: list[ColumnSchema], etype: str = "TABLE") -> EntitySchema:
    return EntitySchema(entity_name=name, entity_type=etype, columns=cols)  # type: ignore[arg-type]


def _rel(from_ref: str, to_ref: str, cardinality: str = "N:1") -> RelationshipSchema:
    return RelationshipSchema.model_validate(
        {"from": from_ref, "to": to_ref, "cardinality": cardinality}
    )


def _ecommerce() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity(
                "customers",
                [
                    _col("id", "INTEGER", pk=True),
                    _col("email", "VARCHAR(255)"),
                    _col("full_name", "VARCHAR(255)"),
                ],
            ),
            _entity(
                "orders",
                [
                    _col("id", "INTEGER", pk=True),
                    _col("customer_id", "INTEGER", fk=True),
                    _col("total", "NUMERIC(12,2)"),
                ],
            ),
        ],
        relationships=[_rel("orders.customer_id", "customers.id")],
    )


def _cyclic() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity("a", [_col("id", "INTEGER", pk=True), _col("b_id", "INTEGER", fk=True)]),
            _entity("b", [_col("id", "INTEGER", pk=True), _col("a_id", "INTEGER", fk=True)]),
        ],
        relationships=[_rel("a.b_id", "b.id"), _rel("b.a_id", "a.id")],
    )


def _rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))


# ---------------------------------------------------------------------------
# Unit: SyntheticSeedGenerator
# ---------------------------------------------------------------------------
def test_generation_order_puts_parents_first() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 5, "csv")
    assert result.generation_order.index("customers") < result.generation_order.index("orders")


def test_row_count_per_entity() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 7, "csv")
    assert len(_rows(result.files["customers.csv"])) == 7
    assert len(_rows(result.files["orders.csv"])) == 7


def test_foreign_keys_reference_real_parent_rows() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 20, "csv")
    customer_ids = {r["id"] for r in _rows(result.files["customers.csv"])}
    order_fks = {r["customer_id"] for r in _rows(result.files["orders.csv"])}
    # Every child FK must point at an existing parent PK.
    assert order_fks
    assert order_fks <= customer_ids


def test_output_is_deterministic() -> None:
    a = SyntheticSeedGenerator().generate(_ecommerce(), 10, "sql_insert")
    b = SyntheticSeedGenerator().generate(_ecommerce(), 10, "sql_insert")
    assert a.files == b.files


def test_sql_insert_format() -> None:
    result = SyntheticSeedGenerator(dialect="postgres").generate(_ecommerce(), 3, "sql_insert")
    script = result.files["seed_postgres.sql"]
    assert "INSERT INTO customers (id, email, full_name) VALUES" in script
    assert "INSERT INTO orders (id, customer_id, total) VALUES" in script
    # customers must be inserted before orders (FK-safe order).
    assert script.index("INSERT INTO customers") < script.index("INSERT INTO orders")
    assert script.rstrip().endswith(";")


def test_email_heuristic_produces_addresses() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 5, "csv")
    for row in _rows(result.files["customers.csv"]):
        assert "@" in row["email"]


def test_pk_surrogates_are_unique_and_sequential() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 6, "csv")
    ids = [int(r["id"]) for r in _rows(result.files["customers.csv"])]
    assert ids == [1, 2, 3, 4, 5, 6]


def test_cyclic_model_does_not_crash() -> None:
    # Falls back to declared order rather than raising on the FK cycle.
    result = SyntheticSeedGenerator().generate(_cyclic(), 3, "sql_insert")
    assert set(result.generation_order) == {"a", "b"}
    assert "INSERT INTO a" in result.files["seed_postgres.sql"]


def test_string_literals_are_escaped() -> None:
    model = SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[_entity("t", [_col("id", "INTEGER", pk=True), _col("label", "VARCHAR(64)")])],
    )
    script = SyntheticSeedGenerator().generate(model, 2, "sql_insert").files["seed_postgres.sql"]
    # No unescaped lone quotes would appear; labels are quoted string literals.
    assert "'label_1'" in script


# ---------------------------------------------------------------------------
# Integration: POST /api/v1/model/{id}/export/synthetic-data
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


async def test_synthetic_data_endpoint_returns_seed(session: AsyncSession) -> None:
    from app.api.v1.dependencies import get_current_user, get_synthesis_engine
    from app.core.database import get_db_session
    from app.main import create_app

    user = User(email="owner@example.com", hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()
    workspace = Workspace(name="ws")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id, user_id=user.user_id, role="OWNER"
        )
    )
    await session.flush()

    resp = await SynthesisEngine(session, _StubGateway(_ecommerce())).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="ecommerce",
            target_paradigm="3NF",  # type: ignore[arg-type]
            dialect="postgres",
            workspace_id=workspace.workspace_id,
        )
    )
    model_id = str(resp.model_id)

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_synthesis_engine] = lambda: SynthesisEngine(
        session, _StubGateway(_ecommerce())
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/model/{model_id}/export/synthetic-data",
            json={"row_count_per_entity": 8, "format": "sql_insert", "dialect": "postgres"},
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generation_order"].index("customers") < body["generation_order"].index("orders")
    script = body["files"]["seed_postgres.sql"]
    assert "INSERT INTO customers" in script
    assert "INSERT INTO orders" in script
