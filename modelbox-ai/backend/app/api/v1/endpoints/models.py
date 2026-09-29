"""Model synthesis & retrieval endpoints (workspace-scoped, Slice 3A)."""

from __future__ import annotations

import io
import uuid
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.v1.dependencies import (
    AuthenticatedDep,
    CurrentUserDep,
    ExporterServiceDep,
    ModelMemberDep,
    ModelViewerDep,
    SessionDep,
    SynthesisEngineDep,
    require_body_models_role,
    require_body_workspace_role,
    require_listed_workspaces,
    require_model_role,
)
from app.models.metadata_store import DataModel, User
from app.schemas.data_model import (
    ContractExportResponse,
    ContractFormat,
    DictionaryExportResponse,
    DictionaryFormat,
    DiffRequest,
    DiffResponse,
    ExportFormat,
    ExportGapSchema,
    ExportResponse,
    GraphUpdateRequest,
    ModelInfo,
    ModelUpdateRequest,
    SemanticEngine,
    SemanticExportResponse,
    SynthesizedModel,
    SynthesizeRequest,
    SynthesizeResponse,
    SyntheticSeedRequest,
    SyntheticSeedResponse,
    ValidationReport,
)
from app.services import audit_log
from app.services.diff_engine import DiffEngine
from app.services.exporter_service import ExporterError, ExporterService
from app.services.graph_engine import GraphEngine
from app.services.graph_repository import GraphRepository

router = APIRouter(prefix="/model", tags=["models"])


async def _audit(action: str, user: User, model: DataModel, **detail: object) -> None:
    """Record a model-level event in the model's workspace."""
    await audit_log.record(
        action=action,
        actor_user_id=user.user_id,
        actor_email=user.email,
        workspace_id=model.workspace_id,
        resource_type="model",
        resource_id=str(model.model_id),
        detail={"title": model.title, **detail},
    )


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
    workspace_id: Annotated[uuid.UUID, Depends(require_body_workspace_role("MEMBER"))],
) -> SynthesizeResponse:
    """Generate, validate, and persist a data model (FR-1, Blueprint §6).

    MEMBER+ in the target workspace; when omitted, a personal workspace is
    resolved/created for the user.
    """
    payload.workspace_id = workspace_id
    return await engine.synthesize(payload, user_id=user.user_id)


@router.get(
    "",
    response_model=list[ModelInfo],
    summary="List models in the caller's workspaces",
)
async def list_models(
    session: SessionDep,
    ws_ids: Annotated[list[uuid.UUID], Depends(require_listed_workspaces("VIEWER"))],
) -> list[ModelInfo]:
    """List models the caller can access, newest first (FR-2.2 diff selector).

    An optional ``workspace_id`` query parameter narrows to one workspace.
    """
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
    _models: Annotated[
        list[DataModel],
        Depends(require_body_models_role("VIEWER", ("source_model_id", "target_model_id"))),
    ],
) -> DiffResponse:
    """Compare a source (V1) and target (V2) model into ALTER DDL (FR-2.2).

    Both models are authorized independently, VIEWER+ in each one's workspace.
    Emits dialect-specific migration statements and flags destructive/breaking
    changes.
    """
    source_model = await engine.get_model(payload.source_model_id)
    target_model = await engine.get_model(payload.target_model_id)
    assert source_model is not None and target_model is not None

    statements, breaking, semantic = DiffEngine(payload.dialect).diff(
        _to_synthesized(source_model), _to_synthesized(target_model)
    )
    return DiffResponse(
        source_model_id=payload.source_model_id,
        target_model_id=payload.target_model_id,
        dialect=payload.dialect,
        alter_statements=statements,
        breaking_changes=breaking,
        semantic_breaks=semantic,
    )


