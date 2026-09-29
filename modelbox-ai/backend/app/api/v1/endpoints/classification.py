"""A workspace's classification scale (Sprint 8 Step 4b).

Each workspace has one scale, four levels by default (Public, Internal,
Confidential, Restricted), which its ADMINs may extend, rename, reorder and
prune. Columns refer to a level by id, so a rename changes every use at once;
a level any column uses cannot be deleted. PII type is a separate field.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.v1.dependencies import CurrentUserDep, SessionDep, require_resource_role
from app.models.metadata_store import (
    AuditEvent,
    ClassificationLevel,
    ClassificationScale,
    EntityColumn,
    User,
    Workspace,
)
from app.schemas.dictionary import (
    ClassificationLevelSchema,
    ClassificationScaleSchema,
    LevelCreateRequest,
    LevelUpdateRequest,
)

router = APIRouter(prefix="/workspaces", tags=["classification"])

ViewerWorkspace = Annotated[Workspace, Depends(require_resource_role("VIEWER", Workspace, "workspace_id", "path"))]
AdminWorkspace = Annotated[Workspace, Depends(require_resource_role("ADMIN", Workspace, "workspace_id", "path"))]


async def _scale(session: SessionDep, workspace: Workspace) -> ClassificationScale:
    scale = (await session.execute(select(ClassificationScale).where(
        ClassificationScale.workspace_id == workspace.workspace_id))).scalar_one_or_none()
    if scale is None:  # pragma: no cover - every workspace gets one (0026; the Workspace insert event)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This workspace has no scale.")
    return scale


async def _levels(session: SessionDep, scale: ClassificationScale) -> list[ClassificationLevel]:
    return list((await session.execute(select(ClassificationLevel).where(
        ClassificationLevel.scale_id == scale.scale_id).order_by(ClassificationLevel.rank))).scalars().all())


async def _in_use(session: SessionDep, level_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    rows = (await session.execute(
        select(EntityColumn.classification_level_id, func.count())
        .where(EntityColumn.classification_level_id.in_(level_ids))
        .group_by(EntityColumn.classification_level_id))).all()
    return {level_id: count for level_id, count in rows}


async def _response(session: SessionDep, workspace: Workspace) -> ClassificationScaleSchema:
    scale = await _scale(session, workspace)
    levels = await _levels(session, scale)
    used = await _in_use(session, [lv.level_id for lv in levels])
    return ClassificationScaleSchema(
        workspace_id=workspace.workspace_id, scale_id=scale.scale_id, name=scale.name,
        levels=[ClassificationLevelSchema(level_id=lv.level_id, name=lv.name, rank=lv.rank,
                                          columns_using=used.get(lv.level_id, 0)) for lv in levels],
    )


def _audit(session: SessionDep, user: User, workspace: Workspace, change: str, level: str,
           **detail: object) -> None:
    """In the change's own transaction: a scale change and its event stand or fall together."""
    session.add(AuditEvent(
        action="CLASSIFICATION_CHANGED", outcome="SUCCESS", scope="workspace",
        actor_user_id=user.user_id, actor_email=user.email, workspace_id=workspace.workspace_id,
        resource_type="classification", resource_id=str(workspace.workspace_id),
        detail={"change": change, "level": level, **detail},
    ))


async def _level(session: SessionDep, scale: ClassificationScale, level_id: uuid.UUID) -> ClassificationLevel:
    level = await session.get(ClassificationLevel, level_id)
    if level is None or level.scale_id != scale.scale_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such level in this workspace's classification scale.")
    return level


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("/{workspace_id}/classification", response_model=ClassificationScaleSchema,
            summary="The workspace's classification scale")
async def get_scale(session: SessionDep, workspace: ViewerWorkspace) -> ClassificationScaleSchema:
    return await _response(session, workspace)


@router.post("/{workspace_id}/classification/levels", response_model=ClassificationScaleSchema,
             status_code=status.HTTP_201_CREATED, summary="Add a level at the top of the scale (ADMIN)")
async def add_level(payload: LevelCreateRequest, session: SessionDep, user: CurrentUserDep,
                    workspace: AdminWorkspace) -> ClassificationScaleSchema:
    scale = await _scale(session, workspace)
    levels = await _levels(session, scale)
    name = payload.name.strip()
    if any(lv.name == name for lv in levels):
        raise _conflict(f"The scale already has a level named {name!r}.")
    session.add(ClassificationLevel(scale_id=scale.scale_id, name=name, rank=len(levels) + 1))
    _audit(session, user, workspace, "added", name)
    await session.flush()
    return await _response(session, workspace)


@router.patch("/{workspace_id}/classification/levels/{level_id}", response_model=ClassificationScaleSchema,
              summary="Rename or move a level (ADMIN)")
async def update_level(level_id: uuid.UUID, payload: LevelUpdateRequest, session: SessionDep,
                       user: CurrentUserDep, workspace: AdminWorkspace) -> ClassificationScaleSchema:
    """A rename changes the level's name everywhere it is used: columns hold
    its id, not its name. A move renumbers the scale."""
    scale = await _scale(session, workspace)
    level = await _level(session, scale, level_id)
    levels = await _levels(session, scale)
    if payload.name is not None and payload.name.strip() != level.name:
        name = payload.name.strip()
        if any(lv.name == name for lv in levels):
            raise _conflict(f"The scale already has a level named {name!r}.")
        _audit(session, user, workspace, "renamed", name, previous=level.name)
        level.name = name
    if payload.rank is not None and payload.rank != level.rank:
        rank = min(payload.rank, len(levels))
        ordered = [lv for lv in levels if lv.level_id != level.level_id]
        ordered.insert(rank - 1, level)
        for position, lv in enumerate(ordered, start=1):
            lv.rank = position
        _audit(session, user, workspace, "moved", level.name, rank=rank)
    await session.flush()
    return await _response(session, workspace)


@router.delete("/{workspace_id}/classification/levels/{level_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a level no column uses (ADMIN)")
async def delete_level(level_id: uuid.UUID, session: SessionDep, user: CurrentUserDep,
                       workspace: AdminWorkspace) -> Response:
    """Refused while any column uses the level; the database's foreign key
    refuses it too, so no path around this check can delete one in use."""
    scale = await _scale(session, workspace)
    level = await _level(session, scale, level_id)
    used = (await _in_use(session, [level.level_id])).get(level.level_id, 0)
    if used:
        raise _conflict(f"The level {level.name!r} is used by {used} column(s); reclassify them first.")
    name = level.name
    try:
        await session.delete(level)
        await session.flush()
    except IntegrityError as exc:  # a column took the level between the check and the delete
        raise _conflict(f"The level {name!r} is in use.") from exc
    for position, lv in enumerate(await _levels(session, scale), start=1):
        lv.rank = position
    _audit(session, user, workspace, "deleted", name)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
