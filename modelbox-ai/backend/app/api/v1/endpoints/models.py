"""Model synthesis & retrieval endpoints (workspace-scoped, Slice 3A)."""

from __future__ import annotations

import io
import uuid
import zipfile

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.v1.dependencies import (
    AuthorizedModelDep,
    CurrentUserDep,
    ExporterServiceDep,
    SessionDep,
    SynthesisEngineDep,
    require_membership,
    require_model_role,
    resolve_user_workspace,
)
from app.models.metadata_store import DataModel, WorkspaceMember
from app.schemas.data_model import (
    ContractExportResponse,
    ContractFormat,
    DiffRequest,
    DiffResponse,
    ExportFormat,
    ExportResponse,
    GraphUpdateRequest,
    ModelInfo,
    ModelUpdateRequest,
    SemanticEngine,
    SemanticExportResponse,
    SyntheticSeedRequest,
    SyntheticSeedResponse,
    SynthesizedModel,
    SynthesizeRequest,
    SynthesizeResponse,
    ValidationReport,
)
from app.services.diff_engine import DiffEngine
from app.services.exporter_service import ExporterError
from app.services.graph_engine import GraphEngine
from app.services.graph_repository import GraphRepository

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
    "",
    response_model=list[ModelInfo],
    summary="List models in the caller's workspaces",
)
async def list_models(
    session: SessionDep,
    user: CurrentUserDep,
    workspace_id: uuid.UUID | None = Query(default=None),
) -> list[ModelInfo]:
    """List models the caller can access, newest first (FR-2.2 diff selector)."""
    member_ws = (
        await session.execute(
            select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user.user_id
            )
        )
    ).scalars().all()

    if workspace_id is not None:
        if workspace_id not in member_ws:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this workspace.",
            )
        ws_ids: list[uuid.UUID] = [workspace_id]
    else:
        ws_ids = list(member_ws)

    if not ws_ids:
        return []

    rows = (
        await session.execute(
            select(DataModel)
            .where(DataModel.workspace_id.in_(ws_ids))
            .order_by(DataModel.created_at.desc())
        )
    ).scalars().all()
    return [ModelInfo.model_validate(row) for row in rows]


@router.post(
    "/diff",
    response_model=DiffResponse,
    summary="Diff two models into migration DDL + breaking changes",
)
async def diff_models(
    payload: DiffRequest,
    engine: SynthesisEngineDep,
    session: SessionDep,
    user: CurrentUserDep,
) -> DiffResponse:
    """Compare a source (V1) and target (V2) model into ALTER DDL (FR-2.2).

    Both models are authorized independently against the caller's workspace
    membership. Emits dialect-specific migration statements and flags
    destructive/breaking changes.
    """
    source = await session.get(DataModel, payload.source_model_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {payload.source_model_id} not found.",
        )
    target = await session.get(DataModel, payload.target_model_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {payload.target_model_id} not found.",
        )
    await require_membership(session, user.user_id, source.workspace_id)
    await require_membership(session, user.user_id, target.workspace_id)

    source_model = await engine.get_model(payload.source_model_id)
    target_model = await engine.get_model(payload.target_model_id)
    assert source_model is not None and target_model is not None

    statements, breaking = DiffEngine(payload.dialect).diff(
        _to_synthesized(source_model), _to_synthesized(target_model)
    )
    return DiffResponse(
        source_model_id=payload.source_model_id,
        target_model_id=payload.target_model_id,
        dialect=payload.dialect,
        alter_statements=statements,
        breaking_changes=breaking,
    )


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


@router.patch(
    "/{model_id}",
    response_model=ModelInfo,
    summary="Update model metadata (title / dialect)",
)
async def update_model(
    payload: ModelUpdateRequest,
    session: SessionDep,
    model: Annotated[DataModel, Depends(require_model_role("MEMBER"))],
) -> ModelInfo:
    """Patch model metadata. Requires MEMBER or higher (FR-6, Slice B2)."""
    if payload.title is not None:
        model.title = payload.title
    if payload.target_dialect is not None:
        model.target_dialect = payload.target_dialect
    await session.flush()
    return ModelInfo.model_validate(model)


@router.delete(
    "/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a model (ADMIN or OWNER only)",
)
async def delete_model(
    session: SessionDep,
    model: Annotated[DataModel, Depends(require_model_role("ADMIN"))],
) -> Response:
    """Delete a model and its graph (cascade). Requires ADMIN or higher."""
    await session.delete(model)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{model_id}/graph",
    response_model=ValidationReport,
    summary="Persist canvas edits (replace the model graph)",
)
async def replace_model_graph(
    payload: GraphUpdateRequest,
    session: SessionDep,
    model: Annotated[DataModel, Depends(require_model_role("MEMBER"))],
) -> ValidationReport:
    """Replace a model's graph with the canvas's current state (FR-1.2).

    Requires MEMBER+. Re-validates and bumps the model version.
    """
    await GraphRepository(session).replace_graph(
        model.model_id, payload.entities, payload.relationships
    )
    model.version_number += 1
    await session.flush()
    return GraphEngine().validate(payload.entities, payload.relationships)


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


@router.post(
    "/{model_id}/export/synthetic-data",
    response_model=SyntheticSeedResponse,
    summary="Generate referentially-intact synthetic seed data (FR-2.4)",
)
async def export_synthetic_data(
    payload: SyntheticSeedRequest,
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: AuthorizedModelDep,
) -> SyntheticSeedResponse:
    """Emit FK-safe mock rows as SQL INSERTs or a CSV bundle (FR-2.4)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep

    seed = exporter.generate_synthetic_seed(
        _to_synthesized(result),
        row_count=payload.row_count_per_entity,
        seed_format=payload.format,
        dialect=payload.dialect,
    )
    return SyntheticSeedResponse(
        model_id=model.model_id,
        format=payload.format,  # type: ignore[arg-type]
        dialect=payload.dialect,
        row_count_per_entity=payload.row_count_per_entity,
        generation_order=seed.generation_order,
        files=seed.files,
    )


@router.get(
    "/{model_id}/export/contract",
    response_model=ContractExportResponse,
    summary="Export a governance data contract (ODCS / Avro / Protobuf)",
)
async def export_contract(
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: AuthorizedModelDep,
    contract_format: ContractFormat = Query(ContractFormat.OPENDATACONTRACT, alias="format"),
) -> ContractExportResponse:
    """Generate a data contract from a persisted model (FR-2.3, Phase 3)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    try:
        files = exporter.export_data_contract(
            _to_synthesized(result), contract_format.value, dataset_name=model.title
        )
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return ContractExportResponse(
        model_id=model.model_id, format=contract_format, files=files
    )


@router.get(
    "/{model_id}/export/semantic",
    response_model=SemanticExportResponse,
    summary="Export a semantic layer (Cube.js / LookML / MetricFlow)",
)
async def export_semantic(
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: AuthorizedModelDep,
    semantic_engine: SemanticEngine = Query(SemanticEngine.CUBE, alias="engine"),
) -> SemanticExportResponse:
    """Generate a BI semantic-layer definition from a model (FR-2.3, Phase 3)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    try:
        files = exporter.export_semantic_layer(
            _to_synthesized(result), semantic_engine.value
        )
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return SemanticExportResponse(
        model_id=model.model_id, engine=semantic_engine, files=files
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
