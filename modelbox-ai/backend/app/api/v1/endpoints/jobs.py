"""Async synthesis job endpoints (FR-1.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_membership,
    resolve_user_workspace,
)
from app.models.metadata_store import SynthesisJob
from app.schemas.data_model import (
    JobCreatedResponse,
    JobStatusResponse,
    SynthesizeRequest,
)
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_enqueuer() -> Callable[[str], None]:
    """Return the callable that dispatches a job to the Celery worker.

    Overridable in tests so no broker is required.
    """

    def _enqueue(job_id: str) -> None:
        from app.worker import run_synthesis_job

        run_synthesis_job.delay(job_id)

    return _enqueue


EnqueuerDep = Annotated[Callable[[str], None], Depends(get_job_enqueuer)]


@router.post(
    "/synthesize",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreatedResponse,
    summary="Enqueue an async synthesis job",
)
async def enqueue_synthesis(
    payload: SynthesizeRequest,
    session: SessionDep,
    user: CurrentUserDep,
    enqueue: EnqueuerDep,
) -> JobCreatedResponse:
    """Create a PENDING job for the caller's workspace and dispatch it."""
    workspace_id = await resolve_user_workspace(
        session, user, payload.workspace_id
    )
    job = await JobService(session).create_job(user, payload, workspace_id)
    # Ensure the row is committed before the worker (separate session) reads it.
    await session.commit()
    enqueue(str(job.job_id))
    return JobCreatedResponse(
        job_id=job.job_id,
        status=job.status,
        poll_url=f"/api/v1/jobs/{job.job_id}",
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll an async synthesis job",
)
async def get_job(
    job_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> JobStatusResponse:
    """Return job status (workspace-scoped)."""
    job = await session.get(SynthesisJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )
    await require_membership(session, user.user_id, job.workspace_id)
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        result_model_id=job.result_model_id,
        error=job.error_message,
    )
