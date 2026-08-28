"""ModelBox Trainer endpoints (Pillar 3) — isolated /api/v1/trainer/* router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.v1.dependencies import (
    CurrentUserDep,
    GatewayDep,
    SessionDep,
    require_membership,
    resolve_user_workspace,
)
from app.models.metadata_store import TrainerAssignment, WorkspaceMember
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


async def _load_assignment(
    session: SessionDep, user: CurrentUserDep, assignment_id: uuid.UUID
) -> TrainerAssignment:
    assignment = await session.get(TrainerAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found.",
        )
    await require_membership(session, user.user_id, assignment.workspace_id)
    return assignment


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
) -> AssignmentInfo:
    workspace_id = await resolve_user_workspace(
        session, user, payload.workspace_id
    )
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
    session: SessionDep, user: CurrentUserDep
) -> list[AssignmentInfo]:
    rows = (
        await session.execute(
            select(TrainerAssignment)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == TrainerAssignment.workspace_id,
            )
            .where(WorkspaceMember.user_id == user.user_id)
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
    assignment_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> AssignmentInfo:
    assignment = await _load_assignment(session, user, assignment_id)
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
) -> SocraticStepResponse:
    assignment = await _load_assignment(session, user, payload.assignment_id)
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
    payload: GradeRequest, session: SessionDep, user: CurrentUserDep
) -> GradeResponse:
    assignment = await _load_assignment(session, user, payload.assignment_id)
    return await TrainerService(session).grade(
        assignment, payload.submitted_graph, user
    )
