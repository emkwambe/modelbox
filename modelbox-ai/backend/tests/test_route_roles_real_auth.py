"""Declared roles hold over HTTP, with real credentials.

`test_route_policy.py` proves every route's dependency chain carries its
declared role. This proves the dependencies refuse the role below the line,
with a caller authenticated by a real bearer token through the real
`get_current_user`: one route per kind of enforcement (model path, body
workspace, body resource, listing, query workspace).

The negative control overrides exactly the dependency `transform-paradigm`
uses, `require_model_role("MEMBER")`, with one that checks membership only,
and asserts the VIEWER refusal then fails.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import SessionDep, get_llm_gateway, require_model_role
from app.models.metadata_store import DatabaseConnection, DataModel
from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)

TRANSFORM = "/api/v1/model/{model_id}/transform-paradigm"


class _StubGateway:
    """Returns a lint-clean one-entity model for any structured completion."""

    async def structured_completion(self, *args: Any, **kwargs: Any) -> SynthesizedModel:
        return SynthesizedModel(
            paradigm="DATA_VAULT",
            entities=[
                EntitySchema(
                    entity_name="hub_customer",
                    columns=[ColumnSchema(name="customer_hk", data_type="CHAR(32)", is_primary_key=True)],
                )
            ],
        )


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    users = {role: await make_user(session, f"{role.lower()}@example.com") for role in
             ("VIEWER", "MEMBER", "ADMIN")}
    workspace = await make_workspace(session, "W", {users[r]: r for r in users})
    model = DataModel(workspace_id=workspace.workspace_id, title="Ledger", target_dialect="postgres")
    connection = DatabaseConnection(
        workspace_id=workspace.workspace_id,
        name="warehouse",
        engine="POSTGRESQL",
        connection_uri_encrypted="not-used",
    )
    session.add_all([model, connection])
    await session.commit()
    return {"users": users, "ws": workspace, "model": model, "connection": connection}


def _client(session: AsyncSession, overrides: dict[object, object] | None = None) -> AsyncClient:
    return real_client(session, {get_llm_gateway: lambda: _StubGateway(), **(overrides or {})})


async def _transform_status(client: AsyncClient, world: dict[str, Any], role: str) -> int:
    response = await client.post(
        TRANSFORM.format(model_id=world["model"].model_id),
        json={"target_paradigm": "DATA_VAULT"},
        headers=bearer(world["users"][role]),
    )
    return response.status_code


@pytest.mark.parametrize(("role", "expected"), [("VIEWER", 403), ("MEMBER", 200), ("ADMIN", 200)])
async def test_transform_requires_member(session, world, role, expected) -> None:
    async with _client(session) as client:
        assert await _transform_status(client, world, role) == expected


async def test_synthesis_in_a_named_workspace_requires_member(session, world) -> None:
    async with _client(session) as client:
        response = await client.post(
            "/api/v1/model/synthesize",
            json={
                "source_type": "natural_language",
                "content": "customers and orders",
                "workspace_id": str(world["ws"].workspace_id),
            },
            headers=bearer(world["users"]["VIEWER"]),
        )
    assert response.status_code == 403, response.text


async def test_introspection_requires_member(session, world) -> None:
    async with _client(session) as client:
        response = await client.post(
            "/api/v1/connectors/introspect",
            json={"connection_id": str(world["connection"].connection_id), "schema_name": "public"},
            headers=bearer(world["users"]["VIEWER"]),
        )
    assert response.status_code == 403, response.text


async def test_creating_a_connector_requires_admin(session, world) -> None:
    async with _client(session) as client:
        response = await client.post(
            "/api/v1/connectors",
            json={
                "name": "x",
                "engine": "POSTGRESQL",
                "connection_uri": "postgresql://u:p@h/d",
                "workspace_id": str(world["ws"].workspace_id),
            },
            headers=bearer(world["users"]["MEMBER"]),
        )
    assert response.status_code == 403, response.text


async def test_listing_api_keys_shows_nothing_below_admin(session, world) -> None:
    """A listing narrows to workspaces where the role holds; naming one is a 403."""
    async with _client(session) as client:
        listed = await client.get("/api/v1/auth/api-keys", headers=bearer(world["users"]["MEMBER"]))
        named = await client.get(
            "/api/v1/auth/api-keys",
            params={"workspace_id": str(world["ws"].workspace_id)},
            headers=bearer(world["users"]["MEMBER"]),
        )
    assert (listed.status_code, listed.json()) == (200, [])
    assert named.status_code == 403


async def test_reading_the_audit_trail_requires_admin(session, world) -> None:
    async with _client(session) as client:
        response = await client.get(
            "/api/v1/audit/events",
            params={"workspace_id": str(world["ws"].workspace_id)},
            headers=bearer(world["users"]["MEMBER"]),
        )
    assert response.status_code == 403


async def test_an_anonymous_caller_is_refused(session, world) -> None:
    async with _client(session) as client:
        response = await client.get("/api/v1/model")
    assert response.status_code == 401


# --- Negative control --------------------------------------------------------


async def _membership_only(model_id: uuid.UUID, session: SessionDep) -> DataModel:
    """The shape the guard replaced: the model loads, and the role is never read."""
    model = await session.get(DataModel, model_id)
    assert model is not None
    return model


async def test_negative_control_without_the_member_check_a_viewer_gets_through(
    session, world
) -> None:
    async with _client(session, {require_model_role("MEMBER"): _membership_only}) as client:
        status = await _transform_status(client, world, "VIEWER")
    assert status != 403
    assert status == 200
