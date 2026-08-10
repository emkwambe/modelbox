"""Tests for the data dictionary / glossary exporter + endpoint (Pick 2)."""

from __future__ import annotations

import json
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
from app.services.exporter_service import ExporterError, ExporterService
from app.services.synthesis_engine import SynthesisEngine


def _col(
    name: str,
    dtype: str,
    *,
    pk: bool = False,
    fk: bool = False,
    pii: bool = False,
    ptype: str | None = None,
    desc: str | None = None,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type=dtype,
        is_primary_key=pk,
        is_foreign_key=fk,
        is_pii=pii,
        pii_type=ptype,  # type: ignore[arg-type]
        description=desc,
    )


def _model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="dim_customer",
                entity_type="DIMENSION",  # type: ignore[arg-type]
                description="One row per customer.",
                columns=[
                    _col("customer_sk", "INTEGER", pk=True, desc="Surrogate key."),
                    _col("email", "VARCHAR(255)", pii=True, ptype="EMAIL"),
                ],
            ),
            EntitySchema(
                entity_name="fact_orders",
                entity_type="FACT",  # type: ignore[arg-type]
                grain="One row per order.",
                columns=[
                    _col("order_id", "INTEGER", pk=True),
                    _col("customer_sk", "INTEGER", fk=True),
                    _col("total", "NUMERIC(12,2)"),
                ],
            ),
        ],
        relationships=[
            RelationshipSchema.model_validate(
                {"from": "fact_orders.customer_sk", "to": "dim_customer.customer_sk",
                 "cardinality": "N:1"}
            )
        ],
    )


def test_dictionary_markdown() -> None:
    md = ExporterService().export_data_dictionary(_model(), "markdown", "Sales")[
        "data_dictionary.md"
    ]
    assert "# Data Dictionary — Sales" in md
    assert "### dim_customer (DIMENSION)" in md
    assert "**Grain:** One row per order." in md
    assert "FK → dim_customer.customer_sk" in md  # FK target resolved
    assert "EMAIL" in md  # PII surfaced
    assert "## Relationships" in md
    assert "## Business Glossary" in md
    assert "One row per customer." in md  # documented term in glossary


def test_dictionary_html_escaped() -> None:
    html = ExporterService().export_data_dictionary(_model(), "html", "Sales")[
        "data_dictionary.html"
    ]
    assert "<!DOCTYPE html>" in html
    assert "<title>Data Dictionary — Sales</title>" in html
    assert "dim_customer" in html
    assert 'class="pii"' in html


def test_dictionary_json_structure() -> None:
    doc = json.loads(
        ExporterService().export_data_dictionary(_model(), "json", "Sales")[
            "data_dictionary.json"
        ]
    )
    assert doc["dataset"] == "Sales"
    assert doc["paradigm"] == "KIMBALL"
    names = {e["name"] for e in doc["entities"]}
    assert names == {"dim_customer", "fact_orders"}
    fact = next(e for e in doc["entities"] if e["name"] == "fact_orders")
    fk_col = next(c for c in fact["columns"] if c["name"] == "customer_sk")
    assert fk_col["foreign_key"] is True
    assert fk_col["references"] == "dim_customer.customer_sk"
    email = next(
        c
        for e in doc["entities"]
        for c in e["columns"]
        if c["name"] == "email"
    )
    assert email["pii"] is True and email["pii_type"] == "EMAIL"


def test_dictionary_unknown_format_raises() -> None:
    try:
        ExporterService().export_data_dictionary(_model(), "pdf", "Sales")
    except ExporterError:
        return
    raise AssertionError("expected ExporterError for unknown dictionary format")


# ---------------------------------------------------------------------------
# Endpoint
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


async def test_dictionary_endpoint(session: AsyncSession) -> None:
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
            target_paradigm="KIMBALL",  # type: ignore[arg-type]
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
        r = await client.get(f"/api/v1/model/{model_id}/export/dictionary?format=json")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert "data_dictionary.json" in r.json()["files"]
