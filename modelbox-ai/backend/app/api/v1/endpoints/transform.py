"""Paradigm transformation endpoint (workspace-scoped, Slice 3A)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.dependencies import (
    CurrentUserDep,
    ModelMemberDep,
    ParadigmTranslatorDep,
)
from app.schemas.data_model import (
    TransformParadigmRequest,
    TransformParadigmResponse,
)
from app.services import audit_log
from app.services.paradigm_translator import ModelApprovedError, TransformLintError

router = APIRouter(prefix="/model", tags=["transform"])


@router.post(
    "/{model_id}/transform-paradigm",
    response_model=TransformParadigmResponse,
    summary="Transform a model into another modeling paradigm",
)
async def transform_paradigm(
    payload: TransformParadigmRequest,
    translator: ParadigmTranslatorDep,
    model: ModelMemberDep,
    user: CurrentUserDep,
) -> TransformParadigmResponse:
    """Transform an existing model graph into a new paradigm (FR-3, TRD §2.4).

    MEMBER+: it replaces the model's graph and calls a model provider.

    409 if the model's current version is approved; 422 if the transformed
    graph has linter errors. Either way the stored graph is unchanged.
    """
    try:
        result = await translator.transform(
            model.model_id,
            payload,
            user_id=user.user_id,
            workspace_id=model.workspace_id,
        )
    except ModelApprovedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TransformLintError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": str(exc),
                "errors": [issue.model_dump() for issue in exc.errors],
            },
        ) from exc
    if result is None:  # pragma: no cover - AuthorizedModelDep already checked
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found."
        )
    await audit_log.record(
        action="MODEL_UPDATED",
        actor_user_id=user.user_id,
        actor_email=user.email,
        workspace_id=model.workspace_id,
        resource_type="model",
        resource_id=str(model.model_id),
        detail={
            "title": model.title,
            "fields": ["graph", "paradigm"],
            "paradigm": str(result.new_paradigm),
            "version": model.version_number,
        },
    )
    return result
