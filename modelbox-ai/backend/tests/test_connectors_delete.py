"""Test for DELETE /api/v1/connectors/{id} (connection management)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.crypto import encrypt_secret
from app.core.security import hash_password
from app.models.metadata_store import (
    Base,
    DatabaseConnection,
    User,
    Workspace,
    WorkspaceMember,
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


async def test_delete_connection(session: AsyncSession) -> None:
    from app.api.v1.dependencies import get_current_user
    from app.core.database import get_db_session
    from app.main import create_app

    user = User(email="admin@example.com", hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()
    workspace = Workspace(name="ws")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id, user_id=user.user_id, role="ADMIN"
        )
    )
    connection = DatabaseConnection(
        workspace_id=workspace.workspace_id,
        name="temp",
        engine="POSTGRESQL",
        connection_uri_encrypted=encrypt_secret("postgresql://u:p@h/db"),
    )
    session.add(connection)
    await session.flush()
    conn_id = str(connection.connection_id)

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deleted = await client.delete(f"/api/v1/connectors/{conn_id}")
        listing = await client.get("/api/v1/connectors")
        missing = await client.delete(f"/api/v1/connectors/{uuid.uuid4()}")
    app.dependency_overrides.clear()

    assert deleted.status_code == 204, deleted.text
    assert listing.json() == []  # gone
    assert missing.status_code == 404
