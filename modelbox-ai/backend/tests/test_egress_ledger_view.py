"""The operator can answer the question from the UI, not from SQL (D4).

D4 asks that an operator answer "what left our network, when, to whom" *without
engineering help*. The ledger has held the answer since Task 1 and the identity
columns were populated in this sprint, but the only way to read it was a
`psql` session — which is help from an engineer by definition.

Two properties matter here and they pull against each other. The view must be
**scoped**, because a ledger is workspace data like any other and a tenant must
not read another's egress. And it must be **honest about what scoping hides**:
rows written with no workspace belong to nobody, so scoping returns them to
nobody, and a governance view that silently omits them reports "this is what
left" when the truth is "this is what left that we can place".

The second is the one worth testing hardest. The first fails loudly the moment
someone checks; the second fails by looking complete.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.models.metadata_store import (
    EGRESS_ATTEMPT,
    Base,
    EgressAudit,
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


def _row(
    *,
    workspace_id: uuid.UUID | None,
    user_id: uuid.UUID | None = None,
    provider: str = "anthropic_cloud",
    event: str = EGRESS_ATTEMPT,
    minutes: int = 0,
) -> EgressAudit:
    return EgressAudit(
        attempt_id=uuid.uuid4(),
        event=event,
        task="unstructured_doc_parsing",
        provider=provider,
        egress_class="cloud",
        prompt_sha256="a" * 64,
        prompt_chars=42,
        workspace_id=workspace_id,
        user_id=user_id,
        occurred_at=datetime.datetime(2026, 8, 29, 12, minutes, tzinfo=datetime.UTC),
    )


async def _client(session: AsyncSession, user: User) -> AsyncClient:
    from app.api.v1.dependencies import get_current_user
    from app.core.database import get_db_session
    from app.main import create_app

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def world(session: AsyncSession):
    """Two tenants, one row each, and one row belonging to nobody."""
    user_a = User(email="a@example.com", hashed_password=hash_password("pw"))
    user_b = User(email="b@example.com", hashed_password=hash_password("pw"))
    session.add_all([user_a, user_b])
    await session.flush()
    wa, wb = Workspace(name="WA"), Workspace(name="WB")
    session.add_all([wa, wb])
    await session.flush()
    session.add_all(
        [
            WorkspaceMember(
                workspace_id=wa.workspace_id, user_id=user_a.user_id, role="OWNER"
            ),
            WorkspaceMember(
                workspace_id=wb.workspace_id, user_id=user_b.user_id, role="OWNER"
            ),
        ]
    )
    session.add_all(
        [
            _row(workspace_id=wa.workspace_id, user_id=user_a.user_id, minutes=1),
            _row(workspace_id=wb.workspace_id, user_id=user_b.user_id, minutes=2),
            _row(workspace_id=None, minutes=3),
        ]
    )
    await session.flush()
    return user_a, user_b, wa, wb


@pytest.mark.asyncio
async def test_an_operator_sees_their_own_egress(session: AsyncSession, world) -> None:
    user_a, _, wa, _ = world
    async with await _client(session, user_a) as client:
        body = (await client.get("/api/v1/egress/events")).json()

    assert body["total"] == 1
    row = body["events"][0]
    assert row["provider"] == "anthropic_cloud"
    assert row["egress_class"] == "cloud"
    assert row["workspace_id"] == str(wa.workspace_id)
    assert row["user_id"] == str(user_a.user_id)


@pytest.mark.asyncio
async def test_one_tenant_cannot_read_anothers_egress(
    session: AsyncSession, world
) -> None:
    """A ledger is workspace data. Reading it is not an operator superpower."""
    user_a, _, _, wb = world
    async with await _client(session, user_a) as client:
        body = (await client.get("/api/v1/egress/events")).json()
        forbidden = await client.get(
            f"/api/v1/egress/events?workspace_id={wb.workspace_id}"
        )

    assert all(e["workspace_id"] != str(wb.workspace_id) for e in body["events"])
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_rows_scoping_cannot_show_are_counted_not_dropped(
    session: AsyncSession, world
) -> None:
    """The load-bearing one.

    A row with no workspace is returned to nobody by workspace scoping. If the
    view simply omits it, an operator reads "one request left the network" from
    a ledger holding three, and the omission is invisible exactly where a
    governance answer needs to be complete. The count is what turns silence
    into a statement.
    """
    user_a, *_ = world
    async with await _client(session, user_a) as client:
        body = (await client.get("/api/v1/egress/events")).json()

    assert body["total"] == 1
    assert body["unattributed"] == 1, (
        "an unattributed row must be reported as unshown, not dropped"
    )


@pytest.mark.asyncio
async def test_a_user_with_no_workspaces_still_learns_of_unattributed_egress(
    session: AsyncSession, world
) -> None:
    """The early-return path is the one that forgets.

    A caller in no workspace short-circuits before any query — the easy way to
    write that returns an empty page and says nothing about the rest.
    """
    orphan = User(email="c@example.com", hashed_password=hash_password("pw"))
    session.add(orphan)
    await session.flush()

    async with await _client(session, orphan) as client:
        body = (await client.get("/api/v1/egress/events")).json()

    assert body["events"] == []
    assert body["unattributed"] == 1


@pytest.mark.asyncio
async def test_the_view_never_returns_the_prompt(session: AsyncSession, world) -> None:
    """The ledger stores a digest, never the text, and the view must not widen that.

    Opening egress history to everyone who can see a workspace is only safe
    while the history is metadata. A field carrying prompt content would turn a
    governance view into a disclosure channel.
    """
    user_a, *_ = world
    async with await _client(session, user_a) as client:
        row = (await client.get("/api/v1/egress/events")).json()["events"][0]

    assert "prompt_sha256" in row
    assert not any("prompt" in k and k != "prompt_sha256" and "chars" not in k
                   and "tokens" not in k for k in row), row.keys()


@pytest.mark.asyncio
async def test_filters_narrow_without_widening_scope(
    session: AsyncSession, world
) -> None:
    """A filter must not become a way around the scoping."""
    user_a, _, _, wb = world
    async with await _client(session, user_a) as client:
        by_provider = (
            await client.get("/api/v1/egress/events?provider=anthropic_cloud")
        ).json()
        missing = (await client.get("/api/v1/egress/events?provider=nope")).json()

    assert by_provider["total"] == 1
    assert all(e["workspace_id"] != str(wb.workspace_id) for e in by_provider["events"])
    assert missing["total"] == 0
