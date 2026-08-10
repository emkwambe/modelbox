"""Tests for API key management + X-API-Key authentication (Step 1)."""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.models.metadata_store import Base, User, Workspace, WorkspaceMember


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


async def _seed_owner(session: AsyncSession) -> User:
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
    return user


def _client(session: AsyncSession):
    from app.core.database import get_db_session
    from app.main import create_app

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    return app, AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    )


async def test_api_key_lifecycle(session: AsyncSession) -> None:
    user = await _seed_owner(session)
    bearer = {"Authorization": f"Bearer {create_access_token(str(user.user_id))}"}
    app, client = _client(session)

    async with client:
        # Create — secret returned exactly once, prefixed mb_live_.
        created = await client.post(
            "/api/v1/auth/api-keys", json={"name": "CI pipeline"}, headers=bearer
        )
        assert created.status_code == 201, created.text
        body = created.json()
        secret = body["api_key"]
        assert secret.startswith("mb_live_")
        assert body["key_prefix"].startswith("mb_live_")
        key_id = body["api_key_id"]

        # The secret authenticates programmatically via X-API-Key.
        me = await client.get("/api/v1/auth/me", headers={"X-API-Key": secret})
        assert me.status_code == 200
        assert me.json()["email"] == user.email

        # List returns metadata only — never the secret.
        listing = await client.get("/api/v1/auth/api-keys", headers=bearer)
        assert listing.status_code == 200
        assert len(listing.json()) == 1
        assert "api_key" not in listing.json()[0]

        # A bogus key is rejected.
        bad = await client.get(
            "/api/v1/auth/me", headers={"X-API-Key": "mb_live_bogus"}
        )
        assert bad.status_code == 401

        # Revoke, then the key no longer authenticates.
        revoked = await client.delete(
            f"/api/v1/auth/api-keys/{key_id}", headers=bearer
        )
        assert revoked.status_code == 204
        after = await client.get("/api/v1/auth/me", headers={"X-API-Key": secret})
        assert after.status_code == 401

    app.dependency_overrides.clear()


async def test_expired_api_key_is_rejected(session: AsyncSession) -> None:
    user = await _seed_owner(session)
    bearer = {"Authorization": f"Bearer {create_access_token(str(user.user_id))}"}
    past = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    ).isoformat()
    app, client = _client(session)

    async with client:
        created = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "expired", "expires_at": past},
            headers=bearer,
        )
        secret = created.json()["api_key"]
        me = await client.get("/api/v1/auth/me", headers={"X-API-Key": secret})
        assert me.status_code == 401  # expired

    app.dependency_overrides.clear()
