"""Model synthesis & retrieval endpoints (workspace-scoped, Slice 3A)."""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.v1.dependencies import (
    AuthorizedModelDep,
    CurrentUserDep,
    ExporterServiceDep,
    SessionDep,
    SynthesisEngineDep,
    resolve_user_workspace,
)
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


def _to_synthesized(model: SynthesizeResponse) -> SynthesizedModel:
    """Rebuild the LLM-shaped model from a persisted response DTO."""
    return SynthesizedModel(
        paradigm=model.paradigm,
        entities=model.entities,
        relationships=model.relationships,
        suggested_metrics=model.suggested_metrics,
    )


@router.post(
    "/synthesize",
    response_model=SynthesizeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Synthesize a data model from natural language or documents",
)
async def synthesize_model(
    payload: SynthesizeRequest,
    engine: SynthesisEngineDep,
    user: CurrentUserDep,
    session: SessionDep,
) -> SynthesizeResponse:
    """Generate, validate, and persist a data model (FR-1, Blueprint §6).

    The target workspace is enforced against the caller's membership; when
    omitted, a personal workspace is resolved/created for the user.
    """
    payload.workspace_id = await resolve_user_workspace(
        session, user, payload.workspace_id
    )
    return await engine.synthesize(payload)


@router.get(
    "/{model_id}",
    response_model=SynthesizeResponse,
    summary="Retrieve a persisted data model",
)
async def get_model(
    engine: SynthesisEngineDep, model: AuthorizedModelDep
) -> SynthesizeResponse:
    """Return a previously synthesized model by id (workspace-scoped)."""
    result = await engine.get_model(model.model_id)
    if result is None:  # pragma: no cover - AuthorizedModelDep already checked
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found."
        )
    return result


@router.post(
    "/{model_id}/validate",
    response_model=ValidationReport,
    summary="Re-run topological/structural validation on a model",
)
async def validate_model(
    engine: SynthesisEngineDep, model: AuthorizedModelDep
) -> ValidationReport:
    """Re-check a persisted model's graph for lint issues (FR-2.3)."""
    report = await engine.validate_model(model.model_id)
    if report is None:  # pragma: no cover - AuthorizedModelDep already checked
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model not found."
        )
    return report


@router.get(
    "/{model_id}/export",
    response_model=ExportResponse,
    summary="Export a model as SQL DDL, dbt, or Cube.js artifacts",
)
async def export_model(
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: AuthorizedModelDep,
    export_format: ExportFormat = Query(ExportFormat.DDL, alias="format"),
    dialect: str = "snowflake",
) -> ExportResponse:
    """Generate downloadable artifacts from a persisted model (FR-4)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    try:
        files = exporter.export(_to_synthesized(result), export_format.value, dialect)
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return ExportResponse(
        model_id=model.model_id,
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
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: AuthorizedModelDep,
    export_format: ExportFormat = Query(ExportFormat.DBT, alias="format"),
    dialect: str = "snowflake",
) -> Response:
    """Pack a model's export artifacts into an in-memory zip archive (FR-4)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    try:
        files = exporter.export(_to_synthesized(result), export_format.value, dialect)
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)

    filename = f"modelbox_{export_format.value}_{model.model_id}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
