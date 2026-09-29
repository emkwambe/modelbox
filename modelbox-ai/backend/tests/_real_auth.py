"""A client that authenticates the way production does.

Sprint 7's rule: a test that overrides `get_current_user` is not evidence for
an authorization criterion, because it skips the code that decides who the
caller is. These helpers override only the database session. A caller
authenticates with a real bearer token from `create_access_token`, or a real
`X-API-Key`, and `get_current_user` resolves it exactly as it would in the
appliance.

The audit sink opens its own session through `get_sessionmaker()`, so it is
pointed at the same database, or an audited 403 is written somewhere else. The
patch uses monkeypatch's default `raising=True`: it fails if the name does not
exist in `app.core.database`, which is what production would call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.models.metadata_store import Base, User, Workspace, WorkspaceMember


async def sqlite_session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.get_sessionmaker", lambda: maker)
    async with maker() as session:
        # For code that opens its own sessions, such as `app.cli.run`.
        session.info["maker"] = maker
        yield session
    await engine.dispose()


def real_client(
    session: AsyncSession, overrides: dict[object, object] | None = None
) -> AsyncClient:
    """An app whose only override is the database session (plus ``overrides``).

    ``overrides`` maps dependency callables to replacements, for doubles such
    as the LLM gateway. Passing `get_current_user` here is refused, because
    that is the one override these tests exist to avoid.
    """
    from app.api.v1.dependencies import get_current_user
    from app.core.database import get_db_session, get_streaming_db_session
    from app.main import create_app

    overrides = overrides or {}
    assert get_current_user not in overrides, "real_client must not override get_current_user"
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    # The JSONL exports read through their own streaming session; same database.
    app.dependency_overrides[get_streaming_db_session] = _session
    app.dependency_overrides.update(overrides)  # type: ignore[arg-type]
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def bearer(user: User) -> dict[str, str]:
    """A real token for ``user``, as `/auth/token` would issue it."""
    return {"Authorization": f"Bearer {create_access_token(str(user.user_id))}"}


async def make_user(session: AsyncSession, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("pw-for-tests"))
    session.add(user)
    await session.flush()
    return user


async def make_workspace(
    session: AsyncSession, name: str, members: dict[User, str]
) -> Workspace:
    workspace = Workspace(name=name)
    session.add(workspace)
    await session.flush()
    for user, role in members.items():
        session.add(
            WorkspaceMember(workspace_id=workspace.workspace_id, user_id=user.user_id, role=role)
        )
    await session.flush()
    return workspace
