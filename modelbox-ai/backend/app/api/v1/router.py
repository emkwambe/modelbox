"""Aggregate v1 API router.

Combines all v1 endpoint routers under a single ``api_router`` that
``app.main`` mounts at the configured API prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    classification,
    connectors,
    ddl_import,
    egress,
    export_status,
    jobs,
    mappings,
    members,
    models,
    scim,
    trainer,
    transform,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(models.router)
api_router.include_router(transform.router)
api_router.include_router(workspaces.router)
api_router.include_router(classification.router)
api_router.include_router(members.router)
api_router.include_router(trainer.router)
api_router.include_router(connectors.router)
api_router.include_router(audit.router)
api_router.include_router(scim.router)
api_router.include_router(egress.router)
api_router.include_router(export_status.router)
api_router.include_router(ddl_import.router)
api_router.include_router(mappings.router)

__all__ = ["api_router"]
