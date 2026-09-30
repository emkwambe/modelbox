"""What the appliance has verified about each exportable artifact (F5).

Read-only, and requires sign-in. It is a statement about the product's own
build rather than anyone's data, but the appliance denies by default and nothing
needs it anonymously: its only caller is the export panel, which works only for a
signed-in user (owner decision, Sprint 7 Step 2).

The manifest it serves is the same one the fidelity harness derives its dialect
lists and `preview` markers from, so the badge a user sees and the gate that
turns the build red cannot disagree.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.dependencies import AuthenticatedDep
from app.schemas.data_model import ArtifactStatusOut
from app.services.artifact_status import ARTIFACT_STATUS

router = APIRouter(prefix="/export", tags=["export"])


@router.get(
    "/status",
    response_model=list[ArtifactStatusOut],
    summary="Verification status of every exportable artifact",
)
async def list_artifact_status(_user: AuthenticatedDep) -> list[ArtifactStatusOut]:
    """Return the verification status of every artifact the product can emit."""
    return [
        ArtifactStatusOut(
            variant=entry.variant,
            family=entry.family,
            status=entry.status.value,
            reason=entry.reason,
            options=list(entry.options),
        )
        for entry in ARTIFACT_STATUS
    ]
