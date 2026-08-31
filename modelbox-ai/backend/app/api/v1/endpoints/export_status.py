"""What the appliance has verified about each exportable artifact (F5).

Read-only, and deliberately unauthenticated: this is a statement about the
product's own build, not about anyone's data. Requiring a session to learn which
dialects are deployment-verified would make the answer harder to obtain than the
artifacts it describes.

The manifest it serves is the same one the fidelity harness derives its dialect
lists and `preview` markers from, so the badge a user sees and the gate that
turns the build red cannot disagree.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.data_model import ArtifactStatusOut
from app.services.artifact_status import ARTIFACT_STATUS

router = APIRouter(prefix="/export", tags=["export"])


@router.get(
    "/status",
    response_model=list[ArtifactStatusOut],
    summary="Verification status of every exportable artifact",
)
async def list_artifact_status() -> list[ArtifactStatusOut]:
    """Return the verification status of every artifact the product can emit."""
    return [
        ArtifactStatusOut(
            variant=entry.variant,
            family=entry.family,
            status=entry.status.value,
            reason=entry.reason,
        )
        for entry in ARTIFACT_STATUS
    ]
