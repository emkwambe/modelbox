"""Operator-facing view of the egress ledger (D4).

The criterion is that an operator can answer "what left our network, when, to
whom" **without engineering help**. Until now the answer existed only as SQL
against `egress_audit`, which means the answer existed for engineers.

Read-only by construction: there is no route here that writes, and the ledger is
append-only anyway. The rows are the record of what the appliance sent, so a
view that could edit them would undo the point of having them.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.v1.dependencies import CurrentUserDep, SessionDep
from app.models.metadata_store import EgressAudit, WorkspaceMember
from app.schemas.data_model import EgressEventOut, EgressLedgerPage

router = APIRouter(prefix="/egress", tags=["egress"])


@router.get(
    "/events",
    response_model=EgressLedgerPage,
    summary="What left the network, when, and on whose behalf",
)
async def list_egress_events(
    session: SessionDep,
    user: CurrentUserDep,
    # `Annotated[...]` rather than `= Query(...)`: the older form calls a
    # function in a default argument, which flake8-bugbear flags (B008). It is
    # a false positive for FastAPI and the existing endpoints carry it, but new
    # code need not add to that count when the supported spelling avoids it.
    workspace_id: Annotated[uuid.UUID | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    event: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EgressLedgerPage:
    """Return ledger rows for the caller's workspaces, newest first.

    Scoped by workspace membership, like every other listing here. That leaves
    a real gap and the response names it rather than hiding it: rows written
    before an actor was known carry no workspace, so workspace scoping can
    return them to nobody. `unattributed` counts them.

    Reporting the count is the whole point. A governance view that silently
    drops what it cannot attribute tells an operator "this is what left",
    when the truth is "this is what left that we can place" — and the gap is
    invisible precisely where it matters most.
    """
    member_ws = (
        (
            await session.execute(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.user_id == user.user_id
                )
            )
        )
        .scalars()
        .all()
    )

    if workspace_id is not None:
        if workspace_id not in member_ws:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this workspace.",
            )
        ws_ids: list[uuid.UUID] = [workspace_id]
    else:
        ws_ids = list(member_ws)

    # Mutation, 2026-08-29: hard-coding this to 0 — the natural way to write
    # the view if the gap is not front of mind — fails
    # `test_rows_scoping_cannot_show_are_counted_not_dropped` and the
    # no-workspace variant, and nothing else. Both survive because they assert
    # on what the page *cannot* show rather than on what it does.
    unattributed = (
        await session.execute(
            select(func.count())
            .select_from(EgressAudit)
            .where(EgressAudit.workspace_id.is_(None))
        )
    ).scalar_one()

    if not ws_ids:
        return EgressLedgerPage(events=[], total=0, unattributed=unattributed)

    filters = [EgressAudit.workspace_id.in_(ws_ids)]
    if provider:
        filters.append(EgressAudit.provider == provider)
    if event:
        filters.append(EgressAudit.event == event)

    total = (
        await session.execute(
            select(func.count()).select_from(EgressAudit).where(*filters)
        )
    ).scalar_one()

    rows = (
        (
            await session.execute(
                select(EgressAudit)
                .where(*filters)
                # Newest first, then by id: `occurred_at` has second-or-better
                # resolution but an ATTEMPT and its outcome can share a
                # timestamp, and an unstable order would shuffle a page between
                # two requests that read the same data.
                .order_by(EgressAudit.occurred_at.desc(), EgressAudit.egress_id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return EgressLedgerPage(
        events=[EgressEventOut.model_validate(row) for row in rows],
        total=total,
        unattributed=unattributed,
    )
