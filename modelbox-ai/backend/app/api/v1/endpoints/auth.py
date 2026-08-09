"""Authentication endpoints — local token issuance & registration (Slice 3B).

Provides a standard OAuth2 password flow for local/dev use. Enterprise
deployments continue to present RS256/OIDC tokens, which the same
``get_current_user`` verification path accepts unchanged.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.v1.dependencies import CurrentUserDep, SessionDep
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.metadata_store import User, Workspace, WorkspaceMember
from app.schemas.data_model import RegisterRequest, Token, UserOut

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
