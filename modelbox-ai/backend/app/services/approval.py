"""Whether a model's current version carries a recorded sign-off.

Approval is not a state on the model. `POST /model/{id}/approve` writes a
`MODEL_APPROVED` audit event naming the approver and the version they signed,
and nothing else (Sprint 6.5: deliberately not a workflow). So "approved" is
derived: a successful `MODEL_APPROVED` event exists for this model at its
current `version_number`. Any edit bumps the version, so an approval covers
exactly what was signed and lapses when the graph changes.

This is the one definition (owner decision, Sprint 7 Step 2). Every caller that
needs to know uses :func:`is_current_version_approved`; none re-derives it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import AuditEvent, DataModel


async def is_current_version_approved(session: AsyncSession, model: DataModel) -> bool:
    """True if a successful approval was recorded for ``model``'s current version."""
    details = (
        await session.execute(
            select(AuditEvent.detail).where(
                AuditEvent.action == "MODEL_APPROVED",
                AuditEvent.outcome == "SUCCESS",
                AuditEvent.resource_type == "model",
                AuditEvent.resource_id == str(model.model_id),
            )
        )
    ).scalars()
    return any(
        isinstance(detail, dict) and detail.get("version") == model.version_number
        for detail in details
    )
