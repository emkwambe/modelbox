"""An external IdP subject resolves to a local user, on stated terms (G8).

Token *verification* was already correct and already tested — RS256, with
audience and issuer pinning made mandatory in D9. What did not exist was the
step after it: `get_current_user` required `sub` to be a UUID naming an existing
row, and an OIDC subject is an opaque provider string. So a correctly signed,
correctly audienced token from a real identity provider was rejected with a 401
that looked like a signature problem, and SSO was configurable but unusable.

The tests below are mostly about **refusals**, because every dangerous version
of this feature passes a "the user can sign in" test:

- keyed on email, so a recycled address inherits an account;
- provisioning anyone a trusted IdP will sign for;
- granting the new user a workspace.

Each of those is the obvious implementation, and each is asserted against here.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.metadata_store import (
    Base,
    FederatedIdentity,
    User,
    Workspace,
    WorkspaceMember,
)
from app.services import federated_identity

ISSUER = "https://login.example-idp.com/tenant-1"
OTHER_ISSUER = "https://login.example-idp.com/tenant-2"


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
def allow_issuer(monkeypatch: pytest.MonkeyPatch):
    """Put ISSUER on the allowlist for one test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_allowed_issuers", [ISSUER], raising=False)
    return settings


def _claims(sub: str, *, iss: str = ISSUER, email: str | None = "person@example.com"):
    claims: dict[str, object] = {"sub": sub, "iss": iss}
    if email:
        claims["email"] = email
    return claims


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def test_provisioning_is_off_by_default() -> None:
    """The fail-closed default, asserted rather than assumed.

    A deployment that configured a signing key has said what it trusts to
    *sign*, not what it trusts to *enrol*. If this list defaulted to anything
    non-empty, every principal a shared IdP will sign for — other tenants,
    service accounts, guests — would create an account here on first contact.
    """
    assert get_settings().oidc_allowed_issuers == []
    assert not federated_identity.issuer_is_allowed(ISSUER)
    assert not federated_identity.issuer_is_allowed(None)


@pytest.mark.asyncio
async def test_an_unlisted_issuer_provisions_nobody(session) -> None:
    user = await federated_identity.resolve(session, _claims("00u-abc"))
    assert user is None
    rows = (await session.execute(select(User))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_a_listed_issuer_provisions_on_first_sight(
    session, allow_issuer
) -> None:
    user = await federated_identity.resolve(session, _claims("00u-abc"))
    assert user is not None
    assert user.email == "person@example.com"
    # No local password: this account cannot be signed into with the password
    # form, which is the point of federating it.
    assert user.hashed_password is None


@pytest.mark.asyncio
async def test_the_second_sign_in_reuses_the_same_user(session, allow_issuer) -> None:
    first = await federated_identity.resolve(session, _claims("00u-abc"))
    second = await federated_identity.resolve(session, _claims("00u-abc"))
    assert first is not None and second is not None
    assert first.user_id == second.user_id
    links = (await session.execute(select(FederatedIdentity))).scalars().all()
    assert len(links) == 1


@pytest.mark.asyncio
async def test_a_token_with_no_email_provisions_nobody(session, allow_issuer) -> None:
    """A user with no address cannot be named in an audit trail or found by an
    admin adding them to a workspace, and cannot be told apart from the next
    such user."""
    user = await federated_identity.resolve(
        session, _claims("00u-abc", email=None)
    )
    assert user is None


# ---------------------------------------------------------------------------
# The three dangerous implementations
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recycled_email_does_not_inherit_the_account(
    session, allow_issuer
) -> None:
    """The reason identity is keyed on subject rather than email.

    Organisations recycle addresses when people leave. An email-keyed link
    would return the *departed* user here — with every workspace they belonged
    to — and would pass every other test in this file.
    """
    leaver = await federated_identity.resolve(session, _claims("00u-leaver"))
    assert leaver is not None
    leaver_id = leaver.user_id

    joiner = await federated_identity.resolve(session, _claims("00u-joiner"))

    # **Refused, not silently separated.** This test was first written expecting
    # a second user, and running it found the real constraint: `users.email` is
    # UNIQUE, so the same address cannot produce two accounts. That leaves three
    # options and only one is safe — linking the new subject to the old account
    # is the inheritance this module exists to prevent, crashing on the
    # constraint is a 500 nobody can act on, and refusing states the ambiguity.
    #
    # Two identities claiming one address is a problem in the organisation, not
    # in this code. An admin reassigns it; nobody inherits a workspace.
    assert joiner is None, "a recycled address must not resolve to anybody"

    still_there = await session.get(User, leaver_id)
    assert still_there is not None, "refusing must not disturb the existing user"


@pytest.mark.asyncio
async def test_the_same_subject_from_another_issuer_is_a_different_person(
    session, monkeypatch
) -> None:
    """Subject spaces are per-issuer, and providers reuse formats.

    Keying on `sub` alone would make tenant-2's user 00u-abc the same person as
    tenant-1's.
    """
    settings = get_settings()
    monkeypatch.setattr(
        settings, "oidc_allowed_issuers", [ISSUER, OTHER_ISSUER], raising=False
    )
    a = await federated_identity.resolve(session, _claims("00u-abc", iss=ISSUER))
    b = await federated_identity.resolve(
        session, _claims("00u-abc", iss=OTHER_ISSUER, email="other@example.com")
    )
    assert a is not None and b is not None
    assert a.user_id != b.user_id


@pytest.mark.asyncio
async def test_a_provisioned_user_gets_no_workspace(session, allow_issuer) -> None:
    """Authentication is not authorisation, and this is the assertion that says so.

    Auto-joining a default workspace is the convenient implementation: the new
    user signs in and can immediately do something, which demos well. It also
    means anyone the IdP will authenticate can read whatever that workspace
    holds — an access grant nobody made, arriving as a side effect of an
    identity decision.
    """
    ws = Workspace(name="Existing")
    session.add(ws)
    await session.flush()

    user = await federated_identity.resolve(session, _claims("00u-abc"))
    assert user is not None

    memberships = (
        (
            await session.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == user.user_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert memberships == [], "a provisioned user was granted access to a workspace"


# ---------------------------------------------------------------------------
# Coexistence with local accounts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_local_uuid_subject_still_resolves(session) -> None:
    """The HS256 path this service mints for itself must keep working.

    Local tokens carry the user's own id as `sub`, no federation involved, and
    that path is tried first so the common case costs one lookup.
    """
    local = User(email="local@example.com", hashed_password=hash_password("pw"))
    session.add(local)
    await session.flush()

    found = await federated_identity.resolve(
        session, {"sub": str(local.user_id), "iss": None}
    )
    assert found is not None
    assert found.user_id == local.user_id


@pytest.mark.asyncio
async def test_a_uuid_subject_that_names_nobody_resolves_to_nobody(session) -> None:
    found = await federated_identity.resolve(
        session, {"sub": str(uuid.uuid4()), "iss": None}
    )
    assert found is None


@pytest.mark.asyncio
async def test_a_changed_email_updates_the_user_without_moving_the_link(
    session, allow_issuer
) -> None:
    """People change their name; the account should not change with it.

    The email is display data and audit data, refreshed from the token. The
    link is the subject, so a rename is a field update rather than a new
    account — which is the other half of not keying on email.
    """
    first = await federated_identity.resolve(session, _claims("00u-abc"))
    assert first is not None
    original_id = first.user_id

    again = await federated_identity.resolve(
        session, _claims("00u-abc", email="renamed@example.com")
    )
    assert again is not None
    assert again.user_id == original_id
    assert again.email == "renamed@example.com"
