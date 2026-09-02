"""Who did what inside the appliance, and who is allowed to read it (G11).

`test_egress_ledger_view.py` covers the outbound half — what left the network.
This covers the inbound half, and the two are deliberately separate sinks. A
supervisor reviewing a remediation programme asks both questions, and one table
answering neither cleanly is worse than two answering one each.

Three properties, and they fail in different directions.

**Scoping** fails loudly: one tenant reading another's events is the kind of bug
somebody finds. **Admin-gating** fails quietly, because a trail readable by
everyone it records still looks like a working audit trail. And **the DENIED
row** fails most quietly of all — an implementation that records only permitted
actions produces a log where nothing was ever refused, which reads as a
well-governed system and is the exact opposite of one.

The export is asserted as JSONL rather than as "an export exists", because G11
asks for a format a SIEM ingests without a custom parser. A route that returns
something is not the criterion; a route whose every line is independently
parseable JSON is.
"""

from __future__ import annotations

import datetime
import json
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.models.metadata_store import (
    AUDIT_ACTIONS,
    AUDIT_OUTCOMES,
    AuditEvent,
    Base,
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


def _event(
    *,
    workspace_id: uuid.UUID | None,
    action: str = "MODEL_UPDATED",
    outcome: str = "SUCCESS",
    actor_email: str | None = "a@example.com",
    actor_user_id: uuid.UUID | None = None,
    minutes: int = 0,
) -> AuditEvent:
    return AuditEvent(
        action=action,
        outcome=outcome,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        workspace_id=workspace_id,
        resource_type="model",
        resource_id=str(uuid.uuid4()),
        detail={"field": "title"},
        occurred_at=datetime.datetime(2026, 9, 2, 12, minutes, tzinfo=datetime.UTC),
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
    """Two tenants. One admin, one plain member, and events in both workspaces."""
    admin = User(email="admin@example.com", hashed_password=hash_password("pw"))
    member = User(email="member@example.com", hashed_password=hash_password("pw"))
    other = User(email="other@example.com", hashed_password=hash_password("pw"))
    session.add_all([admin, member, other])
    await session.flush()

    wa, wb = Workspace(name="WA"), Workspace(name="WB")
    session.add_all([wa, wb])
    await session.flush()

    session.add_all(
        [
            WorkspaceMember(
                workspace_id=wa.workspace_id, user_id=admin.user_id, role="ADMIN"
            ),
            WorkspaceMember(
                workspace_id=wa.workspace_id, user_id=member.user_id, role="MEMBER"
            ),
            WorkspaceMember(
                workspace_id=wb.workspace_id, user_id=other.user_id, role="OWNER"
            ),
        ]
    )
    session.add_all(
        [
            _event(workspace_id=wa.workspace_id, minutes=1),
            _event(
                workspace_id=wa.workspace_id,
                action="MEMBER_ROLE_CHANGED",
                minutes=2,
            ),
            _event(
                workspace_id=wa.workspace_id,
                action="AUTH_LOGIN_FAILED",
                outcome="DENIED",
                minutes=3,
            ),
            _event(workspace_id=wb.workspace_id, minutes=4),
        ]
    )
    await session.commit()
    return {"admin": admin, "member": member, "other": other, "wa": wa, "wb": wb}


# ---------------------------------------------------------------------------
# The sink
# ---------------------------------------------------------------------------
def test_the_action_and_outcome_vocabularies_are_not_empty() -> None:
    """Precondition. Empty tuples would make every CHECK constraint vacuous."""
    assert len(AUDIT_ACTIONS) >= 10
    assert set(AUDIT_OUTCOMES) == {"SUCCESS", "DENIED", "FAILURE"}


def test_denied_is_a_distinct_outcome_from_failure() -> None:
    """A refused authorisation and a crashed handler are different events.

    Collapsing them into "not SUCCESS" hides the one a reviewer came to look
    for. Asserted rather than commented, because the cheap simplification is to
    keep two outcomes and it would pass every other test in this file.
    """
    assert "DENIED" in AUDIT_OUTCOMES
    assert "FAILURE" in AUDIT_OUTCOMES


@pytest.mark.asyncio
async def test_an_unknown_action_is_refused_rather_than_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo must not become a silently dropped event.

    `record` swallows exceptions by design — the action it describes has
    already happened, so a logging fault must not fail the request. That makes
    an invalid action especially dangerous: it would raise on the CHECK
    constraint, be swallowed, and leave a caller believing it recorded
    something that was never stored. So the vocabulary is validated *before*
    the write, and this asserts the guard fires without touching a database.
    """
    from app.services import audit_log

    called = False

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        nonlocal called
        called = True
        raise AssertionError("should not reach the database")

    monkeypatch.setattr("app.core.database.AsyncSessionLocal", _boom, raising=False)
    await audit_log.record(action="NOT_A_REAL_ACTION")
    assert not called


# ---------------------------------------------------------------------------
# The view
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_admin_reads_their_own_workspace(session, world) -> None:
    client = await _client(session, world["admin"])
    async with client:
        r = await client.get(
            "/api/v1/audit/events",
            params={"workspace_id": str(world["wa"].workspace_id)},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert {e["action"] for e in body["events"]} == {
        "MODEL_UPDATED",
        "MEMBER_ROLE_CHANGED",
        "AUTH_LOGIN_FAILED",
    }


@pytest.mark.asyncio
async def test_the_denied_row_is_returned_not_filtered(session, world) -> None:
    """The row an audit trail exists for.

    An implementation that recorded only permitted actions would satisfy every
    other assertion here and produce a log in which nothing was ever refused —
    which reads as a well-governed system and is the opposite of one.
    """
    client = await _client(session, world["admin"])
    async with client:
        r = await client.get(
            "/api/v1/audit/events",
            params={
                "workspace_id": str(world["wa"].workspace_id),
                "outcome": "DENIED",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["events"][0]["action"] == "AUTH_LOGIN_FAILED"


@pytest.mark.asyncio
async def test_a_plain_member_cannot_read_the_trail(session, world) -> None:
    """Membership is not enough — this is the quiet failure.

    A trail readable by everyone it records still looks like a working audit
    trail, and these events include other people's authentication and role
    changes.
    """
    client = await _client(session, world["member"])
    async with client:
        r = await client.get(
            "/api/v1/audit/events",
            params={"workspace_id": str(world["wa"].workspace_id)},
        )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_an_admin_of_one_workspace_cannot_read_another(session, world) -> None:
    client = await _client(session, world["admin"])
    async with client:
        r = await client.get(
            "/api/v1/audit/events",
            params={"workspace_id": str(world["wb"].workspace_id)},
        )
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# The export
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_export_is_parseable_jsonl_line_by_line(session, world) -> None:
    """G11's actual ask: a format a SIEM ingests without a custom parser.

    Asserted line by line rather than on the whole body, because that is the
    property Splunk and Sentinel rely on — a JSON *array* would also "be JSON"
    and would fail the moment it was streamed into a line-oriented ingester.
    """
    client = await _client(session, world["admin"])
    async with client:
        r = await client.get(
            "/api/v1/audit/export",
            params={"workspace_id": str(world["wa"].workspace_id)},
        )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")

    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(lines) == 3
    for line in lines:
        row = json.loads(line)  # each line parses alone, or this raises
        assert row["action"] in AUDIT_ACTIONS
        assert row["outcome"] in AUDIT_OUTCOMES
        assert row["occurred_at"]


@pytest.mark.asyncio
async def test_the_export_refuses_a_non_admin(session, world) -> None:
    client = await _client(session, world["member"])
    async with client:
        r = await client.get(
            "/api/v1/audit/export",
            params={"workspace_id": str(world["wa"].workspace_id)},
        )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_the_trail_survives_the_actor_being_deleted(session, world) -> None:
    """The moment somebody most wants to read it.

    `actor_user_id` is not a foreign key and `actor_email` is copied at write
    time, so deleting the user must leave the row and its attribution intact.
    A join-based design passes every other test here and fails this one by
    returning NULL for a departed employee — or, with a cascade, by deleting
    the evidence outright.
    """
    admin_id = world["admin"].user_id
    session.add(
        _event(
            workspace_id=world["wa"].workspace_id,
            actor_user_id=admin_id,
            actor_email="leaver@example.com",
            minutes=9,
        )
    )
    await session.commit()

    await session.delete(world["member"])
    await session.delete(world["admin"])
    await session.commit()

    rows = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.actor_user_id == admin_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_email == "leaver@example.com"
