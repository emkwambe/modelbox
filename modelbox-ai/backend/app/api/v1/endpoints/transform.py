"""Paradigm transformation endpoint (workspace-scoped, Slice 3A)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.dependencies import AuthorizedModelDep, ParadigmTranslatorDep
from app.schemas.data_model import (
    TransformParadigmRequest,
    TransformParadigmResponse,
)

router = APIRouter(prefix="/model", tags=["transform"])


@router.post(
    "/{model_id}/transform-paradigm",
    response_model=TransformParadigmResponse,
    summary="Transform a model into another modeling paradigm",
)
async def transform_paradigm(
    payload: TransformParadigmRequest,
    translator: ParadigmTranslatorDep,
    model: AuthorizedModelDep,
) -> TransformParadigmResponse:
    """Transform an existing model graph into a new paradigm (FR-3, TRD §2.4)."""
    result = await translator.transform(model.model_id, payload)
    if result is None:  # pragma: no cover - AuthorizedModelDep already checked
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found."
        )
    return result
