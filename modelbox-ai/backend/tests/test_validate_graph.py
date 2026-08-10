"""Test for POST /api/v1/model/validate-graph (stateless linting for labs)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.models.metadata_store import Base, User


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


async def test_validate_graph_flags_fan_out(session: AsyncSession) -> None:
    from app.api.v1.dependencies import get_current_user
    from app.core.database import get_db_session
    from app.main import create_app

    user = User(email="l@example.com", hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user

    body = {
        "entities": [
            {
                "entity_name": "a",
                "entity_type": "TABLE",
                "columns": [{"name": "id", "data_type": "INT", "is_primary_key": True}],
            },
            {
                "entity_name": "b",
                "entity_type": "TABLE",
                "columns": [{"name": "id", "data_type": "INT", "is_primary_key": True}],
            },
        ],
        "relationships": [{"from": "a.id", "to": "b.id", "cardinality": "N:M"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/model/validate-graph", json=body)
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    codes = {i["code"] for i in r.json()["issues"]}
    assert "FAN_OUT_RISK" in codes
