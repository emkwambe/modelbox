"""Source-to-target mapping documents (Sprint 9 Step 3).

A document maps a source model's columns to a target model's. Reading is
VIEWER; proposing and deciding is MEMBER. **A decision needs a person**: every
route that accepts, edits, rejects, writes, changes or removes an entry takes
the decider from the signed-in caller and refuses an API key, which acts for
an automation rather than a person deciding. No body can name a decider.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_model_role,
    require_resource_role,
)
from app.models.metadata_store import AuditEvent, DataModel, MappingDocument, User
from app.schemas.mapping import (
    AcceptProposalRequest,
    AuthorEntryRequest,
    ChangeEntryRequest,
    ColumnPick,
    ColumnView,
    Completeness,
    CreateMappingRequest,
    DecisionView,
    EntryFields,
    EntryView,
    LineageResponse,
    MappingDocumentSchema,
    MappingExportResponse,
    MappingReportResponse,
    ProposalView,
    RowView,
)
from app.services import mapping as rules
from app.services import mapping_store as store

router = APIRouter(tags=["mappings"])

TargetMemberDep = Annotated[DataModel, Depends(require_model_role("MEMBER"))]
TargetViewerDep = Annotated[DataModel, Depends(require_model_role("VIEWER"))]
DocumentViewerDep = Annotated[MappingDocument, Depends(require_resource_role(
    "VIEWER", MappingDocument, "document_id", "path"))]
DocumentMemberDep = Annotated[MappingDocument, Depends(require_resource_role(
    "MEMBER", MappingDocument, "document_id", "path"))]

_CONTENT_TYPES = {"csv": "csv", "markdown": "md", "html": "html", "json": "json"}


def _person(request: Request, user: User) -> store.Actor:
    """The decider: the signed-in caller, and a person, not an API key."""
    principal = getattr(request.state, "principal", None)
    if principal is not None and principal.is_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="A mapping decision needs a person signed in; an API key cannot make one.")
    return store.Actor(user.user_id, user.email)


def _refused(exc: Exception) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, store.NotFound) else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=code, detail=str(exc))


def _pairs(picks: list[ColumnPick] | None) -> list[tuple[str, str]]:
    return [(p.entity, p.column) for p in picks or []]


def _fields(fields: EntryFields | None) -> dict[str, object]:
    return {} if fields is None else fields.model_dump(exclude_none=True)


def _document(row: MappingDocument) -> MappingDocumentSchema:
    return MappingDocumentSchema(
        document_id=row.document_id, workspace_id=row.workspace_id, title=row.title,
        target_model_id=row.target_model_id, source_model_id=row.source_model_id,
        source_model_title=row.source_model_title, source_system=row.source_system,
        target_system=row.target_system, version=row.version, status=row.status,
        created_by_email=row.created_by_email, created_at=row.created_at)


def _column(view: dict[str, object]) -> ColumnView:
    return ColumnView(**view)  # type: ignore[arg-type]


def _row(row: rules.Row) -> RowView:
    entry = None
    if row.entry is not None:
        e = row.entry
        entry = EntryView(entry_id=e.entry_id, mapping_key=e.mapping_key, kind=e.kind, revision=e.revision,
                          sources=[_column(s) for s in row.sources], fields=e.fields,
                          provenance_by=e.provenance_by, provenance_at=e.provenance_at)
    return RowView(
        target=_column(row.target), status=row.status, entry=entry, drift=row.drift,
        proposals=[ProposalView(proposal_id=p.proposal_id,
                                sources=[ColumnView(entity=s.entity, column=s.column, stable_id=s.stable_id,
                                                    exists=True) for s in p.sources],
                                name_similarity=p.name_similarity, type_compatibility=p.type_compatibility,
                                confidence=p.confidence, method=p.method, method_version=p.method_version)
                   for p in row.proposals])


def _completeness(rep: rules.Report) -> Completeness:
    return Completeness(total=rep.total, mapped=rep.mapped, explicitly_unmapped=rep.unmapped, pending=rep.pending,
                        silent=rep.silent, in_drift=rep.in_drift, orphaned=rep.orphaned,
                        accepted_entries=rep.accepted, pending_proposals=rep.pending_proposals,
                        complete=rep.complete, summary=rep.summary())


async def _report(session: SessionDep, document: MappingDocument) -> MappingReportResponse:
    loaded = await store.load(session, document)
    rep = loaded.report()
    return MappingReportResponse(document=_document(document), completeness=_completeness(rep),
                                 rows=[_row(r) for r in rep.rows])


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
@router.get("/model/{model_id}/mappings", response_model=list[MappingDocumentSchema],
            summary="Mapping documents whose target is this model")
async def list_mappings(session: SessionDep, model: TargetViewerDep) -> list[MappingDocumentSchema]:
    from sqlalchemy import select

    rows = await session.execute(select(MappingDocument).where(MappingDocument.target_model_id == model.model_id)
                                 .order_by(MappingDocument.created_at))
    return [_document(r) for r in rows.scalars()]


@router.post("/model/{model_id}/mappings", response_model=MappingReportResponse,
             status_code=status.HTTP_201_CREATED, summary="Start a mapping from a source model to this model")
async def create_mapping(payload: CreateMappingRequest, request: Request, session: SessionDep,
                         user: CurrentUserDep, model: TargetMemberDep) -> MappingReportResponse:
    source = await session.get(DataModel, payload.source_model_id)
    if source is None or source.workspace_id != model.workspace_id:
        # Same answer for a model elsewhere as for none: nothing leaks across workspaces.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"source model {payload.source_model_id} not found in this workspace")
    try:
        document = await store.create_document(session, model, source, payload.title, _person(request, user),
                                               payload.source_system, payload.target_system)
    except rules.MappingError as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


@router.get("/mappings/{document_id}", response_model=MappingReportResponse,
            summary="A mapping: every target column, completeness, drift and pending proposals")
async def get_mapping(session: SessionDep, document: DocumentViewerDep) -> MappingReportResponse:
    return await _report(session, document)


@router.delete("/mappings/{document_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a mapping; its decisions stay in the ledger")
async def delete_mapping(request: Request, session: SessionDep, user: CurrentUserDep,
                         document: DocumentMemberDep) -> None:
    actor = _person(request, user)
    await store.load(session, document)  # loads its rows, so they are deleted with it
    await store.delete_document(session, document, actor)


# ---------------------------------------------------------------------------
# Proposals: inference, then a person's decision
# ---------------------------------------------------------------------------
@router.post("/mappings/{document_id}/proposals", response_model=MappingReportResponse,
             summary="Propose candidates for target columns with no entry (pending until a person decides)")
async def propose(session: SessionDep, document: DocumentMemberDep) -> MappingReportResponse:
    loaded = await store.load(session, document)
    try:
        await store.run_proposer(session, loaded)
    except rules.MappingError as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


@router.post("/mappings/{document_id}/proposals/{proposal_id}/accept", response_model=MappingReportResponse,
             summary="Accept a proposal, as offered or edited (a person's decision)")
async def accept_proposal(proposal_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUserDep,
                          document: DocumentMemberDep,
                          payload: AcceptProposalRequest | None = None) -> MappingReportResponse:
    actor = _person(request, user)
    body = payload or AcceptProposalRequest()
    loaded = await store.load(session, document)
    try:
        await store.accept(session, loaded, actor, proposal_id,
                           None if body.sources is None else _pairs(body.sources),
                           _fields(body.fields) or None)
    except (rules.MappingError, store.NotFound) as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


@router.post("/mappings/{document_id}/proposals/{proposal_id}/reject", response_model=MappingReportResponse,
             summary="Reject a proposal (a person's decision)")
async def reject_proposal(proposal_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUserDep,
                          document: DocumentMemberDep) -> MappingReportResponse:
    actor = _person(request, user)
    loaded = await store.load(session, document)
    try:
        await store.reject(session, loaded, actor, proposal_id)
    except (rules.MappingError, store.NotFound) as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


# ---------------------------------------------------------------------------
# Entries a person writes
# ---------------------------------------------------------------------------
@router.post("/mappings/{document_id}/entries", response_model=MappingReportResponse,
             status_code=status.HTTP_201_CREATED,
             summary="Write an entry, or declare a target column explicitly unmapped")
async def author_entry(payload: AuthorEntryRequest, request: Request, session: SessionDep, user: CurrentUserDep,
                       document: DocumentMemberDep) -> MappingReportResponse:
    actor = _person(request, user)
    loaded = await store.load(session, document)
    try:
        await store.author(session, loaded, actor, (payload.target.entity, payload.target.column), payload.kind,
                           _pairs(payload.sources), _fields(payload.fields))
    except rules.MappingError as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


@router.put("/mappings/{document_id}/entries/{mapping_key}", response_model=MappingReportResponse,
            summary="Change an entry")
async def change_entry(mapping_key: str, payload: ChangeEntryRequest, request: Request, session: SessionDep,
                       user: CurrentUserDep, document: DocumentMemberDep) -> MappingReportResponse:
    actor = _person(request, user)
    loaded = await store.load(session, document)
    try:
        await store.change(session, loaded, actor, mapping_key, payload.kind, _pairs(payload.sources),
                           _fields(payload.fields))
    except (rules.MappingError, store.NotFound) as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


@router.delete("/mappings/{document_id}/entries/{mapping_key}", response_model=MappingReportResponse,
               summary="Remove an entry: its target column is reported silent")
async def remove_entry(mapping_key: str, request: Request, session: SessionDep, user: CurrentUserDep,
                       document: DocumentMemberDep) -> MappingReportResponse:
    actor = _person(request, user)
    loaded = await store.load(session, document)
    try:
        await store.remove(session, loaded, actor, mapping_key)
    except store.NotFound as exc:
        raise _refused(exc) from exc
    return await _report(session, document)


# ---------------------------------------------------------------------------
# Exports and lineage
# ---------------------------------------------------------------------------
@router.get("/mappings/{document_id}/export", response_model=MappingExportResponse,
            summary="Export the mapping as CSV, Markdown, HTML or JSON")
async def export_mapping(session: SessionDep, user: CurrentUserDep, document: DocumentViewerDep,
                         export_format: str = Query("csv", alias="format")) -> MappingExportResponse:
    loaded = await store.load(session, document)
    try:
        content = await store.export(session, loaded, export_format)
    except rules.MappingError as exc:
        raise _refused(exc) from exc
    session.add(AuditEvent(action="ARTIFACT_GENERATED", outcome="SUCCESS", scope="workspace",
                           actor_user_id=user.user_id, actor_email=user.email, workspace_id=document.workspace_id,
                           resource_type="mapping", resource_id=str(document.document_id),
                           detail={"artifact": "mapping", "format": export_format}))
    return MappingExportResponse(document_id=document.document_id, format=export_format,
                                 filename=f"mapping_{document.document_id}.{_CONTENT_TYPES[export_format]}",
                                 content=content)


@router.get("/mappings/{document_id}/lineage", response_model=LineageResponse,
            summary="One target column's lineage: its entry, sources as they stand, drift and decisions")
async def lineage(session: SessionDep, document: DocumentViewerDep, entity: str = Query(...),
                  column: str = Query(...)) -> LineageResponse:
    loaded = await store.load(session, document)
    try:
        row = rules.lineage(loaded.report(), entity, column)
    except rules.MappingError as exc:
        raise _refused(exc) from exc
    key = row.entry.mapping_key if row.entry else None
    history = [d for d in await store.decisions(session, document.document_id)
               if (key is not None and d.mapping_key == key)
               or (d.evidence.get("target") or {}).get("column") == column
               and (d.evidence.get("target") or {}).get("entity") == entity]
    return LineageResponse(document_id=document.document_id, row=_row(row), decisions=[
        DecisionView(decision_id=d.decision_id, decision=d.decision, mapping_key=d.mapping_key,
                     proposal_id=d.proposal_id, decided_by_email=d.decided_by_email, decided_at=d.decided_at,
                     evidence=d.evidence) for d in history])
