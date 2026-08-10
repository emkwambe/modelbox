"""Tests for the Celery worker loop fix + Phase 3 exporters (FR-2.3).

Covers:
* worker per-task engine isolation (consecutive jobs each on their own loop),
* data contracts (OpenDataContract YAML, Avro JSON, Protobuf proto3),
* semantic layers (Cube dispatch, LookML views, MetricFlow YAML),
* the contract/semantic export endpoints.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
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
from app.services.exporter_service import ExporterError, ExporterService
from app.services.synthesis_engine import SynthesisEngine


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _col(name: str, dtype: str, *, pk: bool = False, fk: bool = False, agg: str | None = None) -> ColumnSchema:
    return ColumnSchema(
        name=name, data_type=dtype, is_primary_key=pk, is_foreign_key=fk, aggregation=agg
    )


def _entity(name: str, cols: list[ColumnSchema], etype: str = "TABLE") -> EntitySchema:
    return EntitySchema(entity_name=name, entity_type=etype, columns=cols)  # type: ignore[arg-type]


def _model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity(
                "customers",
                [
                    _col("id", "INTEGER", pk=True),
                    _col("email", "VARCHAR(255)"),
                    _col("created_at", "TIMESTAMP"),
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
        relationships=[
            RelationshipSchema.model_validate(
                {"from": "orders.customer_id", "to": "customers.id", "cardinality": "N:1"}
            )
        ],
    )


# ---------------------------------------------------------------------------
# Worker loop-isolation fix
# ---------------------------------------------------------------------------
def test_worker_processes_consecutive_jobs(monkeypatch) -> None:
    """Two back-to-back jobs must each run on their own loop without crashing.

    The old code reused a process-wide engine bound to the first asyncio loop,
    so job #2 raised 'attached to a different loop'. The fix builds a fresh
    engine per task; here we stub the DB engine + process_job to assert the
    wrapper drives two independent asyncio.run() loops cleanly.
    """
    pytest.importorskip("celery")  # installed in CI; may be absent on dev hosts
    import app.worker as worker

    processed: list[str] = []

    async def _stub_process(session, gateway, job_id) -> None:
        processed.append(str(job_id))

    def _fake_engine(*_a, **_k):
        # A fresh in-memory engine per call — mirrors per-task isolation.
        return create_async_engine(
            "sqlite+aiosqlite://", connect_args={"check_same_thread": False}
        )

    monkeypatch.setattr("app.services.job_service.JobService.process_job", _stub_process)
    monkeypatch.setattr(worker, "get_llm_gateway", lambda: object())
    monkeypatch.setattr(worker, "create_async_engine", _fake_engine)

    id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
    assert worker.run_synthesis_job(id1) == id1
    assert worker.run_synthesis_job(id2) == id2  # would crash under the old shared engine
    assert processed == [id1, id2]


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------
def test_opendatacontract_yaml() -> None:
    files = ExporterService().export_data_contract(_model(), "opendatacontract", "sales")
    doc = yaml.safe_load(files["datacontract.yaml"])
    assert doc["kind"] == "DataContract"
    assert doc["id"] == "sales"
    names = {t["name"] for t in doc["schema"]}
    assert names == {"customers", "orders"}
    customers = next(t for t in doc["schema"] if t["name"] == "customers")
    id_prop = next(p for p in customers["properties"] if p["name"] == "id")
    assert id_prop["primaryKey"] is True and id_prop["required"] is True


def test_avro_schema_types_and_nullability() -> None:
    files = ExporterService().export_data_contract(_model(), "avro", "sales")
    schema = json.loads(files["customers.avsc"])
    assert schema["type"] == "record"
    by_name = {f["name"]: f for f in schema["fields"]}
    assert by_name["id"]["type"] == "int"  # PK is required (not a union)
    assert by_name["email"]["type"] == ["null", "string"]  # nullable union
    # created_at is a non-PK temporal -> nullable union ["null", {logicalType..}].
    assert by_name["created_at"]["type"][1]["logicalType"] == "timestamp-micros"


def test_protobuf_proto3() -> None:
    files = ExporterService().export_data_contract(_model(), "protobuf", "sales")
    proto = files["sales.proto"]
    assert 'syntax = "proto3";' in proto
    assert "message Customers {" in proto
    assert "int32 id = 1;" in proto
    assert "string email = 2;" in proto
    assert "double total = 3;" in proto  # NUMERIC -> double


def test_contract_unknown_format_raises() -> None:
    try:
        ExporterService().export_data_contract(_model(), "parquet", "sales")
    except ExporterError:
        return
    raise AssertionError("expected ExporterError for unknown contract format")


# ---------------------------------------------------------------------------
# Semantic layers
# ---------------------------------------------------------------------------
def test_lookml_view() -> None:
    files = ExporterService().export_semantic_layer(_model(), "lookml")
    view = files["customers.view.lkml"]
    assert "view: customers {" in view
    assert "dimension: id {" in view
    assert "primary_key: yes" in view
    assert "dimension_group: created_at {" in view  # TIMESTAMP -> time group
    assert "measure: count {" in view
    orders = files["orders.view.lkml"]
    assert "measure: total_total {" in orders  # NUMERIC measure


def test_metricflow_yaml() -> None:
    files = ExporterService().export_semantic_layer(_model(), "metricflow")
    doc = yaml.safe_load(files["semantic_models.yml"])
    names = {m["name"] for m in doc["semantic_models"]}
    assert names == {"customers", "orders"}
    customers = next(m for m in doc["semantic_models"] if m["name"] == "customers")
    entity_types = {e["name"]: e["type"] for e in customers["entities"]}
    assert entity_types["id"] == "primary"
    measure_names = {m["name"] for m in customers["measures"]}
    assert "customers_count" in measure_names
    metric_names = {m["name"] for m in doc["metrics"]}
    assert "customers_count" in metric_names


def test_semantic_cube_dispatch_and_unknown_raises() -> None:
    files = ExporterService().export_semantic_layer(_model(), "cube")
    assert any(p.endswith(".js") for p in files)
    try:
        ExporterService().export_semantic_layer(_model(), "superset")
    except ExporterError:
        return
    raise AssertionError("expected ExporterError for unknown semantic engine")


# ---------------------------------------------------------------------------
# Endpoints
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


async def test_contract_and_semantic_endpoints(session: AsyncSession) -> None:
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

    resp = await SynthesisEngine(session, _StubGateway(_model())).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="sales",
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
        session, _StubGateway(_model())
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        c = await client.get(f"/api/v1/model/{model_id}/export/contract?format=avro")
        s = await client.get(f"/api/v1/model/{model_id}/export/semantic?engine=lookml")
    app.dependency_overrides.clear()

    assert c.status_code == 200, c.text
    assert "customers.avsc" in c.json()["files"]
    assert s.status_code == 200, s.text
    assert "customers.view.lkml" in s.json()["files"]
