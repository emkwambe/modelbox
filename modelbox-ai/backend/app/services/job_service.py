"""Async synthesis job service (FR-1.1).

Splits synthesis into: (1) fast job creation on the request path, and (2) the
heavy LLM synthesis, run by a Celery worker via :meth:`process_job`. Keeping
``process_job`` as a plain ``(session, gateway, job_id)`` coroutine makes it
directly testable without a broker.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import SynthesisJob, User
from app.schemas.data_model import SynthesizeRequest
from app.services.llm_gateway import LLMGateway
from app.services.synthesis_engine import SynthesisEngine

logger = logging.getLogger(__name__)


class JobService:
    """Create and process async synthesis jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_job(
        self,
        user: User,
        request: SynthesizeRequest,
        workspace_id: uuid.UUID,
    ) -> SynthesisJob:
        """Persist a PENDING job for a (pre-authorized) workspace."""
        job = SynthesisJob(
            workspace_id=workspace_id,
            user_id=user.user_id,
            status="PENDING",
            prompt=request.content,
            paradigm=str(request.target_paradigm),
            dialect=request.dialect,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    @staticmethod
    async def process_job(
        session: AsyncSession, gateway: LLMGateway, job_id: uuid.UUID
    ) -> None:
        """Run synthesis for a job, recording COMPLETED/FAILED + result.

        Safe to call from a worker: opens no transactions of its own beyond
        flush; the caller commits.
        """
        job = await session.get(SynthesisJob, job_id)
        if job is None:
            logger.warning("process_job: job %s not found", job_id)
            return

        job.status = "PROCESSING"
        await session.flush()

        try:
            engine = SynthesisEngine(session, gateway)
            request = SynthesizeRequest(
                source_type="natural_language",  # type: ignore[arg-type]
                content=job.prompt,
                target_paradigm=job.paradigm,  # type: ignore[arg-type]
                dialect=job.dialect,
                workspace_id=job.workspace_id,
            )
            result = await engine.synthesize(request)
            job.result_model_id = result.model_id
            job.status = "COMPLETED"
        except Exception as exc:  # noqa: BLE001 - record any failure on the job
            logger.exception("Synthesis job %s failed", job_id)
            job.status = "FAILED"
            job.error_message = str(exc)[:2000]
        await session.flush()
