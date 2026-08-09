"""Model synthesis & retrieval endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.dependencies import ExporterServiceDep, SynthesisEngineDep
from app.schemas.data_model import (
    ExportFormat,
    ExportResponse,
    SynthesizedModel,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.services.exporter_service import ExporterError

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


@router.get(
    "/{model_id}/export",
    response_model=ExportResponse,
    summary="Export a model as SQL DDL, dbt, or Cube.js artifacts",
)
async def export_model(
    model_id: uuid.UUID,
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    export_format: ExportFormat = Query(ExportFormat.DDL, alias="format"),
    dialect: str = "snowflake",
) -> ExportResponse:
    """Generate downloadable artifacts from a persisted model (FR-4)."""
    model = await engine.get_model(model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found.",
        )

    synthesized = SynthesizedModel(
        paradigm=model.paradigm,
        entities=model.entities,
        relationships=model.relationships,
        suggested_metrics=model.suggested_metrics,
    )
    try:
        files = exporter.export(synthesized, export_format.value, dialect)
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return ExportResponse(
        model_id=model_id,
        format=export_format,
        dialect=dialect if export_format == ExportFormat.DDL else None,
        files=files,
    )
