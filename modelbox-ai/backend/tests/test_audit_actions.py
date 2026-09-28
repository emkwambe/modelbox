"""Every declared audit action is emitted, with its scope, and appliance events have one reader.

Sprint 7 Step 3.1.

* **Every action in `AUDIT_ACTIONS` is emitted by a code path.** Each has a
  trigger below that exercises the real path, over HTTP with real credentials
  where there is a route. The trigger map must cover exactly the declared set,
  so declaring an action with no path fails here.
* **Every event carries a workspace, or none with scope `appliance`.**
* **Appliance-scope events are read by the appliance owner** (the
  `is_appliance_owner` flag `create-owner` sets), through `/audit/appliance-events`
  and `/audit/appliance-export`. A workspace OWNER is not the appliance owner:
  every personal workspace makes its creator an OWNER.

Negative controls: a vocabulary with an extra, never-emitted action fails the
coverage check; with `holds_appliance_ownership` patched to accept anyone, a
plain workspace OWNER reads appliance events.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.api.v1 import dependencies
from app.api.v1.dependencies import get_llm_gateway
from app.api.v1.endpoints import scim
from app.core.config import Settings
from app.models.metadata_store import AUDIT_ACTIONS, AuditEvent, DataModel
from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)

PASSWORD = "a-long-enough-password"
SCIM_TOKEN = "s" * 40
APPLIANCE_ACTIONS = {"AUTH_LOGIN", "AUTH_LOGIN_FAILED", "USER_PROVISIONED", "USER_DEPROVISIONED"}


class _Gateway:
    async def structured_completion(self, *args: Any, **kwargs: Any) -> SynthesizedModel:
        return SynthesizedModel(
            paradigm="3NF",
            entities=[
                EntitySchema(
                    entity_name="customers",
                    # Explicit: the field's default is an enum member that is
                    # never validated into its value (flagged separately).
                    entity_type="TABLE",
                    description="People who buy.",
                    columns=[ColumnSchema(name="customer_id", data_type="INT", is_primary_key=True)],
                )
            ],
        )


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    owner = await cli.create_owner(session, "owner@example.com", PASSWORD, "Org")
    admin = await make_user(session, "admin@example.com")
    workspace = await make_workspace(session, "W", {admin: "ADMIN"})
    spare = DataModel(workspace_id=workspace.workspace_id, title="to delete", target_dialect="postgres")
    session.add(spare)
    await session.commit()
    monkeypatch.setattr(
        scim, "get_settings", lambda: Settings(_env_file=None, scim_token=SCIM_TOKEN)  # type: ignore[call-arg]
    )
    return {"owner": owner, "admin": admin, "ws": workspace, "spare": spare}


def _client(session: AsyncSession) -> AsyncClient:
    return real_client(session, {get_llm_gateway: lambda: _Gateway()})


Trigger = Callable[[AsyncClient, dict[str, Any]], Awaitable[None]]


async def _ok(response: Any, *codes: int) -> Any:
    assert response.status_code in codes, f"{response.request.url}: {response.status_code} {response.text[:300]}"
    return response


async def _login(c: AsyncClient, w: dict[str, Any]) -> None:
    await _ok(await c.post("/api/v1/auth/token", data={"username": "owner@example.com", "password": PASSWORD}), 200)


async def _login_failed(c: AsyncClient, w: dict[str, Any]) -> None:
    await _ok(await c.post("/api/v1/auth/token", data={"username": "owner@example.com", "password": "wrong"}), 401)


async def _key_created(c: AsyncClient, w: dict[str, Any]) -> None:
    r = await _ok(
        await c.post(
            "/api/v1/auth/api-keys",
            json={"name": "ci", "workspace_id": str(w["ws"].workspace_id)},
            headers=bearer(w["admin"]),
        ),
        201,
    )
    w["key_id"] = r.json()["api_key_id"]


async def _key_revoked(c: AsyncClient, w: dict[str, Any]) -> None:
    if "key_id" not in w:
        await _key_created(c, w)
    await _ok(await c.delete(f"/api/v1/auth/api-keys/{w['key_id']}", headers=bearer(w["admin"])), 204)


async def _member_added(c: AsyncClient, w: dict[str, Any]) -> None:
    # create-owner already recorded one; registration records another.
    await _ok(await c.post("/api/v1/auth/register", json={"email": "new@example.com", "password": PASSWORD}), 201)


async def _model_created(c: AsyncClient, w: dict[str, Any]) -> None:
    r = await _ok(
        await c.post(
            "/api/v1/model/synthesize",
            json={
                "source_type": "natural_language",
                "content": "customers",
                "workspace_id": str(w["ws"].workspace_id),
            },
            headers=bearer(w["admin"]),
        ),
        201,
    )
    w["model_id"] = r.json()["model_id"]


async def _model_updated(c: AsyncClient, w: dict[str, Any]) -> None:
    if "model_id" not in w:
        await _model_created(c, w)
    await _ok(
        await c.patch(f"/api/v1/model/{w['model_id']}", json={"title": "Renamed"}, headers=bearer(w["admin"])),
        200,
    )


async def _model_deleted(c: AsyncClient, w: dict[str, Any]) -> None:
    await _ok(await c.delete(f"/api/v1/model/{w['spare'].model_id}", headers=bearer(w["admin"])), 204)


async def _model_approved(c: AsyncClient, w: dict[str, Any]) -> None:
    if "model_id" not in w:
        await _model_created(c, w)
    await _ok(await c.post(f"/api/v1/model/{w['model_id']}/approve", headers=bearer(w["admin"])), 204)


async def _artifact_generated(c: AsyncClient, w: dict[str, Any]) -> None:
    if "model_id" not in w:
        await _model_created(c, w)
    await _ok(
        await c.get(f"/api/v1/model/{w['model_id']}/export", params={"format": "ddl"}, headers=bearer(w["admin"])),
        200,
    )


async def _user_provisioned(c: AsyncClient, w: dict[str, Any]) -> None:
    r = await _ok(
        await c.post(
            "/api/v1/scim/v2/Users",
            json={"userName": "scim@example.com"},
            headers={"Authorization": f"Bearer {SCIM_TOKEN}"},
        ),
        201,
    )
    w["scim_id"] = r.json()["id"]


async def _user_deprovisioned(c: AsyncClient, w: dict[str, Any]) -> None:
    if "scim_id" not in w:
        await _user_provisioned(c, w)
    await _ok(
        await c.delete(f"/api/v1/scim/v2/Users/{w['scim_id']}", headers={"Authorization": f"Bearer {SCIM_TOKEN}"}),
        204,
    )


TRIGGERS: dict[str, Trigger] = {
    "AUTH_LOGIN": _login,
    "AUTH_LOGIN_FAILED": _login_failed,
    "API_KEY_CREATED": _key_created,
    "API_KEY_REVOKED": _key_revoked,
    "MEMBER_ADDED": _member_added,
    "MODEL_CREATED": _model_created,
    "MODEL_UPDATED": _model_updated,
    "MODEL_DELETED": _model_deleted,
    "MODEL_APPROVED": _model_approved,
    "ARTIFACT_GENERATED": _artifact_generated,
    "USER_PROVISIONED": _user_provisioned,
    "USER_DEPROVISIONED": _user_deprovisioned,
}


async def _recorded(session: AsyncSession) -> list[AuditEvent]:
    session.expire_all()
    return list((await session.execute(select(AuditEvent))).scalars().all())


def _check_every_action_emitted(declared: tuple[str, ...], recorded: set[str]) -> None:
    """The check, shared by the test and its negative control."""
    assert set(TRIGGERS) == set(declared), (
        f"no trigger for {sorted(set(declared) - set(TRIGGERS))}; "
        f"trigger for undeclared {sorted(set(TRIGGERS) - set(declared))}"
    )
    missing = sorted(set(declared) - recorded)
    assert not missing, f"declared but never emitted: {missing}"


async def test_every_declared_action_is_emitted_by_its_path(session, world) -> None:
    async with _client(session) as client:
        for action in AUDIT_ACTIONS:
            await TRIGGERS[action](client, world)
    events = await _recorded(session)
    _check_every_action_emitted(AUDIT_ACTIONS, {e.action for e in events})


async def test_every_event_carries_a_workspace_or_says_appliance(session, world) -> None:
    async with _client(session) as client:
        for action in AUDIT_ACTIONS:
            await TRIGGERS[action](client, world)
    events = await _recorded(session)
    assert events, "precondition: the triggers recorded something"
    for event in events:
        assert (event.scope == "workspace") == (event.workspace_id is not None), event.action
        if event.action in APPLIANCE_ACTIONS:
            assert event.scope == "appliance", event.action


def test_the_removed_actions_are_gone() -> None:
    assert not {"AUTH_LOGOUT", "MEMBER_ROLE_CHANGED", "MEMBER_REMOVED"} & set(AUDIT_ACTIONS)


# --- The appliance owner reads appliance events -----------------------------


async def _plain_owner(session: AsyncSession) -> Any:
    """A user who is OWNER of a workspace but not the appliance owner."""
    user = await make_user(session, "plain-owner@example.com")
    await make_workspace(session, "Theirs", {user: "OWNER"})
    await session.commit()
    return user


async def test_the_appliance_owner_reads_logins_and_failed_logins(session, world) -> None:
    async with _client(session) as client:
        await _login(client, world)
        await _login_failed(client, world)
        page = await client.get("/api/v1/audit/appliance-events", headers=bearer(world["owner"]))
        export = await client.get("/api/v1/audit/appliance-export", headers=bearer(world["owner"]))
    assert page.status_code == 200, page.text
    assert {"AUTH_LOGIN", "AUTH_LOGIN_FAILED"} <= {e["action"] for e in page.json()["events"]}
    assert all(e["scope"] == "appliance" for e in page.json()["events"])
    lines = [json.loads(line) for line in export.text.splitlines() if line]
    assert {"AUTH_LOGIN", "AUTH_LOGIN_FAILED"} <= {line["action"] for line in lines}


async def _check_plain_owner_refused(session: AsyncSession) -> None:
    """The check, shared by the test and its negative control."""
    user = await _plain_owner(session)
    async with _client(session) as client:
        response = await client.get("/api/v1/audit/appliance-events", headers=bearer(user))
    assert response.status_code == 403, f"a plain workspace OWNER read appliance events: {response.status_code}"


async def test_a_plain_workspace_owner_is_refused(session, world) -> None:
    await _check_plain_owner_refused(session)


async def test_the_appliance_owner_cannot_read_through_an_api_key(session, world) -> None:
    async with _client(session) as client:
        owner_ws = (
            await session.execute(select(dependencies.WorkspaceMember.workspace_id).where(
                dependencies.WorkspaceMember.user_id == world["owner"].user_id
            ))
        ).scalar_one()
        minted = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "k", "workspace_id": str(owner_ws), "role_cap": "OWNER"},
            headers=bearer(world["owner"]),
        )
        response = await client.get(
            "/api/v1/audit/appliance-events", headers={"X-API-Key": minted.json()["api_key"]}
        )
    assert response.status_code == 403


# --- Negative controls ------------------------------------------------------


def test_negative_control_an_unemitted_action_fails_the_check() -> None:
    with pytest.raises(AssertionError, match="GHOST_ACTION"):
        _check_every_action_emitted((*AUDIT_ACTIONS, "GHOST_ACTION"), set(AUDIT_ACTIONS))


async def test_negative_control_without_the_flag_check_a_plain_owner_reads(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dependencies, "holds_appliance_ownership", lambda user: True)
    with pytest.raises(AssertionError, match="plain workspace OWNER read"):
        await _check_plain_owner_refused(session)
