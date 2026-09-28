"""ModelBox Trainer endpoints (Pillar 3) — isolated /api/v1/trainer/* router."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.v1.dependencies import (
    CurrentUserDep,
    GatewayDep,
    SessionDep,
    require_body_workspace_role,
    require_listed_workspaces,
    require_resource_role,
)
from app.models.metadata_store import TrainerAssignment
from app.schemas.data_model import (
    AssignmentCreateRequest,
    AssignmentInfo,
    GradeRequest,
    GradeResponse,
    SocraticStepRequest,
    SocraticStepResponse,
)
from app.services.trainer_service import TrainerService

router = APIRouter(prefix="/trainer", tags=["trainer"])

# Reading an assignment is VIEWER; working on one (the tutor calls a model
# provider, grading records a result) is MEMBER.
AssignmentFromPath = Annotated[
    TrainerAssignment,
    Depends(require_resource_role("VIEWER", TrainerAssignment, "assignment_id", "path")),
]
AssignmentFromBody = Annotated[
    TrainerAssignment,
    Depends(require_resource_role("MEMBER", TrainerAssignment, "assignment_id", "body")),
]


@router.post(
    "/assignments",
    response_model=AssignmentInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create a data-modeling assignment",
)
async def create_assignment(
    payload: AssignmentCreateRequest,
    session: SessionDep,
    user: CurrentUserDep,
    workspace_id: Annotated[uuid.UUID, Depends(require_body_workspace_role("MEMBER"))],
) -> AssignmentInfo:
    assignment = await TrainerService(session).create_assignment(
        user, payload, workspace_id
    )
    return AssignmentInfo.model_validate(assignment)


@router.get(
    "/assignments",
    response_model=list[AssignmentInfo],
    summary="List assignments in the caller's workspaces",
)
async def list_assignments(
    session: SessionDep,
    ws_ids: Annotated[list[uuid.UUID], Depends(require_listed_workspaces("VIEWER"))],
) -> list[AssignmentInfo]:
    if not ws_ids:
        return []
    rows = (
        await session.execute(
            select(TrainerAssignment)
            .where(TrainerAssignment.workspace_id.in_(ws_ids))
            .order_by(TrainerAssignment.created_at.desc())
        )
    ).scalars().all()
    return [AssignmentInfo.model_validate(a) for a in rows]


@router.get(
    "/assignments/{assignment_id}",
    response_model=AssignmentInfo,
    summary="Fetch an assignment",
)
async def get_assignment(
    assignment_id: uuid.UUID, assignment: AssignmentFromPath
) -> AssignmentInfo:
    return AssignmentInfo.model_validate(assignment)


@router.post(
    "/socratic/step",
    response_model=SocraticStepResponse,
    summary="Get the tutor's next guiding question",
)
async def socratic_step(
    payload: SocraticStepRequest,
    session: SessionDep,
    user: CurrentUserDep,
    gateway: GatewayDep,
    assignment: AssignmentFromBody,
) -> SocraticStepResponse:
    return await TrainerService(session, gateway).socratic_step(
        payload,
        user_id=user.user_id,
        workspace_id=assignment.workspace_id,
    )


@router.post(
    "/grade",
    response_model=GradeResponse,
    summary="Auto-grade a student ERD against expected invariants",
)
async def grade_submission(
    payload: GradeRequest,
    session: SessionDep,
    user: CurrentUserDep,
    assignment: AssignmentFromBody,
) -> GradeResponse:
    return await TrainerService(session).grade(
        assignment, payload.submitted_graph, user
    )
