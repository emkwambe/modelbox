"""Roles are enforced at the API, per role, per mutating route (G10).

The register's wording is deliberate: *enforced at the API rather than in the
UI*. A frontend that hides a button is a usability feature; the control is the
403. So every assertion here goes through the HTTP layer, and none of them
inspects a component.

**The matrix is the test.** Asserting that an ADMIN can delete a model proves
almost nothing — the interesting question is always the row below the line, and
a permission model is wrong in exactly one direction that matters: somebody can
do a thing they should not. So each route is exercised at the role that should
be refused as well as the one that should succeed, and the refusal is the
assertion that would catch a regression.

**Why VIEWER exists, tested rather than asserted in a comment.** Before this
sprint the lowest role could edit every model in the workspace, so "let the
auditor look" and "let the auditor change things" were the same grant. The
VIEWER row below is the only thing standing between those two sentences.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.dependencies import _ROLE_LEVEL
from app.core.security import hash_password
from app.models.metadata_store import (
    WORKSPACE_ROLES,
    AuditEvent,
    Base,
    DataModel,
    User,
    Workspace,
    WorkspaceMember,
)

ROLES = ("VIEWER", "MEMBER", "APPROVER", "ADMIN", "OWNER")


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    """A database, plus the audit sink pointed at the same one.

    `audit_log.record` deliberately opens its **own** session through
    `AsyncSessionLocal` rather than joining the caller's, so that a DENIED event
    survives the 403 that rolls the request back. That is correct in production
    and invisible in a test, where overriding `get_db_session` redirects the
    request but not the sink — the audit row is written to whatever the real
    settings point at, and the assertion looks in the test database and finds
    nothing.

    A first draft of `test_an_approval_names_the_person` failed for exactly that
    reason and looked like a missing feature. Binding the sink here keeps the
    production behaviour under test rather than stubbing it out.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker, raising=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


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
    """One workspace, one model, and a user holding each role."""
    ws = Workspace(name="W")
    session.add(ws)
    await session.flush()

    users: dict[str, User] = {}
    for role in ROLES:
        u = User(email=f"{role.lower()}@example.com", hashed_password=hash_password("pw"))
        session.add(u)
        await session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=ws.workspace_id, user_id=u.user_id, role=role
            )
        )
        users[role] = u

    model = DataModel(
        workspace_id=ws.workspace_id, title="Ledger", target_dialect="postgres"
    )
    session.add(model)
    await session.commit()
    return {"ws": ws, "model": model, "users": users}


# ---------------------------------------------------------------------------
# The ladder itself
# ---------------------------------------------------------------------------
def test_the_ladder_is_ordered_and_complete() -> None:
    """Precondition. A missing level defaults to 0 and silently denies nothing.

    `require_workspace_role` compares `_ROLE_LEVEL.get(role, 0)`, so a role
    absent from the map scores zero — which passes a `>= 0` comparison and
    would make an unknown role behave like the lowest one rather than raising.
    Both directions matter, so both are asserted: every declared role has a
    level, and the levels are strictly increasing.
    """
    assert set(WORKSPACE_ROLES) == set(_ROLE_LEVEL)
    levels = [_ROLE_LEVEL[r] for r in ROLES]
    assert levels == sorted(levels)
    assert len(set(levels)) == len(levels), "two roles share a level"


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("role", "expected"),
    [("VIEWER", 403), ("MEMBER", 200), ("APPROVER", 200), ("ADMIN", 200), ("OWNER", 200)],
)
@pytest.mark.asyncio
async def test_editing_the_graph_requires_member(session, world, role, expected) -> None:
    """The VIEWER row is the one this test exists for."""
    client = await _client(session, world["users"][role])
    async with client:
        r = await client.put(
            f"/api/v1/model/{world['model'].model_id}/graph",
            json={"entities": [], "relationships": []},
        )
    assert r.status_code == expected, f"{role}: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize(
    ("role", "expected"),
    [("VIEWER", 403), ("MEMBER", 403), ("APPROVER", 204), ("ADMIN", 204), ("OWNER", 204)],
)
@pytest.mark.asyncio
async def test_approving_requires_approver(session, world, role, expected) -> None:
    """A modeller cannot sign off on their own work.

    That is the entire reason the role exists — if MEMBER could approve, the
    audit trail would record sign-off by the person who made the change, which
    answers the question a reviewer asks with the wrong name.
    """
    client = await _client(session, world["users"][role])
    async with client:
        r = await client.post(f"/api/v1/model/{world['model'].model_id}/approve")
    assert r.status_code == expected, f"{role}: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize(
    ("role", "expected"),
    [("VIEWER", 403), ("MEMBER", 403), ("APPROVER", 403), ("ADMIN", 204), ("OWNER", 204)],
)
@pytest.mark.asyncio
async def test_deleting_requires_admin(session, world, role, expected) -> None:
    """An approver can sign off and still not destroy the evidence."""
    client = await _client(session, world["users"][role])
    async with client:
        r = await client.delete(f"/api/v1/model/{world['model'].model_id}")
    assert r.status_code == expected, f"{role}: {r.status_code} {r.text[:200]}"


