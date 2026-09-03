"""SCIM 2.0 user provisioning and de-provisioning (G9).

Entra, Okta and Ping all push user lifecycle over SCIM, and the half that gets
audited is **de-provisioning**: a leaver losing access is the control, and their
arrival is merely convenient. So the endpoints an IdP calls to remove somebody
are the ones tested hardest here.

**De-provisioning deactivates; it does not delete.** `DELETE /Users/{id}` sets
`is_active = False` and revokes the user's API keys, and the row stays. Deleting
would cascade the user's audit attribution into nothing — which is exactly
backwards, because a departure is the moment somebody wants to read what that
person did. The audit trail already survives a deleted user by copying the
email, but there is no reason to make it lean on that when deactivation answers
the IdP's question completely.

**Revocation has to be immediate on both credentials, and that is not free.**
Deactivating a user stops bearer tokens because `get_current_user` re-reads the
row on every request. It also stops API keys, because `_user_from_api_key`
checks `is_active` — verified rather than assumed, since an API key that
outlives its owner's deactivation is the exact hole a leaver-control exists to
close. The keys are revoked as well, so the credential is gone rather than
merely inert.

**Authenticated by a dedicated token, and disabled without one.** `scim_token`
is unset by default, which turns these routes off. An unauthenticated
user-provisioning API is a way to create administrators, and the credential is
kept separate from every human login because it lives in an IdP's configuration
and must be revocable on its own.

This is a deliberate subset of RFC 7644: Users only, no Groups, no bulk, no
complex filters. `filter=userName eq "..."` is supported because that is the
call every IdP makes before deciding whether to create; the rest would be
surface nobody has asked for.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select

from app.api.v1.dependencies import SessionDep
from app.core.config import get_settings
from app.models.metadata_store import ApiKey, User
from app.services import audit_log

router = APIRouter(prefix="/scim/v2", tags=["scim"])

_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


async def require_scim_token(request: Request) -> None:
    """Authorise a SCIM call, or refuse.

    Compared with `secrets.compare_digest`, because a token check that returns
    early on the first wrong byte leaks its length and prefix to anyone willing
    to measure. The cost is nothing and the alternative is a timing oracle on a
    credential that can create users.
    """
    configured = get_settings().scim_token
    if not configured:
        # Not 401: nothing is wrong with the caller's credential. The feature is
        # switched off, and saying so is more useful than implying a bad token.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SCIM is not enabled on this appliance.",
        )
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        presented, configured
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SCIM credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )


ScimAuth = Depends(require_scim_token)


def _as_scim(user: User) -> dict[str, Any]:
    return {
        "schemas": [_USER_SCHEMA],
        "id": str(user.user_id),
        "userName": user.email,
        "name": {"formatted": user.full_name} if user.full_name else {},
        "emails": [{"value": user.email, "primary": True}],
        "active": user.is_active,
        "meta": {"resourceType": "User"},
    }


def _username_from_filter(expression: str | None) -> str | None:
    """Extract the value from `userName eq "x"`, the only filter supported.

    Anything else returns None and the caller reports an empty list rather than
    guessing. A filter that is silently ignored would make an IdP believe no
    such user exists and create a duplicate on every sync.
    """
    if not expression:
        return None
    parts = expression.strip().split(None, 2)
    if len(parts) != 3 or parts[0].lower() != "username" or parts[1].lower() != "eq":
        return None
    return parts[2].strip().strip('"')


@router.get("/Users", dependencies=[ScimAuth], summary="List or filter users")
async def list_users(
    session: SessionDep,
    filter: Annotated[str | None, Query(alias="filter")] = None,
) -> dict[str, Any]:
    username = _username_from_filter(filter)
    stmt = select(User)
    if filter is not None:
        if username is None:
            # An unsupported filter returns nothing rather than everything.
            # Returning everything is how an IdP concludes a user exists,
            # skips creation, and leaves somebody unable to sign in.
            return {"schemas": [_LIST_SCHEMA], "totalResults": 0, "Resources": []}
        stmt = stmt.where(User.email == username)

    rows = (await session.execute(stmt)).scalars().all()
    return {
        "schemas": [_LIST_SCHEMA],
        "totalResults": len(rows),
        "Resources": [_as_scim(u) for u in rows],
    }


@router.get("/Users/{user_id}", dependencies=[ScimAuth], summary="Read one user")
async def read_user(user_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"schemas": [_ERROR_SCHEMA], "status": "404"},
        )
    return _as_scim(user)


@router.post(
    "/Users",
    dependencies=[ScimAuth],
    status_code=status.HTTP_201_CREATED,
    summary="Provision a user",
)
async def create_user(payload: dict[str, Any], session: SessionDep) -> dict[str, Any]:
    """Create a user, or return the existing one for the same userName.

    **Returns 409 on a duplicate rather than creating a second row.** SCIM
    clients retry, and an IdP that loses a response will replay the create — so
    a provisioning endpoint that is not idempotent-safe manufactures duplicate
    accounts during exactly the network conditions that made it retry.
    """
    username = (payload.get("userName") or "").strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"schemas": [_ERROR_SCHEMA], "detail": "userName is required"},
        )

    existing = (
        await session.execute(select(User).where(User.email == username))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "schemas": [_ERROR_SCHEMA],
                "detail": "User already exists",
                "status": "409",
            },
        )

    name = payload.get("name") or {}
    user = User(
        email=username,
        full_name=name.get("formatted") or payload.get("displayName"),
        # No password. A SCIM-provisioned account signs in through the IdP that
        # provisioned it; giving it a local credential would create a way in
        # that de-provisioning does not close.
        hashed_password=None,
        is_active=bool(payload.get("active", True)),
    )
    session.add(user)
    await session.flush()

    await audit_log.record(
        action="USER_PROVISIONED",
        actor_email=username,
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=str(user.user_id),
        detail={"via": "scim"},
    )
    return _as_scim(user)


async def _deactivate(session: SessionDep, user: User) -> None:
    """Deactivate and revoke, which is what de-provisioning has to mean.

    Both halves are required. Clearing `is_active` stops bearer tokens because
    every request re-reads the row, and stops API keys because
    `_user_from_api_key` checks the same flag — but leaving the key rows behind
    means the credential still exists and would work again the moment somebody
    reactivated the account. Revoking makes the removal a removal.
    """
    user.is_active = False
    await session.execute(delete(ApiKey).where(ApiKey.user_id == user.user_id))
    await session.flush()
    await audit_log.record(
        action="USER_DEPROVISIONED",
        actor_email=user.email,
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=str(user.user_id),
        detail={"via": "scim"},
    )


@router.patch("/Users/{user_id}", dependencies=[ScimAuth], summary="Update a user")
async def patch_user(
    user_id: uuid.UUID, payload: dict[str, Any], session: SessionDep
) -> dict[str, Any]:
    """Apply a SCIM PATCH. The operation that matters is `active` -> false.

    Every IdP de-provisions this way by default — soft-disable rather than
    DELETE — so an implementation that only handles DELETE passes a manual test
    and never fires in production.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"schemas": [_ERROR_SCHEMA], "status": "404"},
        )

    for operation in payload.get("Operations", []):
        if str(operation.get("op", "")).lower() not in {"replace", "add"}:
            continue
        value = operation.get("value")
        path = str(operation.get("path") or "").lower()

        # Both shapes an IdP sends: {"path": "active", "value": false} and
        # {"value": {"active": false}}. Handling one is how this silently stops
        # working against half the providers.
        active: bool | None = None
        if path == "active":
            active = _as_bool(value)
        elif isinstance(value, dict) and "active" in value:
            active = _as_bool(value["active"])

        if active is False:
            await _deactivate(session, user)
        elif active is True:
            user.is_active = True
            await session.flush()

    return _as_scim(user)


@router.delete(
    "/Users/{user_id}",
    dependencies=[ScimAuth],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="De-provision a user",
)
async def delete_user(user_id: uuid.UUID, session: SessionDep) -> Response:
    """Deactivate and revoke. The row stays — see the module docstring."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"schemas": [_ERROR_SCHEMA], "status": "404"},
        )
    await _deactivate(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return None
