"""Celery worker for async synthesis jobs (FR-1.1).

Run with:  celery -A app.worker worker --loglevel=info

Each task opens its **own** async engine + session bound to the task's event
loop, then disposes it. This is deliberate: Celery invokes every task inside a
fresh ``asyncio.run()`` loop, but the process-wide engine (``get_engine``) binds
its asyncpg pool to the *first* loop that uses it — so reusing it across tasks
raises ``Task ... got Future ... attached to a different loop`` on the second
job. A per-task engine keeps every job on its own loop.
"""

from __future__ import annotations

import asyncio
import uuid

from celery import Celery
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.services.job_service import JobService
from app.services.llm_gateway import get_llm_gateway

settings = get_settings()

# Synthesis runs here, so prompts egress from the worker too — it needs the same
# logging configuration as the API or its routing lines are dropped.
configure_logging(settings)

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
    """Process one synthesis job by id on a fresh, task-bound event loop."""

    async def _run() -> None:
        # A dedicated engine per task, bound to this asyncio.run() loop, so
        # consecutive jobs never share an asyncpg pool across loops.
        engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
        maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        try:
            async with maker() as session:
                await JobService.process_job(
                    session, get_llm_gateway(), uuid.UUID(job_id)
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())
    return job_id
