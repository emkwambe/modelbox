"""Aggregate v1 API router.

Combines all v1 endpoint routers under a single ``api_router`` that
``app.main`` mounts at the configured API prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, jobs, models, transform, workspaces

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(models.router)
api_router.include_router(transform.router)
api_router.include_router(workspaces.router)

__all__ = ["api_router"]
