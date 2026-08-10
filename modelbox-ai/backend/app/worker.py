"""Celery worker for async synthesis jobs (FR-1.1).

Run with:  celery -A app.worker worker --loglevel=info

The task is a thin sync wrapper that opens its own async session + LLM gateway
and delegates to :meth:`JobService.process_job`.
"""

from __future__ import annotations

import asyncio
import uuid

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "modelbox",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="run_synthesis_job")
def run_synthesis_job(job_id: str) -> str:
    """Process one synthesis job by id."""
    from app.core.database import get_sessionmaker
    from app.services.job_service import JobService
    from app.services.llm_gateway import get_llm_gateway

    async def _run() -> None:
        async with get_sessionmaker()() as session:
            await JobService.process_job(
                session, get_llm_gateway(), uuid.UUID(job_id)
            )
            await session.commit()

    asyncio.run(_run())
    return job_id
