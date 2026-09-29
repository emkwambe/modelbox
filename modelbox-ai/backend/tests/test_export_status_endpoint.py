"""The export surface is served its status, not left to invent one (F5).

The manifest in `app.services.artifact_status` is the single source: the
fidelity harness derives its dialect lists and `preview` markers from it, and
this endpoint serves the same rows to the UI. These tests pin the contract
between those two consumers, because a manifest that only one of them reads is
back to two sources of truth wearing one name.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.artifact_status import (
    ARTIFACT_STATUS,
    ArtifactStatus,
    certified_dialects,
    preview_dialects,
)
from tests._real_auth import bearer, make_user, real_client, sqlite_session


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Signed in with a real token: the route requires sign-in (Sprint 7)."""
    user = await make_user(session, "reader@example.com")
    await session.commit()
    async with real_client(session) as c:
        c.headers.update(bearer(user))
        yield c


@pytest.mark.asyncio
async def test_the_endpoint_reports_the_manifest(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/export/status")).json()

    assert len(body) == len(ARTIFACT_STATUS)
    served = {row["variant"]: row for row in body}
    for entry in ARTIFACT_STATUS:
        row = served[entry.variant]
        assert row["status"] == entry.status.value
        assert row["family"] == entry.family
        assert row["reason"] == entry.reason


@pytest.mark.asyncio
async def test_every_row_carries_a_reason(client: AsyncClient) -> None:
    """A status with no reason is a label, and a label is what this replaced.

    The point of serving this at all is that a user can find out *why* an
    artifact is preview rather than only that it is.
    """
    body = (await client.get("/api/v1/export/status")).json()
    thin = [r["variant"] for r in body if len(r["reason"].strip()) < 20]
    assert not thin, f"these variants carry no usable reason: {thin}"


@pytest.mark.asyncio
async def test_it_requires_sign_in(session: AsyncSession) -> None:
    """Default deny (Sprint 7): it describes the build, but nothing needs it anonymously.

    Its only caller is the export panel, which works only for a signed-in user.
    """
    async with real_client(session) as anonymous:
        assert (await anonymous.get("/api/v1/export/status")).status_code == 401


def test_the_dialect_helpers_agree_with_the_manifest() -> None:
    """The harness reads these helpers; the endpoint reads the entries."""
    from_entries = {
        e.variant
        for e in ARTIFACT_STATUS
        if e.family == "ddl" and e.status is ArtifactStatus.CERTIFIED
    }
    assert set(certified_dialects()) == from_entries
    assert not set(certified_dialects()) & set(preview_dialects())
    assert from_entries, "fixture sanity: no certified dialects in the manifest"
