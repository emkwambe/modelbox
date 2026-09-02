"""Resolving an external IdP subject to a local user (G8).

Before this, `get_current_user` required the token's `sub` claim to be a UUID
naming a row that already existed. An IdP's subject is an opaque provider string
— Okta's `00u1a2b3…`, Entra's own GUID — so a perfectly signed, correctly
audienced token from a real identity provider was rejected with 401 unless
somebody had hand-created a local user whose primary key happened to equal it.
SSO was configurable and could not work.

Three rulings, and each has a plausible-looking opposite that is a security
defect rather than a preference.

**Identity is keyed on (issuer, subject), never on email.** Matching on email is
the obvious implementation and it is unsafe: addresses are mutable, and
organisations *recycle* them when people leave. An email-keyed link eventually
hands a new joiner the previous holder's account and every workspace it belonged
to. `sub` is the only identifier OIDC promises is stable and unique within an
issuer.

**Provisioning is gated on an issuer allowlist.** Signature validity proves a
token came from a key holder, not that its holder should have an account here.
Without an allowlist, any principal an accepted IdP will sign for — every other
tenant of a shared provider, every service account, every guest — creates a user
on first contact. `oidc_allowed_issuers` is empty by default, which means
just-in-time provisioning is **off** until somebody names an issuer.

**A provisioned user gets no workspace membership.** This is the ruling most
likely to be argued with, so it is worth stating: authentication is not
authorisation. Auto-joining a default workspace would mean that anyone the IdP
will authenticate can read whatever that workspace holds, which converts an
identity decision into an access grant nobody made. A new federated user can
sign in and see nothing until an admin adds them — which is the same position a
locally registered user is in, and the one an auditor expects.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.metadata_store import FederatedIdentity, User
from app.services import audit_log

logger = logging.getLogger(__name__)


def issuer_is_allowed(issuer: str | None) -> bool:
    """Whether ``issuer`` may provision users here.

    Empty allowlist means no, deliberately — the fail-closed default. A
    deployment that has configured an RS256 key but not named its issuer has
    said what it trusts to *sign*, not what it trusts to *enrol*.
    """
    if not issuer:
        return False
    allowed = get_settings().oidc_allowed_issuers
    return bool(allowed) and issuer in allowed


async def resolve(
    session: AsyncSession, claims: dict[str, object]
) -> User | None:
    """Return the local user for a verified token's claims, provisioning if allowed.

    Returns ``None`` when the caller cannot be resolved, so the dependency
    raises its own 401 and this module never decides how to fail.
    """
    issuer = str(claims.get("iss") or "") or None
    subject = str(claims.get("sub") or "") or None
    if not subject:
        return None

    # A local HS256 token carries this service's own user id as `sub`, and no
    # federation is involved. Tried first so the common path costs one lookup.
    try:
        local_id = uuid.UUID(subject)
    except ValueError:
        local_id = None
    if local_id is not None:
        user = await session.get(User, local_id)
        if user is not None:
            return user

    if issuer is None:
        return None

    link = (
        await session.execute(
            select(FederatedIdentity).where(
                FederatedIdentity.issuer == issuer,
                FederatedIdentity.subject == subject,
            )
        )
    ).scalar_one_or_none()

    if link is not None:
        user = await session.get(User, link.user_id)
        if user is not None and user.is_active:
            # Refresh the display email if the provider's has changed. The link
            # is unaffected — this is why the key is not the email.
            email = _email_from(claims)
            if email and user.email != email:
                user.email = email
            return user
        return None

    if not issuer_is_allowed(issuer):
        logger.warning(
            "Refusing to provision a user for unlisted issuer %r. "
            "Add it to MODELBOX_OIDC_ALLOWED_ISSUERS to enable SSO for it.",
            issuer,
        )
        return None

    email = _email_from(claims)
    if not email:
        # No email claim, no account. A user with no address cannot be named in
        # an audit trail, cannot be found by an admin adding them to a
        # workspace, and cannot be told apart from the next such user.
        logger.warning("Refusing to provision: token from %r carries no email", issuer)
        return None

    # A recycled address, and the one case where refusing is the only safe
    # answer. `users.email` is UNIQUE, so an existing row holding this address
    # leaves exactly three options: link the new subject to the old account —
    # which is the email-keyed inheritance this module exists to prevent, and
    # hands a joiner the leaver's workspaces; crash on the constraint, which is
    # a 500 nobody can act on; or refuse and say why.
    #
    # Refusing is not a limitation to apologise for. Two identities claiming one
    # address is a genuine ambiguity in the *organisation*, not in this code,
    # and resolving it silently is how the dangerous version of this feature
    # ships. An admin renames or removes the departed account and the next
    # sign-in succeeds.
    clash = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if clash is not None:
        logger.warning(
            "Refusing to provision %s from %s: that address already belongs to "
            "user %s, which is not linked to this subject. An address reused "
            "after a leaver must be reassigned by an admin, never inherited.",
            email,
            issuer,
            clash.user_id,
        )
        await audit_log.record(
            action="AUTH_LOGIN_FAILED",
            outcome="DENIED",
            actor_email=email,
            detail={"reason": "email_already_held", "issuer": issuer},
        )
        return None

    user = User(email=email, full_name=_name_from(claims), hashed_password=None)
    session.add(user)
    await session.flush()
    session.add(
        FederatedIdentity(issuer=issuer, subject=subject, user_id=user.user_id)
    )
    await session.flush()

    await audit_log.record(
        action="AUTH_LOGIN",
        actor_user_id=user.user_id,
        actor_email=user.email,
        detail={"provisioned": True, "issuer": issuer},
    )
    logger.info("Provisioned federated user %s from %s", email, issuer)
    return user


def _email_from(claims: dict[str, object]) -> str | None:
    value = claims.get("email") or claims.get("preferred_username")
    return str(value) if value else None


def _name_from(claims: dict[str, object]) -> str | None:
    value = claims.get("name")
    return str(value) if value else None
