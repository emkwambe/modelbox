"""Async synthesis job endpoints (FR-1.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_body_workspace_role,
    require_resource_role,
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
    workspace_id: Annotated[uuid.UUID, Depends(require_body_workspace_role("MEMBER"))],
) -> JobCreatedResponse:
    """Create a PENDING job for the caller's workspace and dispatch it (MEMBER+)."""
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
    job_id: uuid.UUID,
    job: Annotated[
        SynthesisJob,
        Depends(require_resource_role("VIEWER", SynthesisJob, "job_id", "path")),
    ],
) -> JobStatusResponse:
    """Return job status (VIEWER+ in the job's workspace)."""
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        result_model_id=job.result_model_id,
        error=job.error_message,
    )