@router.post(
    "/validate-graph",
    response_model=ValidationReport,
    summary="Validate an unsaved graph (Trainer labs / pre-save checks)",
)
async def validate_graph(
    payload: GraphUpdateRequest, user: AuthenticatedDep
) -> ValidationReport:
    """Run the linter on a submitted graph without persisting it."""
    return GraphEngine().validate(payload.entities, payload.relationships)


@router.get(
    "/{model_id}",
    response_model=SynthesizeResponse,
    summary="Retrieve a persisted data model",
)
async def get_model(
    engine: SynthesisEngineDep, model: ModelViewerDep
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
    model: ModelMemberDep,
    user: CurrentUserDep,
) -> ModelInfo:
    """Patch model metadata. Requires MEMBER or higher (FR-6, Slice B2)."""
    changed = [f for f in ("title", "target_dialect") if getattr(payload, f) is not None]
    if payload.title is not None:
        model.title = payload.title
    if payload.target_dialect is not None:
        model.target_dialect = payload.target_dialect
    await session.flush()
    await _audit("MODEL_UPDATED", user, model, fields=changed)
    return ModelInfo.model_validate(model)


@router.delete(
    "/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a model (ADMIN or OWNER only)",
)
async def delete_model(
    session: SessionDep,
    user: CurrentUserDep,
    model: Annotated[DataModel, Depends(require_model_role("ADMIN"))],
) -> Response:
    """Delete a model and its graph (cascade). Requires ADMIN or higher."""
    await _audit("MODEL_DELETED", user, model, version=model.version_number)
    await session.delete(model)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{model_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record sign-off on a model (APPROVER or higher)",
)
async def approve_model(
    user: CurrentUserDep,
    model: Annotated[DataModel, Depends(require_model_role("APPROVER"))],
) -> Response:
    """Record that a named person signed off on this model, and when.

    **This exists so that the APPROVER role is not decorative.** A remediation
    programme's central question is *who signed off on this model*, and a role
    that grants nothing cannot be asked it. The approval is written to the audit
    trail rather than to a column on the model, for the reason the trail exists:
    a column holds the latest answer and silently loses every previous one,
    while the question a reviewer asks is usually about a version that is no
    longer current.

    Deliberately not a workflow. There is no pending state, no request-changes,
    no second approver — those are product decisions nobody has made, and
    inventing them here would ship a governance process by accident. What is
    claimed is exactly what is recorded: this person, this model, this moment.
    """
    await audit_log.record(
        action="MODEL_APPROVED",
        actor_user_id=user.user_id,
        actor_email=user.email,
        workspace_id=model.workspace_id,
        resource_type="model",
        resource_id=str(model.model_id),
        detail={"title": model.title, "version": model.version_number},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{model_id}/graph",
    response_model=ValidationReport,
    summary="Persist canvas edits (replace the model graph)",
)
async def replace_model_graph(
    payload: GraphUpdateRequest,
    session: SessionDep,
    model: ModelMemberDep,
    user: CurrentUserDep,
) -> ValidationReport:
    """Replace a model's graph with the canvas's current state (FR-1.2).

    Requires MEMBER+. Re-validates and bumps the model version.
    """
    await GraphRepository(session).replace_graph(
        model.model_id, payload.entities, payload.relationships
    )
    model.version_number += 1
    await session.flush()
    await _audit("MODEL_UPDATED", user, model, fields=["graph"], version=model.version_number)
    return GraphEngine().validate(payload.entities, payload.relationships)


