"""Operator-facing view and export of the internal audit trail (G11).

The criterion is that an operator can answer "who did what in this appliance"
and hand the answer to somebody else. `egress.py` answers the outbound half —
what left the network — and this answers the inbound half. A reviewer asks both.

**Two shapes, on purpose.** The JSON page is for reading in the product. The
JSONL export is for shipping to Splunk or Sentinel, and it is a separate route
rather than a `format=` parameter because they have genuinely different
contracts: the page is paginated and the export is not, since an export that
silently stops at page one is worse than no export.

**Admin-scoped, and workspace-scoped within that.** An audit trail readable by
everyone it records is not much of a control. Membership alone is not enough —
`require_workspace_role(..., "ADMIN")` — because the events include other
people's authentication and role changes. Enforced by the route's dependency,
`require_query_workspace_role("ADMIN")`, which `route_policy.py` declares.

Read-only by construction: there is no route here that writes. The rows are the
record, and a view that could edit them would undo the point of having them.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    SessionDep,
    StreamingSessionDep,
    require_appliance_owner,
    require_query_workspace_role,
)
from app.models.metadata_store import User

AdminWorkspace = Annotated[uuid.UUID, Depends(require_query_workspace_role("ADMIN"))]
ApplianceOwner = Annotated[User, Depends(require_appliance_owner)]
from app.models.metadata_store import AuditEvent
from app.schemas.data_model import AuditEventOut, AuditEventPage

router = APIRouter(prefix="/audit", tags=["audit"])


def _filtered(workspace_id: uuid.UUID | None, action: str | None, outcome: str | None):
    """Rows for one workspace, or appliance-scope rows when ``workspace_id`` is None."""
    if workspace_id is None:
        stmt = select(AuditEvent).where(AuditEvent.scope == "appliance")
    else:
        stmt = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    return stmt


@router.get(
    "/events",
    response_model=AuditEventPage,
    summary="Who did what in this workspace",
)
async def list_audit_events(
    session: SessionDep,
    workspace_id: AdminWorkspace,
    action: Annotated[str | None, Query()] = None,
    outcome: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    """Return audit rows for one workspace, newest first.

    `workspace_id` is required rather than optional, which is the opposite of
    the egress view. That view aggregates across the caller's workspaces
    because "what left our network" is a question about the appliance. This one
    is scoped to a single workspace because the answer is only releasable to an
    admin *of that workspace*, and a cross-workspace default would quietly
    widen who can read whose events.
    """
    return await _page(session, workspace_id, action, outcome, limit, offset)


async def _page(
    session: SessionDep,
    workspace_id: uuid.UUID | None,
    action: str | None,
    outcome: str | None,
    limit: int,
    offset: int,
) -> AuditEventPage:
    total = (
        await session.execute(
            select(func.count()).select_from(
                _filtered(workspace_id, action, outcome).subquery()
            )
        )
    ).scalar_one()

    rows = (
        (
            await session.execute(
                _filtered(workspace_id, action, outcome)
                .order_by(AuditEvent.occurred_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return AuditEventPage(
        events=[AuditEventOut.model_validate(r) for r in rows], total=total
    )


def _jsonl(
    session: AsyncSession, workspace_id: uuid.UUID | None, filename: str
) -> StreamingResponse:
    # `session` must outlive the handler: rows are read as the body is sent.
    # Callers pass a StreamingSessionDep, which stays open until then.
    async def _lines():
        result = await session.stream(
            _filtered(workspace_id, None, None).order_by(AuditEvent.occurred_at.asc())
        )
        async for row in result.scalars():
            yield json.dumps(
                AuditEventOut.model_validate(row).model_dump(mode="json")
            ) + "\n"

    return StreamingResponse(
        _lines(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/export",
    summary="Export the audit trail as JSONL for a SIEM",
)
async def export_audit_events(
    session: StreamingSessionDep,
    workspace_id: AdminWorkspace,
) -> StreamingResponse:
    """Stream every audit row for a workspace as newline-delimited JSON.

    JSONL rather than JSON or CSV, and the choice is the criterion. Splunk and
    Sentinel both ingest newline-delimited JSON without a custom parser, which
    is what G11 asks for; a JSON array would require the consumer to hold the
    whole export in memory before reading the first record, and CSV would have
    to either flatten or drop `detail`.

    Streamed rather than assembled, so an export is bounded by the database
    rather than by this process's memory — an audit trail is the table most
    likely to be the largest one here.

    **Not paginated, deliberately.** The page above is for reading; this is for
    shipping, and an export that silently stops at a page boundary produces a
    SIEM that is confidently missing events.
    """
    return _jsonl(session, workspace_id, f"audit-{workspace_id}.jsonl")


# ---------------------------------------------------------------------------
# Appliance scope: events that belong to no workspace
# ---------------------------------------------------------------------------
@router.get(
    "/appliance-events",
    response_model=AuditEventPage,
    summary="Appliance-wide events: sign-ins, failed sign-ins, SCIM",
)
async def list_appliance_events(
    session: SessionDep,
    _owner: ApplianceOwner,
    action: Annotated[str | None, Query()] = None,
    outcome: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    """Return appliance-scope rows, newest first. The appliance owner only.

    These events name no workspace, so no workspace admin can read them
    through `/events`; the appliance owner (`create-owner`) can, here.
    """
    return await _page(session, None, action, outcome, limit, offset)


@router.get(
    "/appliance-export",
    summary="Export appliance-wide events as JSONL for a SIEM",
)
async def export_appliance_events(
    session: StreamingSessionDep, _owner: ApplianceOwner
) -> StreamingResponse:
    """Stream every appliance-scope row as newline-delimited JSON, unpaginated."""
    return _jsonl(session, None, "audit-appliance.jsonl")
