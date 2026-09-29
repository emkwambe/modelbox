"""Offline DDL import: an uploaded file in, a reconciled model out (Sprint 8).

Nothing here opens a connection to anything: the file is read from the request,
parsed in process, and the model is written to the appliance's own database.
The reconciliation report is stored on the model and served as Markdown or
JSON.
"""

from __future__ import annotations

import uuid
from pathlib import PurePath
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_authenticated,
    require_model_role,
    require_query_workspace_role,
)
from app.models.metadata_store import DataModel, User
from app.services import audit_log
from app.services.attestation import Actor
from app.services.ddl_import import report as report_render
from app.services.ddl_import.dialects import IMPORT_DIALECTS
from app.services.ddl_import.importer import import_ddl
from app.services.graph_repository import GraphRepository

router = APIRouter(tags=["import"])

# Larger than any schema-only export we have seen (AdventureWorks is 445 KB);
# refused by name above it rather than read into memory whole.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class ImportDialectInfo(BaseModel):
    dialect: str
    label: str
    evidence: str
    tool: str


class ImportResponse(BaseModel):
    model_id: uuid.UUID
    title: str
    status: Literal["reconciled", "unreconciled"]
    entities: int
    relationships: int
    report: dict[str, Any]


@router.get(
    "/import/dialects",
    response_model=list[ImportDialectInfo],
    summary="The dialects a DDL file can be imported from, and the evidence behind each",
)
async def list_import_dialects(
    _: Annotated[User, Depends(require_authenticated)],
) -> list[ImportDialectInfo]:
    return [ImportDialectInfo(dialect=name, **info) for name, info in IMPORT_DIALECTS.items()]


@router.post(
    "/import/ddl",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import an exported DDL file into a new model (MEMBER+)",
)
async def import_ddl_file(
    session: SessionDep,
    user: CurrentUserDep,
    workspace_id: Annotated[uuid.UUID, Depends(require_query_workspace_role("MEMBER"))],
    file: Annotated[UploadFile, File(description="The DDL file, UTF-8 or UTF-16")],
    dialect: Annotated[str, Form(description="oracle, postgres or snowflake")],
    title: Annotated[str | None, Form(max_length=255)] = None,
) -> ImportResponse:
    if dialect not in IMPORT_DIALECTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"dialect {dialect!r} is not importable; importable: {', '.join(IMPORT_DIALECTS)}",
        )
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"the file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    file_name = PurePath(file.filename or "upload.sql").name
    result = await run_in_threadpool(import_ddl, raw, dialect, file_name)
    if result.model is None:
        # Nothing importable: no model is created, and the report says why.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "nothing in the file could be imported", "report": result.report},
        )

    model = DataModel(
        workspace_id=workspace_id,
        title=(title or PurePath(file_name).stem or "Imported model")[:255],
        current_paradigm="3NF",
        target_dialect=dialect,
        reconciliation_status=result.status,
        import_report=result.report,
    )
    session.add(model)
    await session.flush()
    await GraphRepository(session).replace_graph(
        model.model_id, result.model.entities, result.model.relationships,
        source="ddl_import", actor=Actor(user.user_id, user.email),
    )
    await audit_log.record(
        action="MODEL_CREATED",
        actor_user_id=user.user_id,
        actor_email=user.email,
        workspace_id=workspace_id,
        resource_type="model",
        resource_id=str(model.model_id),
        detail={"title": model.title, "via": "ddl_import", "dialect": dialect,
                "reconciliation": result.status},
    )
    return ImportResponse(
        model_id=model.model_id,
        title=model.title,
        status=result.status,  # type: ignore[arg-type]
        entities=len(result.model.entities),
        relationships=len(result.model.relationships),
        report=result.report,
    )


@router.get(
    "/model/{model_id}/import-report",
    summary="The import's reconciliation report, as Markdown or JSON",
    response_class=PlainTextResponse,
)
async def get_import_report(
    model: Annotated[DataModel, Depends(require_model_role("VIEWER"))],
    format: Annotated[Literal["markdown", "json"], Query()] = "markdown",
) -> PlainTextResponse:
    if model.import_report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="this model was not imported from a DDL file")
    if format == "json":
        return PlainTextResponse(report_render.to_json(model.import_report), media_type="application/json")
    return PlainTextResponse(report_render.to_markdown(model.import_report, model.title),
                             media_type="text/markdown; charset=utf-8")