@router.post(
    "/{model_id}/validate",
    response_model=ValidationReport,
    summary="Re-run topological/structural validation on a model",
)
async def validate_model(
    engine: SynthesisEngineDep, model: ModelViewerDep
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
    model: ModelViewerDep,
    user: CurrentUserDep,
    export_format: ExportFormat = Query(ExportFormat.DDL, alias="format"),
    dialect: str = "snowflake",
) -> ExportResponse:
    """Generate downloadable artifacts from a persisted model (FR-4)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    exporter = _exporter_for(model, exporter)
    gaps: list[ExportGapSchema] = []
    try:
        if export_format == ExportFormat.DDL:
            ddl = exporter.generate_ddl_export(_to_synthesized(result), dialect)
            files = {f"model_{dialect}.sql": ddl.sql}
            gaps = [ExportGapSchema(kind=gap.kind, entity=gap.entity, detail=gap.detail) for gap in ddl.gaps]
        else:
            files = exporter.export(_to_synthesized(result), export_format.value, dialect)
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await _audit("ARTIFACT_GENERATED", user, model, artifact=export_format.value, dialect=dialect)

    return ExportResponse(
        model_id=model.model_id,
        format=export_format,
        dialect=dialect if export_format == ExportFormat.DDL else None,
        files=files,
        gaps=gaps,
    )


def _exporter_for(model: DataModel, exporter: ExporterService) -> ExporterService:
    """An imported model's types, defaults and CHECKs are written in the dialect
    it was imported from; anything else is read as the exporter's default."""
    source = (model.import_report or {}).get("dialect")
    return ExporterService(source_dialect=source) if source else exporter


@router.post(
    "/{model_id}/export/synthetic-data",
    response_model=SyntheticSeedResponse,
    summary="Generate referentially-intact synthetic seed data (FR-2.4)",
)
async def export_synthetic_data(
    payload: SyntheticSeedRequest,
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: ModelViewerDep,
    user: CurrentUserDep,
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
    await _audit("ARTIFACT_GENERATED", user, model, artifact="synthetic-data", format=payload.format)
    return SyntheticSeedResponse(
        model_id=model.model_id,
        format=payload.format,
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
    model: ModelViewerDep,
    user: CurrentUserDep,
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
    await _audit("ARTIFACT_GENERATED", user, model, artifact="contract", format=contract_format.value)
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
    model: ModelViewerDep,
    user: CurrentUserDep,
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
    await _audit("ARTIFACT_GENERATED", user, model, artifact="semantic", engine=semantic_engine.value)
    return SemanticExportResponse(
        model_id=model.model_id, engine=semantic_engine, files=files
    )


@router.get(
    "/{model_id}/export/dictionary",
    response_model=DictionaryExportResponse,
    summary="Export a data dictionary + business glossary (Markdown/HTML/JSON)",
)
async def export_dictionary(
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: ModelViewerDep,
    user: CurrentUserDep,
    dictionary_format: DictionaryFormat = Query(
        DictionaryFormat.MARKDOWN, alias="format"
    ),
) -> DictionaryExportResponse:
    """Generate a documentation artifact from a persisted model (Pick 2)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    try:
        files = exporter.export_data_dictionary(
            _to_synthesized(result), dictionary_format.value, dataset_name=model.title
        )
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await _audit(
        "ARTIFACT_GENERATED", user, model, artifact="dictionary", format=dictionary_format.value
    )
    return DictionaryExportResponse(
        model_id=model.model_id, format=dictionary_format, files=files
    )


@router.get(
    "/{model_id}/export/zip",
    summary="Download a multi-file artifact bundle as a .zip",
    response_class=Response,
)
async def export_model_zip(
    engine: SynthesisEngineDep,
    exporter: ExporterServiceDep,
    model: ModelViewerDep,
    user: CurrentUserDep,
    export_format: ExportFormat = Query(ExportFormat.DBT, alias="format"),
    dialect: str = "snowflake",
) -> Response:
    """Pack a model's export artifacts into an in-memory zip archive (FR-4)."""
    result = await engine.get_model(model.model_id)
    assert result is not None  # guaranteed by AuthorizedModelDep
    exporter = _exporter_for(model, exporter)
    try:
        files = exporter.export(_to_synthesized(result), export_format.value, dialect)
    except ExporterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await _audit(
        "ARTIFACT_GENERATED", user, model, artifact=f"{export_format.value}.zip", dialect=dialect
    )

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
