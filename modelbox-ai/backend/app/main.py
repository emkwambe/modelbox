"""ModelBox AI — FastAPI application entrypoint.

Wires together the async app: lifespan startup/shutdown, CORS for the web UI,
a liveness/readiness ``/health`` route, and the versioned API router mount.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.__version__ import __version__
from app.core.config import Settings, get_settings
from app.core.database import dispose_engine
from app.core.logging_config import configure_logging
from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)
settings = get_settings()

# Install logging before anything else runs. Without this the root logger sits
# at WARNING under uvicorn's defaults and the gateway's egress line — the only
# runtime record that a prompt left the box — is silently dropped.
configure_logging(settings)


def dev_seed_allowed(config: Settings) -> bool:
    """True only in development, and only when the seed was asked for.

    The account's password is published in this repository, so it is a
    credential everyone has. Both conditions are required: development alone
    would seed every developer's database without being asked, and the flag
    alone would let one stray variable put a known OWNER on a production box.
    """
    return config.environment == "development" and config.seed_dev_user


async def _seed_dev_user(config: Settings) -> None:
    """Create the default dev account + workspace if it does not exist.

    Refused unless :func:`dev_seed_allowed`. Otherwise best-effort: logged and
    swallowed on failure (e.g. auth tables not yet migrated) so startup never
    blocks on seeding.
    """
    if not dev_seed_allowed(config):
        return
    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.core.security import hash_password
    from app.models.metadata_store import User, Workspace, WorkspaceMember

    try:
        async with get_sessionmaker()() as session:
            existing = (
                await session.execute(
                    select(User).where(User.email == "dev@modelbox.ai")
                )
            ).scalar_one_or_none()
            if existing is not None:
                return
            user = User(
                email="dev@modelbox.ai",
                hashed_password=hash_password("password123"),
                full_name="Dev User",
            )
            session.add(user)
            await session.flush()
            workspace = Workspace(name="Dev Workspace")
            session.add(workspace)
            await session.flush()
            session.add(
                WorkspaceMember(
                    workspace_id=workspace.workspace_id,
                    user_id=user.user_id,
                    role="OWNER",
                )
            )
            await session.commit()
            logger.info("Seeded default dev user dev@modelbox.ai")
    except Exception as exc:  # noqa: BLE001 - seeding must never block startup
        logger.warning("Dev-user seeding skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: warm singletons on startup, clean up on shutdown."""
    logger.info("Starting %s (airgapped=%s)", settings.app_name, settings.is_airgapped)
    # Eagerly construct the LLM gateway so router-config errors surface at boot.
    get_llm_gateway()
    await _seed_dev_user(settings)
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("Shutdown complete; database engine disposed.")


def create_app() -> FastAPI:
    """Application factory — builds and configures the FastAPI instance."""
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="LLM-agnostic enterprise data modeling engine.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"], summary="Liveness & readiness probe")
    async def health() -> dict[str, Any]:
        """Return service health, version, egress mode, and audit-write health.

        ``degraded`` while this process has failed to write an audit event. The
        HTTP status stays 200: the container healthchecks read only the status
        code, and restarting the backend would not repair an audit sink.
        """
        from app.services.audit_log import write_failure_status

        audit = write_failure_status()
        return {
            "status": "degraded" if audit["write_failures"] else "ok",
            "service": settings.app_name,
            "version": app.version,
            "environment": settings.environment,
            "airgapped": settings.is_airgapped,
            "audit": audit,
        }

    _mount_api_router(app)
    return app


def _mount_api_router(app: FastAPI) -> None:
    """Mount the versioned API router if it is available.

    The ``api/v1`` endpoint modules are scaffolded in a later step; guarding the
    import keeps ``main.py`` runnable (health check + docs) in the meantime.
    """
    try:
        from app.api.v1.router import api_router
    except ImportError:
        logger.warning(
            "app.api.v1.router not present yet; serving /health only."
        )
        return
    app.include_router(api_router, prefix=settings.api_v1_prefix)


app = create_app()
