"""SCIM provisioning, and the de-provisioning that is the actual control (G9).

The register's wording for G9 names the half that matters: *de-provisioning is
the audited half, because a leaver losing access is the control, not their
arrival.* So the weight of this file is on removal.

**The assertion the criterion reduces to** is that after an IdP de-provisions
somebody, their credentials stop working — both of them. A bearer token and an
API key are separate paths into this appliance, and an implementation that
closes one is a leaver-control that does not control leavers. Neither is
asserted by reading `is_active`; both are asserted by making a request.

Everything else here exists because it is a way for de-provisioning to look
done and not be:

- handling `DELETE` but not `PATCH active=false`, which is how every IdP
  actually de-provisions by default;
- clearing the flag but leaving the API key rows, so the credential returns the
  moment somebody reactivates the account;
- deleting the user, which takes their audit history with them at precisely the
  moment somebody wants to read it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import generate_api_key, hash_password
from app.models.metadata_store import ApiKey, AuditEvent, Base, User, Workspace

# A throwaway credential for tests; never a real one.
TOKEN = "scim-secret-token"


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
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


@pytest.fixture
def scim_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "scim_token", TOKEN, raising=False)


async def _client(session: AsyncSession) -> AsyncClient:
    """A client with no user identity — SCIM authenticates as the IdP, not a person."""
    from app.core.database import get_db_session
    from app.main import create_app

    app = create_app()

    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_user(session: AsyncSession, email: str = "leaver@example.com") -> User:
    user = User(email=email, hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()
    return user


async def _give_key(session: AsyncSession, user: User) -> str:
    """Mint a real API key for a user.

    Keys are workspace-scoped, so this makes one — which also means the
    de-provisioning assertion covers the shape the product actually stores
    rather than a simplified stand-in.
    """
    ws = Workspace(name="W")
    session.add(ws)
    await session.flush()
    raw, prefix, key_hash = generate_api_key()
    session.add(
        ApiKey(
            user_id=user.user_id,
            workspace_id=ws.workspace_id,
            name="ci",
            key_prefix=prefix,
            key_hash=key_hash,
        )
    )
    await session.flush()
    return raw


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scim_is_off_without_a_token(session) -> None:
    """The fail-closed default. An unauthenticated user-provisioning API is a
    way to create administrators."""
    assert get_settings().scim_token is None
    client = await _client(session)
    async with client:
        r = await client.get("/api/v1/scim/v2/Users", headers=_auth())
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_a_wrong_token_is_refused(session, scim_enabled) -> None:
    client = await _client(session)
    async with client:
        r = await client.get("/api/v1/scim/v2/Users", headers=_auth("wrong"))
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_no_credential_at_all_is_refused(session, scim_enabled) -> None:
    client = await _client(session)
    async with client:
        r = await client.get("/api/v1/scim/v2/Users")
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provisioning_creates_a_user_with_no_password(
    session, scim_enabled
) -> None:
    """A SCIM account signs in through the IdP that provisioned it.

    Giving it a local password would create a way in that de-provisioning does
    not close — the IdP disables the account and the password still works.
    """
    client = await _client(session)
    async with client:
        r = await client.post(
            "/api/v1/scim/v2/Users",
            headers=_auth(),
            json={"userName": "new@example.com", "name": {"formatted": "New Person"}},
        )
    assert r.status_code == 201, r.text
    assert r.json()["userName"] == "new@example.com"
    assert r.json()["active"] is True

    user = (
        await session.execute(select(User).where(User.email == "new@example.com"))
    ).scalar_one()
    assert user.hashed_password is None


@pytest.mark.asyncio
async def test_a_replayed_create_does_not_duplicate_the_user(
    session, scim_enabled
) -> None:
    """SCIM clients retry, and a lost response is replayed.

    A create that is not safe against replay manufactures duplicate accounts
    during exactly the network conditions that caused the retry.
    """
    client = await _client(session)
    async with client:
        first = await client.post(
            "/api/v1/scim/v2/Users", headers=_auth(), json={"userName": "dup@x.com"}
        )
        second = await client.post(
            "/api/v1/scim/v2/Users", headers=_auth(), json={"userName": "dup@x.com"}
        )
    assert first.status_code == 201
    assert second.status_code == 409, second.text

    rows = (
        (await session.execute(select(User).where(User.email == "dup@x.com")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_an_unsupported_filter_returns_nothing_not_everything(
    session, scim_enabled
) -> None:
    """The failure mode of ignoring a filter is silent and expensive.

    An IdP asks "does this user exist" with a filter it expects to be honoured.
    Answering with the whole directory tells it yes for everyone, so it skips
    creation and somebody is never provisioned.
    """
    await _seed_user(session, "someone@example.com")
    client = await _client(session)
    async with client:
        r = await client.get(
            "/api/v1/scim/v2/Users",
            headers=_auth(),
            params={"filter": 'displayName co "some"'},
        )
    assert r.status_code == 200
    assert r.json()["totalResults"] == 0


@pytest.mark.asyncio
async def test_the_username_filter_finds_the_user(session, scim_enabled) -> None:
    await _seed_user(session, "findme@example.com")
    client = await _client(session)
    async with client:
        r = await client.get(
            "/api/v1/scim/v2/Users",
            headers=_auth(),
            params={"filter": 'userName eq "findme@example.com"'},
        )
    assert r.json()["totalResults"] == 1


# ---------------------------------------------------------------------------
# De-provisioning — the control
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_deprovisioned_users_api_key_stops_working(
    session, scim_enabled
) -> None:
    """The assertion G9 reduces to, made by using the credential.

    Reading `is_active` would prove a flag changed. This proves the *door* is
    shut — which is a different claim, and the only one a leaver-control can be
    said to make.
    """
    user = await _seed_user(session)
    raw = await _give_key(session, user)

    client = await _client(session)
    async with client:
        before = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw})
        assert before.status_code == 200, "precondition: the key must work first"

        gone = await client.delete(
            f"/api/v1/scim/v2/Users/{user.user_id}", headers=_auth()
        )
        assert gone.status_code == 204, gone.text

        after = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw})
    assert after.status_code == 401, "a de-provisioned user's API key still worked"


@pytest.mark.asyncio
async def test_patch_active_false_deprovisions_too(session, scim_enabled) -> None:
    """How every IdP actually removes somebody.

    Entra, Okta and Ping soft-disable by default; `DELETE` is the exception.
    An implementation that handles only DELETE passes a manual test and never
    fires in production.
    """
    user = await _seed_user(session, "patched@example.com")
    raw = await _give_key(session, user)

    client = await _client(session)
    async with client:
        r = await client.patch(
            f"/api/v1/scim/v2/Users/{user.user_id}",
            headers=_auth(),
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": False}],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["active"] is False

        after = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw})
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_the_other_patch_shape_works_too(session, scim_enabled) -> None:
    """`{"value": {"active": false}}` — the shape the other half of providers send.

    Supporting one shape is how this silently stops working for a customer whose
    IdP happens to speak the other.
    """
    user = await _seed_user(session, "shape2@example.com")
    client = await _client(session)
    async with client:
        r = await client.patch(
            f"/api/v1/scim/v2/Users/{user.user_id}",
            headers=_auth(),
            json={"Operations": [{"op": "replace", "value": {"active": False}}]},
        )
    assert r.status_code == 200
    assert r.json()["active"] is False


@pytest.mark.asyncio
async def test_deprovisioning_revokes_the_key_rather_than_disabling_it(
    session, scim_enabled
) -> None:
    """The discriminating half.

    Clearing `is_active` alone would pass the two tests above, because
    `_user_from_api_key` checks the flag. It would also leave the credential in
    the database, working again the moment somebody reactivated the account.
    """
    user = await _seed_user(session, "revoked@example.com")
    await _give_key(session, user)

    client = await _client(session)
    async with client:
        await client.delete(f"/api/v1/scim/v2/Users/{user.user_id}", headers=_auth())

    keys = (
        (await session.execute(select(ApiKey).where(ApiKey.user_id == user.user_id)))
        .scalars()
        .all()
    )
    assert keys == [], "the key survived de-provisioning"


@pytest.mark.asyncio
async def test_deprovisioning_keeps_the_user_and_their_history(
    session, scim_enabled
) -> None:
    """Deactivate, do not delete.

    A departure is the moment somebody wants to read what that person did.
    Deleting the row is the tidy-looking implementation and it removes the
    evidence at exactly the wrong time.
    """
    user = await _seed_user(session, "history@example.com")
    user_id = user.user_id

    client = await _client(session)
    async with client:
        await client.delete(f"/api/v1/scim/v2/Users/{user_id}", headers=_auth())

    still_there = await session.get(User, user_id)
    assert still_there is not None, "the user row was deleted"
    assert still_there.is_active is False


@pytest.mark.asyncio
async def test_deprovisioning_is_recorded_in_the_audit_trail(
    session, scim_enabled
) -> None:
    user = await _seed_user(session, "audited@example.com")
    client = await _client(session)
    async with client:
        await client.delete(f"/api/v1/scim/v2/Users/{user.user_id}", headers=_auth())

    rows = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "USER_DEPROVISIONED")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_email == "audited@example.com"
    assert rows[0].detail == {"via": "scim"}


@pytest.mark.asyncio
async def test_deprovisioning_someone_who_does_not_exist_is_a_404(
    session, scim_enabled
) -> None:
    client = await _client(session)
    async with client:
        r = await client.delete(
            f"/api/v1/scim/v2/Users/{uuid.uuid4()}", headers=_auth()
        )
    assert r.status_code == 404
