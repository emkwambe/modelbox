"""Workspace listing endpoint (RBAC — Slice B2)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.v1.dependencies import CurrentUserDep, SessionDep
from app.models.metadata_store import Workspace, WorkspaceMember
from app.schemas.data_model import WorkspaceInfo

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get(
    "",
    response_model=list[WorkspaceInfo],
    summary="List the caller's workspaces and their role in each",
)
async def list_workspaces(
    user: CurrentUserDep, session: SessionDep
) -> list[WorkspaceInfo]:
    """Return every workspace the current user is a member of."""
    rows = (
        await session.execute(
            select(
                Workspace.workspace_id,
                Workspace.name,
                WorkspaceMember.role,
            )
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Workspace.workspace_id,
            )
            .where(WorkspaceMember.user_id == user.user_id)
            .order_by(Workspace.name)
        )
    ).all()
    return [
        WorkspaceInfo(workspace_id=row[0], name=row[1], role=row[2])
        for row in rows
    ]
