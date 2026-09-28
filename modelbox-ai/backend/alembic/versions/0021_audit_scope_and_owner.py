"""Audit scope, the appliance-owner flag, and the narrowed action vocabulary.

Sprint 7 Step 3 (owner decisions, 2026-09-28).

* ``audit_event.scope`` — ``workspace`` when the event names a workspace,
  ``appliance`` when it does not (logins, SCIM). Added nullable, backfilled
  from ``workspace_id``, then made NOT NULL under a CHECK that keeps the two
  consistent. Locking the ledgers comes in 0022, after this backfill.
* ``users.is_appliance_owner`` — set only by ``create-owner``; it grants
  reading appliance-scope events.
* The action CHECK drops AUTH_LOGOUT, MEMBER_ROLE_CHANGED and MEMBER_REMOVED,
  which no code path emits. **A raw-SQL precondition refuses the upgrade if any
  row uses one of them**: narrowing a CHECK over such a row would fail anyway,
  and deleting audit rows to make it pass is never acceptable, so the operator
  is told instead.

Revision ID: 0021_audit_scope_and_owner
Revises: 0020_api_key_role_cap
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0021_audit_scope_and_owner"
down_revision: str | None = "0020_api_key_role_cap"
branch_labels: str | None = None
depends_on: str | None = None

REMOVED = ("AUTH_LOGOUT", "MEMBER_ROLE_CHANGED", "MEMBER_REMOVED")
_AFTER = (
    "AUTH_LOGIN",
    "AUTH_LOGIN_FAILED",
    "API_KEY_CREATED",
    "API_KEY_REVOKED",
    "MEMBER_ADDED",
    "MODEL_CREATED",
    "MODEL_UPDATED",
    "MODEL_DELETED",
    "MODEL_APPROVED",
    "USER_PROVISIONED",
    "USER_DEPROVISIONED",
    "ARTIFACT_GENERATED",
)
_BEFORE = (*_AFTER, *REMOVED)

_SCOPE_CHECK = (
    "(scope = 'workspace' AND workspace_id IS NOT NULL) OR "
    "(scope = 'appliance' AND workspace_id IS NULL)"
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def assert_no_removed_actions(connection: sa.engine.Connection) -> None:
    """Refuse the upgrade if any audit row uses an action being removed."""
    count = connection.execute(
        sa.text(f"SELECT count(*) FROM audit_event WHERE {_in('action', REMOVED)}")
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"{count} audit_event row(s) use an action this migration removes "
            f"({', '.join(REMOVED)}). Audit rows are never deleted to make a "
            "migration pass; export them and ask for a migration that keeps "
            "these actions."
        )


def upgrade() -> None:
    assert_no_removed_actions(op.get_bind())

    op.add_column("audit_event", sa.Column("scope", sa.String(16), nullable=True))
    op.execute(
        "UPDATE audit_event SET scope = "
        "CASE WHEN workspace_id IS NULL THEN 'appliance' ELSE 'workspace' END"
    )
    op.alter_column("audit_event", "scope", nullable=False)
    op.create_check_constraint("ck_audit_event_scope", "audit_event", _SCOPE_CHECK)

    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint("ck_audit_event_action", "audit_event", _in("action", _AFTER))

    op.add_column(
        "users",
        sa.Column(
            "is_appliance_owner", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_appliance_owner")
    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint("ck_audit_event_action", "audit_event", _in("action", _BEFORE))
    op.drop_constraint("ck_audit_event_scope", "audit_event", type_="check")
    op.drop_column("audit_event", "scope")
