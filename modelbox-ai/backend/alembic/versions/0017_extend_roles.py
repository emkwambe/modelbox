"""Two more roles, and an approval a reviewer can read (G10).

Sprint 6.5. The ladder was OWNER / ADMIN / MEMBER, which left two gaps that
matter to the buyer this sprint exists for.

**VIEWER**, because read-only access had no expression at all. The lowest role
could edit every model in the workspace, so "let the auditor look" and "let the
auditor change things" were the same grant — which is not a permission model a
reviewer accepts.

**APPROVER**, because a remediation programme's central question is *who signed
off on this model*, and a role that cannot be asked that is decorative. It is
paired with `MODEL_APPROVED` in the audit vocabulary and an endpoint that
records it, so the role does something rather than merely existing.

**Extended, not replaced.** The sprint plan names the roles viewer / modeller /
approver / admin, and adopting that vocabulary wholesale would rewrite every
existing member's role and require a data migration whose failure mode is
somebody silently losing access. `MEMBER` already *is* the modeller — it is the
role that edits a model — so the ladder gains the two levels it lacked and
keeps the three it had. No row changes value here.

Purely additive in effect: both CHECK constraints widen, so every row valid
before is valid after. The downgrade narrows them again and would fail on a row
using a new value, which is correct — a downgrade that silently deleted an
approval record, or an auditor's read-only membership, would be worse than one
that refuses.

Revision ID: 0017_extend_roles
Revises: 0016_add_audit_event
"""

from __future__ import annotations

from alembic import op

revision: str = "0017_extend_roles"
down_revision: str | None = "0016_add_audit_event"
branch_labels: str | None = None
depends_on: str | None = None

_OLD_ROLES = "role IN ('OWNER', 'ADMIN', 'MEMBER')"
_NEW_ROLES = "role IN ('OWNER', 'ADMIN', 'APPROVER', 'MEMBER', 'VIEWER')"

_OLD_ACTIONS = (
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
    "ARTIFACT_GENERATED",
)
_NEW_ACTIONS = (*_OLD_ACTIONS, "MODEL_APPROVED")


def _action_check(actions: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{a}'" for a in actions) + ")"


def upgrade() -> None:
    op.drop_constraint(
        "ck_workspace_members_role", "workspace_members", type_="check"
    )
    op.create_check_constraint(
        "ck_workspace_members_role", "workspace_members", _NEW_ROLES
    )

    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint(
        "ck_audit_event_action", "audit_event", _action_check(_NEW_ACTIONS)
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint(
        "ck_audit_event_action", "audit_event", _action_check(_OLD_ACTIONS)
    )

    op.drop_constraint(
        "ck_workspace_members_role", "workspace_members", type_="check"
    )
    op.create_check_constraint(
        "ck_workspace_members_role", "workspace_members", _OLD_ROLES
    )
