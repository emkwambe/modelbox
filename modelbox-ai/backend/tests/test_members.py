"""Workspace members: add, change role, remove, and the rules (Sprint 8 Step 6, B1-B3, B5).

Every call uses a real bearer token or a real API key through the real
`get_current_user` (`tests/_real_auth.py`); what is stored is read back by raw
SQL. Negative controls patch out exactly the rule each test is about and show
the same request then succeeds: the last-owner guard, the no-escalation rule,
and the per-request re-read that stops a removed member's keys.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import dependencies
from app.api.v1.endpoints import members
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    owner = await make_user(session, "owner@example.com")
    admin = await make_user(session, "admin@example.com")
    member = await make_user(session, "member@example.com")
    newcomer = await make_user(session, "newcomer@example.com")
    ws = await make_workspace(session, "W", {owner: "OWNER", admin: "ADMIN", member: "MEMBER"})
    await session.commit()
    return {"owner": owner, "admin": admin, "member": member, "newcomer": newcomer, "ws": ws}


def _url(w: dict[str, Any], who: Any = None) -> str:
    base = f"/api/v1/workspaces/{w['ws'].workspace_id}/members"
    return f"{base}/{who.user_id}" if who is not None else base


async def _roles(session: AsyncSession, w: dict[str, Any]) -> dict[str, str]:
    rows = (await session.execute(text(
        "SELECT u.email, m.role FROM workspace_members m JOIN users u ON u.user_id = m.user_id "
        "ORDER BY u.email"))).all()
    return dict(rows)


async def _events(session: AsyncSession, action: str) -> list[dict[str, Any]]:
    rows = (await session.execute(text("SELECT detail FROM audit_event WHERE action = :a"), {"a": action})).all()
    return [d if isinstance(d, dict) else json.loads(d) for (d,) in rows]


# --- B1: add, change, remove --------------------------------------------------


async def test_an_owner_adds_an_existing_user(session, world) -> None:
    async with real_client(session) as c:
        r = await c.post(_url(world), json={"email": "Newcomer@Example.com", "role": "MEMBER"},
                         headers=bearer(world["owner"]))
    assert r.status_code == 201, r.text
    assert (await _roles(session, world))["newcomer@example.com"] == "MEMBER"
    assert [e["member"] for e in await _events(session, "MEMBER_ADDED")] == ["newcomer@example.com"]


async def test_an_email_with_no_user_is_refused_by_name(session, world) -> None:
    async with real_client(session) as c:
        r = await c.post(_url(world), json={"email": "nobody@example.com", "role": "VIEWER"},
                         headers=bearer(world["owner"]))
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "nobody@example.com" in detail and "OIDC" in detail and "SCIM" in detail and "create-owner" in detail
    count = (await session.execute(text("SELECT count(*) FROM users"))).scalar_one()
    assert count == 4, "no user is created"


async def test_an_existing_member_is_not_added_twice(session, world) -> None:
    async with real_client(session) as c:
        r = await c.post(_url(world), json={"email": "member@example.com", "role": "VIEWER"},
                         headers=bearer(world["owner"]))
    assert r.status_code == 409 and "already a member, as MEMBER" in r.text


async def test_an_admin_changes_a_role_and_removes_a_member(session, world) -> None:
    async with real_client(session) as c:
        changed = await c.patch(_url(world, world["member"]), json={"role": "VIEWER"},
                                headers=bearer(world["admin"]))
        removed = await c.delete(_url(world, world["member"]), headers=bearer(world["admin"]))
    assert (changed.status_code, removed.status_code) == (200, 204)
    assert "member@example.com" not in await _roles(session, world)
    assert [(e["previous"], e["role"]) for e in await _events(session, "MEMBER_ROLE_CHANGED")] == [
        ("MEMBER", "VIEWER")]
    assert [e["previous"] for e in await _events(session, "MEMBER_REMOVED")] == ["VIEWER"]


async def test_a_member_cannot_manage_members(session, world) -> None:
    async with real_client(session) as c:
        add = await c.post(_url(world), json={"email": "newcomer@example.com", "role": "VIEWER"},
                           headers=bearer(world["member"]))
        listed = await c.get(_url(world), headers=bearer(world["member"]))
    assert add.status_code == 403
    assert listed.status_code == 200 and {m["email"] for m in listed.json()} == {
        "owner@example.com", "admin@example.com", "member@example.com"}


# --- B2: no escalation ----------------------------------------------------------


async def _escalations(session: AsyncSession, w: dict[str, Any]) -> list[int]:
    async with real_client(session) as c:
        return [r.status_code for r in (
            await c.post(_url(w), json={"email": "newcomer@example.com", "role": "OWNER"},
                         headers=bearer(w["admin"])),
            await c.patch(_url(w, w["member"]), json={"role": "OWNER"}, headers=bearer(w["admin"])),
        )]


async def test_an_admin_cannot_make_an_owner(session, world) -> None:
    assert await _escalations(session, world) == [403, 403]
    roles = await _roles(session, world)
    assert roles["member@example.com"] == "MEMBER" and "newcomer@example.com" not in roles


async def test_negative_control_without_the_rule_an_admin_makes_an_owner(session, world, monkeypatch) -> None:
    monkeypatch.setattr(members, "check_grant", lambda actor, new: None)
    assert await _escalations(session, world) == [201, 200]


async def test_an_admin_may_grant_up_to_admin(session, world) -> None:
    async with real_client(session) as c:
        r = await c.patch(_url(world, world["member"]), json={"role": "ADMIN"}, headers=bearer(world["admin"]))
    assert r.status_code == 200


async def test_an_admin_cannot_demote_or_remove_an_owner(session, world) -> None:
    async with real_client(session) as c:
        demote = await c.patch(_url(world, world["owner"]), json={"role": "VIEWER"}, headers=bearer(world["admin"]))
        remove = await c.delete(_url(world, world["owner"]), headers=bearer(world["admin"]))
    assert (demote.status_code, remove.status_code) == (403, 403)
    assert (await _roles(session, world))["owner@example.com"] == "OWNER"


async def test_a_key_grants_no_more_than_its_cap(session, world) -> None:
    """The role acted with is the key's effective one: an OWNER's ADMIN-capped key cannot make an OWNER."""
    async with real_client(session) as c:
        minted = await c.post("/api/v1/auth/api-keys", headers=bearer(world["owner"]), json={
            "name": "ci", "workspace_id": str(world["ws"].workspace_id), "role_cap": "ADMIN"})
        key = {"X-API-Key": minted.json()["api_key"]}
        up = await c.patch(_url(world, world["member"]), json={"role": "OWNER"}, headers=key)
        ok = await c.patch(_url(world, world["member"]), json={"role": "ADMIN"}, headers=key)
    assert (up.status_code, ok.status_code) == (403, 200)


# --- B2: the last owner -----------------------------------------------------------


async def _last_owner_changes(session: AsyncSession, w: dict[str, Any]) -> list[int]:
    async with real_client(session) as c:
        return [r.status_code for r in (
            await c.patch(_url(w, w["owner"]), json={"role": "ADMIN"}, headers=bearer(w["owner"])),
            await c.delete(_url(w, w["owner"]), headers=bearer(w["owner"])),
        )]


async def test_the_last_owner_can_never_be_demoted_or_removed(session, world) -> None:
    assert await _last_owner_changes(session, world) == [409, 409]
    assert (await _roles(session, world))["owner@example.com"] == "OWNER"


async def test_negative_control_without_the_guard_the_last_owner_goes(session, world, monkeypatch) -> None:
    async def no_guard(*_: Any) -> None:
        return None

    monkeypatch.setattr(members, "_refuse_last_owner", no_guard)
    statuses = await _last_owner_changes(session, world)
    assert statuses[0] == 200, statuses
    owners = (await session.execute(text("SELECT count(*) FROM workspace_members WHERE role = 'OWNER'"))
              ).scalar_one()
    assert owners == 0, "the workspace was left with no owner"


async def test_with_a_second_owner_an_owner_may_step_down(session, world) -> None:
    async with real_client(session) as c:
        promoted = await c.patch(_url(world, world["admin"]), json={"role": "OWNER"}, headers=bearer(world["owner"]))
        stepped = await c.patch(_url(world, world["owner"]), json={"role": "ADMIN"}, headers=bearer(world["owner"]))
    assert (promoted.status_code, stepped.status_code) == (200, 200)


# --- B2: a removed member's keys ---------------------------------------------------


async def _key_after_removal(session: AsyncSession, w: dict[str, Any]) -> tuple[int, int]:
    """(before, after): a member's key reading the workspace, before and after removal.
    The member is the ADMIN: minting a key takes ADMIN."""
    url = f"/api/v1/workspaces/{w['ws'].workspace_id}/classification"
    async with real_client(session) as c:
        minted = await c.post("/api/v1/auth/api-keys", headers=bearer(w["admin"]), json={
            "name": "ci", "workspace_id": str(w["ws"].workspace_id)})
        assert minted.status_code == 201, minted.text
        key = {"X-API-Key": minted.json()["api_key"]}
        before = (await c.get(url, headers=key)).status_code
        removed = await c.delete(_url(w, w["admin"]), headers=bearer(w["owner"]))
        assert removed.status_code == 204
        after = (await c.get(url, headers=key)).status_code
    return before, after


async def test_a_removed_members_keys_stop_at_once(session, world) -> None:
    assert await _key_after_removal(session, world) == (200, 403)


async def test_negative_control_a_membership_read_once_would_keep_the_key(session, world, monkeypatch) -> None:
    """If membership were not re-read per request (here: the role remembered
    from before the removal), the removed member's key would keep working."""
    real = dependencies.require_membership
    remembered: dict[tuple[Any, Any], Any] = {}

    async def remembering(session_, user_id, workspace_id):  # type: ignore[no-untyped-def]
        key = (user_id, workspace_id)
        if key not in remembered:
            remembered[key] = await real(session_, user_id, workspace_id)
        return remembered[key]

    monkeypatch.setattr(dependencies, "require_membership", remembering)
    assert await _key_after_removal(session, world) == (200, 200)
