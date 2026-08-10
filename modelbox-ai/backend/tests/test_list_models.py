"""Test for GET /api/v1/model — workspace-scoped model listing (diff selector)."""

from __future__ import annotations

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
    SynthesizedModel,
    SynthesizeRequest,
)
from app.services.synthesis_engine import SynthesisEngine


class _StubGateway:
    def __init__(self, model: SynthesizedModel) -> None:
        self._model = model

    async def structured_completion(
        self, task: str, prompt: str, response_model: type[Any], **_: Any
    ) -> SynthesizedModel:
        return self._model


def _model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="t",  # type: ignore[arg-type]
                columns=[ColumnSchema(name="id", data_type="INT", is_primary_key=True)],
            )
        ],
    )


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


async def test_list_models_scoped_to_membership(session: AsyncSession) -> None:
    from app.api.v1.dependencies import get_current_user, get_synthesis_engine
    from app.core.database import get_db_session
    from app.main import create_app

    # User A in workspace WA with one model; user B in workspace WB.
    user_a = User(email="a@example.com", hashed_password=hash_password("pw"))
    user_b = User(email="b@example.com", hashed_password=hash_password("pw"))
    session.add_all([user_a, user_b])
    await session.flush()
    wa, wb = Workspace(name="WA"), Workspace(name="WB")
    session.add_all([wa, wb])
    await session.flush()
    session.add_all(
        [
            WorkspaceMember(workspace_id=wa.workspace_id, user_id=user_a.user_id, role="OWNER"),
            WorkspaceMember(workspace_id=wb.workspace_id, user_id=user_b.user_id, role="OWNER"),
        ]
    )
    await session.flush()

    engine = SynthesisEngine(session, _StubGateway(_model()))
    await engine.synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="m",
            target_paradigm="3NF",  # type: ignore[arg-type]
            dialect="postgres",
            workspace_id=wa.workspace_id,
        )
    )

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_synthesis_engine] = lambda: SynthesisEngine(
        session, _StubGateway(_model())
    )

    transport = ASGITransport(app=app)
    # User A sees their model.
    app.dependency_overrides[get_current_user] = lambda: user_a
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ra = await client.get("/api/v1/model")
    # User B (different workspace) sees none.
    app.dependency_overrides[get_current_user] = lambda: user_b
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rb = await client.get("/api/v1/model")
    app.dependency_overrides.clear()

    assert ra.status_code == 200, ra.text
    assert len(ra.json()) == 1
    assert ra.json()[0]["title"]
    assert rb.status_code == 200
    assert rb.json() == []
