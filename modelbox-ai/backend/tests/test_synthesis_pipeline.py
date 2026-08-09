"""Async service & router tests for the synthesis pipeline.

Runs against an in-memory SQLite database (portable ORM types) with a mocked
``LLMGateway`` — no live Postgres/Redis and no external API keys. Covers:

* SynthesisEngine.synthesize — linter runs, ORM rows persist, DTO serializes,
* ParadigmTranslator.transform — graph replaced, paradigm + version bumped,
* API routers — POST /synthesize (201) and /transform-paradigm (200) wire
  contracts serialize correctly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.metadata_store import (
    Base,
    DataModel,
    EntityColumn,
    EntityRelationship,
    ModelEntity,
    Workspace,
)
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SuggestedMetric,
    SynthesizedModel,
    SynthesizeRequest,
    TransformParadigmRequest,
)
from app.services.paradigm_translator import ParadigmTranslator
from app.services.synthesis_engine import SynthesisEngine


# ---------------------------------------------------------------------------
# Mock gateway + model builders
# ---------------------------------------------------------------------------
class StubGateway:
    """Stand-in for LLMGateway that returns a canned SynthesizedModel."""

    def __init__(self, model: SynthesizedModel) -> None:
        self._model = model
        self.calls: list[str] = []

    async def structured_completion(
        self,
        task: str,
        prompt: str,
        response_model: type[Any],
        **_: Any,
    ) -> SynthesizedModel:
        self.calls.append(task)
        return self._model


def _col(name: str, *, pk: bool = False, fk: bool = False) -> ColumnSchema:
    return ColumnSchema(
        name=name, data_type="VARCHAR(64)", is_primary_key=pk, is_foreign_key=fk
    )


def _entity(name: str, cols: list[ColumnSchema], etype: str = "TABLE") -> EntitySchema:
    return EntitySchema(entity_name=name, entity_type=etype, columns=cols)  # type: ignore[arg-type]


def _rel(from_ref: str, to_ref: str, cardinality: str = "1:N") -> RelationshipSchema:
    return RelationshipSchema.model_validate(
        {"from": from_ref, "to": to_ref, "cardinality": cardinality}
    )


def kimball_model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=[
            _entity(
                "dim_customer",
                [_col("customer_hk", pk=True), _col("email")],
                "DIMENSION",
            ),
            _entity(
                "fact_orders",
                [_col("order_id", pk=True), _col("customer_hk", fk=True)],
                "FACT",
            ),
        ],
        relationships=[
            _rel("fact_orders.customer_hk", "dim_customer.customer_hk")
        ],
        suggested_metrics=[
            SuggestedMetric(name="Revenue", formula="SUM(fact_orders.total)")
        ],
    )


def threenf_model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity("customer", [_col("id", pk=True), _col("email")]),
            _entity("orders", [_col("id", pk=True), _col("customer_id", fk=True)]),
        ],
        relationships=[_rel("orders.customer_id", "customer.id")],
    )


def cyclic_model() -> SynthesizedModel:
    """A model with a mutual FK cycle and one entity missing a PK."""
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity("a", [_col("id", pk=True), _col("b_id", fk=True)]),
            _entity("b", [_col("b_id_only")]),  # no primary key
        ],
        relationships=[
            _rel("a.b_id", "b.b_id_only"),
            _rel("b.b_id_only", "a.id"),
        ],
    )


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite session + ASGI client
# ---------------------------------------------------------------------------
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


@pytest_asyncio.fixture
async def api_client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.api.v1.dependencies import (
        get_paradigm_translator,
        get_synthesis_engine,
    )
    from app.main import create_app

    app = create_app()
    gateway = StubGateway(kimball_model())
    app.dependency_overrides[get_synthesis_engine] = lambda: SynthesisEngine(
        session, gateway
    )
    app.dependency_overrides[get_paradigm_translator] = lambda: ParadigmTranslator(
        session, gateway
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Service: synthesis
# ---------------------------------------------------------------------------
async def test_synthesize_persists_and_serializes(session: AsyncSession) -> None:
    gateway = StubGateway(kimball_model())
    engine = SynthesisEngine(session, gateway)

    resp = await engine.synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="Track customers and their orders.",
            target_paradigm="KIMBALL",  # type: ignore[arg-type]
            dialect="snowflake",
        )
    )

    # DTO serializes with a real UUID and the expected graph.
    assert isinstance(resp.model_id, uuid.UUID)
    assert resp.paradigm == "KIMBALL"
    assert {e.entity_name for e in resp.entities} == {"dim_customer", "fact_orders"}
    assert len(resp.suggested_metrics) == 1

    # The gateway was invoked for the doc-parsing task.
    assert gateway.calls == ["unstructured_doc_parsing"]

    # ORM rows were populated across all tables.
    entities = (await session.execute(select(ModelEntity))).scalars().all()
    columns = (await session.execute(select(EntityColumn))).scalars().all()
    rels = (await session.execute(select(EntityRelationship))).scalars().all()
    workspaces = (await session.execute(select(Workspace))).scalars().all()

    assert len(entities) == 2
    assert len(columns) == 4
    assert len(rels) == 1
    assert len(workspaces) == 1 and workspaces[0].name == "Default"


# ---------------------------------------------------------------------------
# Service: paradigm transformation
# ---------------------------------------------------------------------------
async def test_paradigm_transform_replaces_and_versions(
    session: AsyncSession,
) -> None:
    # Seed a 3NF model.
    seed = await SynthesisEngine(session, StubGateway(threenf_model())).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="Operational orders database.",
            target_paradigm="3NF",  # type: ignore[arg-type]
            dialect="postgres",
        )
    )
    model_id = seed.model_id

    # Transform 3NF -> Kimball.
    translator = ParadigmTranslator(session, StubGateway(kimball_model()))
    result = await translator.transform(
        model_id, TransformParadigmRequest(target_paradigm="KIMBALL")  # type: ignore[arg-type]
    )

    assert result is not None
    assert result.previous_paradigm == "3NF"
    assert result.new_paradigm == "KIMBALL"
    assert result.generated_entities_count == 2
    assert result.transformation_execution_time_ms >= 0

    # DB reflects the new paradigm, a version bump, and the replaced graph.
    model = await session.get(DataModel, model_id)
    assert model is not None
    assert model.current_paradigm == "KIMBALL"
    assert model.version_number == 2

    names = {
        e.entity_name
        for e in (
            await session.execute(
                select(ModelEntity).where(ModelEntity.model_id == model_id)
            )
        )
        .scalars()
        .all()
    }
    assert names == {"dim_customer", "fact_orders"}


# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------
async def test_synthesize_endpoint_returns_201(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/model/synthesize",
        json={
            "source_type": "natural_language",
            "content": "Track customers and their orders.",
            "target_paradigm": "KIMBALL",
            "dialect": "snowflake",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["paradigm"] == "KIMBALL"
    assert {e["entity_name"] for e in body["entities"]} == {
        "dim_customer",
        "fact_orders",
    }
    # model_id serializes as a UUID string.
    uuid.UUID(body["model_id"])


async def test_transform_endpoint_returns_200(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/model/synthesize",
        json={
            "source_type": "natural_language",
            "content": "Track customers and their orders.",
            "target_paradigm": "KIMBALL",
            "dialect": "snowflake",
        },
    )
    model_id = created.json()["model_id"]

    response = await api_client.post(
        f"/api/v1/model/{model_id}/transform-paradigm",
        json={
            "target_paradigm": "DATA_VAULT",
            "preserve_descriptions": True,
            "options": {
                "hash_key_algorithm": "SHA256",
                "satellite_split_strategy": "BY_UPDATE_FREQUENCY",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == model_id
    assert body["new_paradigm"] == "DATA_VAULT"


async def test_get_missing_model_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/model/{uuid.uuid4()}")
    assert response.status_code == 404


async def _create_model(api_client: AsyncClient) -> str:
    created = await api_client.post(
        "/api/v1/model/synthesize",
        json={
            "source_type": "natural_language",
            "content": "Track customers and their orders.",
            "target_paradigm": "KIMBALL",
            "dialect": "snowflake",
        },
    )
    return created.json()["model_id"]


async def test_export_ddl_endpoint(api_client: AsyncClient) -> None:
    model_id = await _create_model(api_client)
    response = await api_client.get(
        f"/api/v1/model/{model_id}/export",
        params={"format": "ddl", "dialect": "postgres"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "ddl"
    assert body["dialect"] == "postgres"
    (path, content), = body["files"].items()
    assert path.endswith(".sql")
    assert "CREATE TABLE" in content


async def test_export_dbt_endpoint(api_client: AsyncClient) -> None:
    model_id = await _create_model(api_client)
    response = await api_client.get(
        f"/api/v1/model/{model_id}/export", params={"format": "dbt"}
    )
    assert response.status_code == 200
    files = response.json()["files"]
    assert "models/staging/schema.yml" in files
    assert any(p.startswith("models/staging/stg_") for p in files)


async def test_export_cube_endpoint(api_client: AsyncClient) -> None:
    model_id = await _create_model(api_client)
    response = await api_client.get(
        f"/api/v1/model/{model_id}/export", params={"format": "cube"}
    )
    assert response.status_code == 200
    files = response.json()["files"]
    assert any(p.startswith("schema/") and p.endswith(".js") for p in files)


async def test_export_invalid_format_returns_422(api_client: AsyncClient) -> None:
    model_id = await _create_model(api_client)
    response = await api_client.get(
        f"/api/v1/model/{model_id}/export", params={"format": "avro"}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
async def test_synthesize_response_includes_validation(
    session: AsyncSession,
) -> None:
    engine = SynthesisEngine(session, StubGateway(kimball_model()))
    resp = await engine.synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="Track customers and orders.",
            target_paradigm="KIMBALL",  # type: ignore[arg-type]
            dialect="snowflake",
        )
    )
    assert resp.validation is not None
    # A clean Kimball model has no errors.
    assert resp.validation.is_valid is True


async def test_validate_endpoint_flags_cycles_and_missing_pk(
    session: AsyncSession,
) -> None:
    # Persist a broken model (mutual FK cycle + a PK-less entity).
    from app.api.v1.dependencies import get_synthesis_engine
    from app.main import create_app

    seed = await SynthesisEngine(session, StubGateway(cyclic_model())).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="broken",
            target_paradigm="3NF",  # type: ignore[arg-type]
            dialect="postgres",
        )
    )

    app = create_app()
    app.dependency_overrides[get_synthesis_engine] = lambda: SynthesisEngine(
        session, StubGateway(cyclic_model())
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/model/{seed.model_id}/validate"
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    report = response.json()
    assert report["is_valid"] is False
    codes = {issue["code"] for issue in report["issues"]}
    assert "CYCLIC_FK" in codes
    assert "MISSING_PK" in codes


async def test_validate_missing_model_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.post(f"/api/v1/model/{uuid.uuid4()}/validate")
    assert response.status_code == 404
