"""Shared FastAPI dependencies for the v1 API.

Assembles service classes with their injected async session + LLM gateway so
route handlers receive fully-constructed engines and stay logic-free. Also
hosts the authentication + workspace-authorization dependencies (Slice 3A).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import TokenError, decode_access_token
from app.models.metadata_store import (
    DataModel,
    User,
    Workspace,
    WorkspaceMember,
)
from app.services.exporter_service import ExporterService
from app.services.llm_gateway import LLMGateway, get_llm_gateway
from app.services.paradigm_translator import ParadigmTranslator
from app.services.synthesis_engine import SynthesisEngine

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
GatewayDep = Annotated[LLMGateway, Depends(get_llm_gateway)]


# ---------------------------------------------------------------------------
# Service providers
# ---------------------------------------------------------------------------
def get_synthesis_engine(
    session: SessionDep, gateway: GatewayDep
) -> SynthesisEngine:
    """Provide a request-scoped :class:`SynthesisEngine`."""
    return SynthesisEngine(session, gateway)


def get_paradigm_translator(
    session: SessionDep, gateway: GatewayDep
) -> ParadigmTranslator:
    """Provide a request-scoped :class:`ParadigmTranslator`."""
    return ParadigmTranslator(session, gateway)


def get_exporter_service() -> ExporterService:
    """Provide a stateless :class:`ExporterService`."""
    return ExporterService()


SynthesisEngineDep = Annotated[SynthesisEngine, Depends(get_synthesis_engine)]
ParadigmTranslatorDep = Annotated[
    ParadigmTranslator, Depends(get_paradigm_translator)
]
ExporterServiceDep = Annotated[ExporterService, Depends(get_exporter_service)]


# ---------------------------------------------------------------------------
# Authentication & workspace authorization (Slice 3A)
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> User:
    """Resolve the authenticated user from a Bearer JWT (401 on failure)."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise unauthorized from exc

    subject = payload.get("sub")
    if not subject:
        raise unauthorized
    try:
        user_id = uuid.UUID(str(subject))
    except ValueError as exc:
        raise unauthorized from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_membership(
    session: AsyncSession, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> WorkspaceMember:
    """Return the caller's membership in ``workspace_id`` or raise 403."""
    member = (
        await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace.",
        )
    return member


async def resolve_user_workspace(
    session: AsyncSession, user: User, workspace_id: uuid.UUID | None
) -> uuid.UUID:
    """Resolve the workspace for a write op, enforcing/creating membership.

    If ``workspace_id`` is given, membership is required. Otherwise the user's
    first workspace is used, or a personal one is created (as OWNER).
    """
    if workspace_id is not None:
        await require_membership(session, user.user_id, workspace_id)
        return workspace_id

    existing = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.user_id == user.user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.workspace_id

    workspace = Workspace(name=f"{user.email}'s Workspace")
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
    return workspace.workspace_id


async def get_authorized_model(
    model_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> DataModel:
    """Load a model and assert the caller is a member of its workspace.

    Raises 404 if the model is absent, 403 if the caller lacks access.
    """
    model = await session.get(DataModel, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found.",
        )
    await require_membership(session, user.user_id, model.workspace_id)
    return model


AuthorizedModelDep = Annotated[DataModel, Depends(get_authorized_model)]

# Role hierarchy for RBAC: OWNER > ADMIN > MEMBER (Slice B2).
_ROLE_LEVEL: dict[str, int] = {"MEMBER": 1, "ADMIN": 2, "OWNER": 3}


def require_model_role(min_role: str):
    """Dependency factory: authorize a model route by minimum workspace role.

    Builds on :func:`get_authorized_model` (404/membership) and additionally
    enforces the caller's role meets ``min_role`` (403 otherwise).
    """

    async def _checker(
        model: AuthorizedModelDep, session: SessionDep, user: CurrentUserDep
    ) -> DataModel:
        member = await require_membership(session, user.user_id, model.workspace_id)
        if _ROLE_LEVEL.get(member.role, 0) < _ROLE_LEVEL.get(min_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires minimum role of {min_role}.",
            )
        return model

    return _checker
