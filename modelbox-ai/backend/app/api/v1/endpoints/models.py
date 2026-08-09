"""Model synthesis & retrieval endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.dependencies import SynthesisEngineDep
from app.schemas.data_model import SynthesizeRequest, SynthesizeResponse

router = APIRouter(prefix="/model", tags=["models"])


@router.post(
    "/synthesize",
    response_model=SynthesizeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Synthesize a data model from natural language or documents",
)
async def synthesize_model(
    payload: SynthesizeRequest, engine: SynthesisEngineDep
) -> SynthesizeResponse:
    """Generate, validate, and persist a data model (FR-1, Blueprint §6)."""
    return await engine.synthesize(payload)


@router.get(
    "/{model_id}",
    response_model=SynthesizeResponse,
    summary="Retrieve a persisted data model",
)
async def get_model(
    model_id: uuid.UUID, engine: SynthesisEngineDep
) -> SynthesizeResponse:
    """Return a previously synthesized model by id."""
    model = await engine.get_model(model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found.",
        )
    return model
