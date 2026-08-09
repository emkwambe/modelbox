"""Paradigm transformation endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.dependencies import ParadigmTranslatorDep
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
    model_id: uuid.UUID,
    payload: TransformParadigmRequest,
    translator: ParadigmTranslatorDep,
) -> TransformParadigmResponse:
    """Transform an existing model graph into a new paradigm (FR-3, TRD §2.4)."""
    result = await translator.transform(model_id, payload)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found.",
        )
    return result
