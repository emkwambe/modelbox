"""Model synthesis & retrieval endpoints."""

from __future__ import annotations

import io
import uuid
import zipfile

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.dependencies import ExporterServiceDep, SynthesisEngineDep
from app.schemas.data_model import (
    ExportFormat,
    ExportResponse,
    SynthesizedModel,
    SynthesizeRequest,
    SynthesizeResponse,
    ValidationReport,
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


@router.post(
    "/{model_id}/validate",
    response_model=ValidationReport,
    summary="Re-run topological/structural validation on a model",
)
async def validate_model(
    model_id: uuid.UUID, engine: SynthesisEngineDep
) -> ValidationReport:
    """Re-check a persisted model's graph for lint issues (FR-2.3)."""
    report = await engine.validate_model(model_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found.",
        )
    return report


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


@router.get(
    "/{model_id}/export/zip",
    summary="Download a multi-file artifact bundle as a .zip",
    response_class=Response,
)
async def export_model_zip(
    model_id: uuid.UUID,
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    export_format: ExportFormat = Query(ExportFormat.DBT, alias="format"),
    dialect: str = "snowflake",
) -> Response:
    """Pack a model's export artifacts into an in-memory zip archive (FR-4)."""
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

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)

    filename = f"modelbox_{export_format.value}_{model_id}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