@pytest.mark.asyncio
async def test_a_non_member_is_refused(session, world) -> None:
    """Somebody outside the workspace is refused, and the code says 403.

    Written first as `assert 404`, on the reasoning that 403 tells a stranger
    the model exists. That is a real if minor information leak — but 403 is the
    documented, uniform behaviour of `get_authorized_model` across every model
    route, so a test asserting 404 would have been inventing a requirement
    nobody made and would fail for the whole API rather than for this change.

    Recorded rather than silently changed: making non-membership indistinguishable
    from absence is a defensible hardening, it belongs to every route at once,
    and it is not G10.
    """
    outsider = User(email="outsider@example.com", hashed_password=hash_password("pw"))
    session.add(outsider)
    await session.commit()

    client = await _client(session, outsider)
    async with client:
        r = await client.delete(f"/api/v1/model/{world['model'].model_id}")
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# The approval is readable afterwards — which is the point of having it
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_approval_names_the_person_and_survives_in_the_trail(
    session, world
) -> None:
    """"Who signed off on this model" has an answer, and it is a name.

    Recorded to the audit trail rather than a column on the model, because a
    column holds only the latest answer and a reviewer usually asks about a
    version that is no longer current.
    """
    approver = world["users"]["APPROVER"]
    client = await _client(session, approver)
    async with client:
        r = await client.post(f"/api/v1/model/{world['model'].model_id}/approve")
    assert r.status_code == 204, r.text

    rows = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "MODEL_APPROVED")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_email == approver.email
    assert rows[0].resource_id == str(world["model"].model_id)
    assert rows[0].outcome == "SUCCESS"


@pytest.mark.asyncio
async def test_a_refused_approval_is_not_recorded_as_one(session, world) -> None:
    """The discriminating half of the test above.

    An implementation that wrote the audit row before checking the role would
    satisfy every assertion in this file except this one — and would produce a
    trail in which people who were refused appear to have signed off.
    """
    client = await _client(session, world["users"]["MEMBER"])
    async with client:
        r = await client.post(f"/api/v1/model/{world['model'].model_id}/approve")
    assert r.status_code == 403

    rows = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "MODEL_APPROVED")
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


def test_every_mutating_model_route_declares_a_role() -> None:
    """The gap this criterion closes, asserted structurally.

    Before Sprint 6.5, mutating model routes went through `AuthorizedModelDep`,
    which proves *membership* and says nothing about role — so the lowest role
    in the workspace could edit and export every model in it. A per-route test
    catches the routes that exist today; this catches the one somebody adds
    next week, which is the failure that actually happens.
    """
    import inspect

    from app.api.v1.endpoints import models as models_module

    source = inspect.getsource(models_module)
    unguarded: list[str] = []
    for chunk in source.split("@router.")[1:]:
        verb = chunk.split("(", 1)[0].strip()
        if verb not in {"post", "put", "patch", "delete"}:
            continue
        header, _, _rest = chunk.partition("\n) -> ")
        name = header.split("async def ", 1)[-1].split("(", 1)[0]
        if "require_model_role" not in header and "require_workspace_role" not in chunk:
            unguarded.append(f"{verb.upper()} {name}")

    # Exempt individually, each for a stated reason, so adding a sixth is a
    # deliberate act rather than a silent widening.
    #
    #   synthesize_model / diff_models / validate_graph — take no model_id.
    #       They create or compute rather than mutate an existing model, and are
    #       membership-scoped at the workspace.
    #   validate_model / export_synthetic_data — POST, but neither writes. They
    #       run the linter and generate rows from a model already loaded, and a
    #       VIEWER auditing a workspace should be able to do both. Requiring
    #       MEMBER here would mean read-only access could not read the thing it
    #       exists to review.
    allowed = {
        "POST synthesize_model",
        "POST diff_models",
        "POST validate_graph",
        "POST validate_model",
        "POST export_synthetic_data",
    }
    assert set(unguarded) <= allowed, f"mutating routes with no role: {unguarded}"
