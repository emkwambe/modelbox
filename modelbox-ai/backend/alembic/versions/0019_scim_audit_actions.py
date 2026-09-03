"""Audit actions for SCIM user lifecycle (G9).

Sprint 6.5. `USER_PROVISIONED` and `USER_DEPROVISIONED` widen the audit
vocabulary so an IdP creating or removing somebody is recorded as what it is.

They are deliberately not folded into the existing `MEMBER_ADDED` /
`MEMBER_REMOVED`: those describe workspace membership, which is an
authorisation change, and this is an identity lifecycle event. A reviewer asked
"when did this person lose access" wants the de-provisioning row, and a reviewer
asked "who could see this workspace" wants the membership row. One vocabulary
for both makes each question return the other's answers.

Widening only — every row valid before is valid after. The downgrade narrows and
would fail on a row using either new value, which is correct: a downgrade that
silently deleted the record of a de-provisioning is worse than one that refuses.

Revision ID: 0019_scim_audit_actions
Revises: 0018_federated_identity
"""

from __future__ import annotations

from alembic import op

revision: str = "0019_scim_audit_actions"
down_revision: str | None = "0018_federated_identity"
branch_labels: str | None = None
depends_on: str | None = None

_BEFORE = (
    "AUTH_LOGIN",
    "AUTH_LOGIN_FAILED",
    "AUTH_LOGOUT",
    "API_KEY_CREATED",
    "API_KEY_REVOKED",
    "MEMBER_ADDED",
    "MEMBER_ROLE_CHANGED",
    "MEMBER_REMOVED",
    "MODEL_CREATED",
    "MODEL_UPDATED",
    "MODEL_DELETED",
    "MODEL_APPROVED",
    "ARTIFACT_GENERATED",
)
_AFTER = (*_BEFORE, "USER_PROVISIONED", "USER_DEPROVISIONED")


def _check(actions: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{a}'" for a in actions) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint(
        "ck_audit_event_action", "audit_event", _check(_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint(
        "ck_audit_event_action", "audit_event", _check(_BEFORE)
    )
