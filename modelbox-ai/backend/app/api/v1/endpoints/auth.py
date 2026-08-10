"""Authentication endpoints — local token issuance & registration (Slice 3B).

Provides a standard OAuth2 password flow for local/dev use. Enterprise
deployments continue to present RS256/OIDC tokens, which the same
``get_current_user`` verification path accepts unchanged.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_workspace_role,
    resolve_user_workspace,
)
from app.core.security import (
    create_access_token,
    generate_api_key,
    hash_password,
    verify_password,
)
from app.models.metadata_store import ApiKey, User, Workspace, WorkspaceMember
from app.schemas.data_model import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyInfo,
    RegisterRequest,
    Token,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token, summary="Obtain an access token")
async def login_for_access_token(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """OAuth2 password grant: email (username) + password -> bearer token."""
    user = (
        await session.execute(
            select(User).where(User.email == form_data.username)
        )
    ).scalar_one_or_none()

    if (
        user is None
        or not user.hashed_password
        or not verify_password(form_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(str(user.user_id)))


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Register a local account and personal workspace",
)
async def register(payload: RegisterRequest, session: SessionDep) -> Token:
    """Create a user + personal workspace (as OWNER) and return a token."""
    existing = (
        await session.execute(
            select(User).where(User.email == payload.email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    session.add(user)
    await session.flush()

    workspace = Workspace(name=f"{payload.email}'s Workspace")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id,
            user_id=user.user_id,
            role="OWNER",
        )
    )
    await session.flush()

    return Token(access_token=create_access_token(str(user.user_id)))


@router.get("/me", response_model=UserOut, summary="Current authenticated user")
async def read_me(user: CurrentUserDep) -> UserOut:
    """Return the profile of the authenticated caller."""
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# API keys (programmatic access for CI/CD & agents)
# ---------------------------------------------------------------------------
@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key (ADMIN+); returns the secret ONCE",
)
async def create_api_key(
    payload: ApiKeyCreateRequest, session: SessionDep, user: CurrentUserDep
) -> ApiKeyCreatedResponse:
    """Mint a workspace API key. The plaintext secret is shown once here."""
    workspace_id = await resolve_user_workspace(
        session, user, payload.workspace_id
    )
    await require_workspace_role(session, user.user_id, workspace_id, "ADMIN")

    plaintext, prefix, key_hash = generate_api_key()
    record = ApiKey(
        workspace_id=workspace_id,
        user_id=user.user_id,
        name=payload.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=payload.expires_at,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)  # populate server-side created_at

    return ApiKeyCreatedResponse(
        api_key=plaintext, **ApiKeyInfo.model_validate(record).model_dump()
    )


@router.get(
    "/api-keys",
    response_model=list[ApiKeyInfo],
    summary="List API keys in the caller's workspaces (no secrets)",
)
async def list_api_keys(
    session: SessionDep, user: CurrentUserDep
) -> list[ApiKeyInfo]:
    """List key metadata for the caller's workspaces (never the secret/hash)."""
    rows = (
        await session.execute(
            select(ApiKey)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == ApiKey.workspace_id,
            )
            .where(WorkspaceMember.user_id == user.user_id)
            .order_by(ApiKey.created_at.desc())
        )
    ).scalars().all()
    return [ApiKeyInfo.model_validate(row) for row in rows]


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key (ADMIN+)",
)
async def revoke_api_key(
    key_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> Response:
    """Revoke (delete) an API key. Requires ADMIN+ in its workspace."""
    record = await session.get(ApiKey, key_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found.",
        )
    await require_workspace_role(
        session, user.user_id, record.workspace_id, "ADMIN"
    )
    await session.delete(record)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
