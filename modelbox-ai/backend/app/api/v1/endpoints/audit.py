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
people's authentication and role changes.

Read-only by construction: there is no route here that writes. The rows are the
record, and a view that could edit them would undo the point of having them.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.v1.dependencies import (
    CurrentUserDep,
    SessionDep,
    require_workspace_role,
)
from app.models.metadata_store import AuditEvent
from app.schemas.data_model import AuditEventOut, AuditEventPage

router = APIRouter(prefix="/audit", tags=["audit"])


def _filtered(workspace_id: uuid.UUID, action: str | None, outcome: str | None):
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
    user: CurrentUserDep,
    workspace_id: Annotated[uuid.UUID, Query()],
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
    await require_workspace_role(session, user.user_id, workspace_id, "ADMIN")

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


@router.get(
    "/export",
    summary="Export the audit trail as JSONL for a SIEM",
)
async def export_audit_events(
    session: SessionDep,
    user: CurrentUserDep,
    workspace_id: Annotated[uuid.UUID, Query()],
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
    await require_workspace_role(session, user.user_id, workspace_id, "ADMIN")

    async def _lines():
        result = await session.stream(
            select(AuditEvent)
            .where(AuditEvent.workspace_id == workspace_id)
            .order_by(AuditEvent.occurred_at.asc())
        )
        async for row in result.scalars():
            yield json.dumps(
                AuditEventOut.model_validate(row).model_dump(mode="json")
            ) + "\n"

    return StreamingResponse(
        _lines(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit-{workspace_id}.jsonl"'
            )
        },
    )
