"""An API key acts only in its workspace, at the lower of its cap and its creator's role.

Sprint 7 Step 2.3. A key resolves to a principal carrying the key's workspace
and role cap. A request for another workspace is 403. The effective role is the
lower of the cap and the creator's *current* role, read on every use, so
demoting or removing the creator limits the key at once. A key cannot mint a
key. New keys default to VIEWER; a creator may choose higher, never above
their own role.

Keys are minted through the real endpoint by a signed-in admin, and used with a
real `X-API-Key` header through the real `get_current_user`.

Negative controls patch exactly the functions this introduced:
`key_allows_workspace`, `effective_role` and `forbid_api_key_principal`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import dependencies
from app.api.v1.endpoints import auth
from app.models.metadata_store import DataModel, WorkspaceMember
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)

GRAPH = {"entities": [], "relationships": []}


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    admin = await make_user(session, "admin@example.com")
    ws_a = await make_workspace(session, "A", {admin: "ADMIN"})
    ws_b = await make_workspace(session, "B", {admin: "ADMIN"})
    model_a = DataModel(workspace_id=ws_a.workspace_id, title="in A", target_dialect="postgres")
    model_b = DataModel(workspace_id=ws_b.workspace_id, title="in B", target_dialect="postgres")
    session.add_all([model_a, model_b])
    await session.commit()
    return {"admin": admin, "a": ws_a, "b": ws_b, "model_a": model_a, "model_b": model_b}


async def _mint(client: AsyncClient, world: dict[str, Any], **body: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "ci", "workspace_id": str(world["a"].workspace_id), **body},
        headers=bearer(world["admin"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _key(minted: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": minted["api_key"]}


# --- Workspace scope --------------------------------------------------------


async def _check_other_workspace_refused(session: AsyncSession, world: dict[str, Any]) -> None:
    """The check, shared by the test and its negative control."""
    async with real_client(session) as client:
        key = _key(await _mint(client, world, role_cap="MEMBER"))
        own = await client.get(f"/api/v1/model/{world['model_a'].model_id}", headers=key)
        other = await client.get(f"/api/v1/model/{world['model_b'].model_id}", headers=key)
    assert own.status_code == 200, own.text
    assert other.status_code == 403, f"a key for A read B: {other.status_code}"


async def test_a_key_is_refused_in_another_workspace(session, world) -> None:
    """The creator is ADMIN in both workspaces; only the key's scope refuses B."""
    await _check_other_workspace_refused(session, world)


async def test_a_key_lists_only_its_workspace(session, world) -> None:
    async with real_client(session) as client:
        key = _key(await _mint(client, world))
        listed = await client.get("/api/v1/model", headers=key)
    assert {m["title"] for m in listed.json()} == {"in A"}


# --- Role cap ---------------------------------------------------------------


async def _check_viewer_cap_refuses_a_write(session: AsyncSession, world: dict[str, Any]) -> None:
    """The check, shared by the test and its negative control."""
    async with real_client(session) as client:
        key = _key(await _mint(client, world))  # default cap
        read = await client.get(f"/api/v1/model/{world['model_a'].model_id}", headers=key)
        write = await client.put(
            f"/api/v1/model/{world['model_a'].model_id}/graph", json=GRAPH, headers=key
        )
    assert read.status_code == 200, read.text
    assert write.status_code == 403, f"a VIEWER-capped key wrote: {write.status_code}"


async def test_a_new_key_defaults_to_viewer(session, world) -> None:
    async with real_client(session) as client:
        minted = await _mint(client, world)
    assert minted["role_cap"] == "VIEWER"


async def test_a_viewer_capped_key_cannot_write(session, world) -> None:
    await _check_viewer_cap_refuses_a_write(session, world)


async def test_a_member_capped_key_can_write(session, world) -> None:
    """Precondition: the cap is what refuses, not the route."""
    async with real_client(session) as client:
        key = _key(await _mint(client, world, role_cap="MEMBER"))
        write = await client.put(
            f"/api/v1/model/{world['model_a'].model_id}/graph", json=GRAPH, headers=key
        )
    assert write.status_code == 200, write.text


async def test_a_cap_cannot_exceed_the_creators_role(session, world) -> None:
    async with real_client(session) as client:
        response = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "x", "workspace_id": str(world["a"].workspace_id), "role_cap": "OWNER"},
            headers=bearer(world["admin"]),
        )
    assert response.status_code == 403, response.text


async def test_the_creators_current_role_is_read_on_every_use(session, world) -> None:
    """Demote the creator after minting: the key loses the write at once."""
    async with real_client(session) as client:
        key = _key(await _mint(client, world, role_cap="MEMBER"))
        url = f"/api/v1/model/{world['model_a'].model_id}/graph"
        assert (await client.put(url, json=GRAPH, headers=key)).status_code == 200

        member = (
            await session.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == world["a"].workspace_id,
                    WorkspaceMember.user_id == world["admin"].user_id,
                )
            )
        ).scalar_one()
        member.role = "VIEWER"
        await session.commit()
        assert (await client.put(url, json=GRAPH, headers=key)).status_code == 403

        await session.delete(member)
        await session.commit()
        read = await client.get(f"/api/v1/model/{world['model_a'].model_id}", headers=key)
    assert read.status_code == 403, "a removed creator's key still reads"


# --- Keys cannot mint keys --------------------------------------------------


async def _check_key_cannot_mint(session: AsyncSession, world: dict[str, Any]) -> None:
    """The check, shared by the test and its negative control."""
    async with real_client(session) as client:
        key = _key(await _mint(client, world, role_cap="ADMIN"))
        response = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "minted by a key", "workspace_id": str(world["a"].workspace_id)},
            headers=key,
        )
    assert response.status_code == 403, f"a key minted a key: {response.status_code}"


async def test_a_key_cannot_mint_a_key(session, world) -> None:
    await _check_key_cannot_mint(session, world)


# --- Negative controls ------------------------------------------------------


async def test_negative_control_without_the_workspace_scope_a_key_reaches_b(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dependencies, "key_allows_workspace", lambda principal, ws: True)
    with pytest.raises(AssertionError, match="a key for A read B"):
        await _check_other_workspace_refused(session, world)


async def test_negative_control_without_the_cap_a_viewer_key_writes(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dependencies, "effective_role", lambda role, principal: role)
    with pytest.raises(AssertionError, match="VIEWER-capped key wrote"):
        await _check_viewer_cap_refuses_a_write(session, world)


async def test_negative_control_without_the_refusal_a_key_mints_a_key(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "forbid_api_key_principal", lambda request: None)
    with pytest.raises(AssertionError, match="a key minted a key"):
        await _check_key_cannot_mint(session, world)
