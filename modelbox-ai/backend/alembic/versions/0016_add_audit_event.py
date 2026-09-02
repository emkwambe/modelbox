"""Internal audit trail — who did what inside the appliance (G11).

Sprint 6.5. The egress ledger added in 0015 answers *what left the network*.
This answers *who did what here*: authentication, authorisation changes, model
mutations and artifact generation. A supervisor reviewing a remediation
programme asks both questions, and a table that answers neither cleanly is
worse than two that answer one each.

Two schema decisions carry reasoning the columns do not show.

``actor_user_id`` is **not** a foreign key and ``actor_email`` is stored beside
it rather than joined. The audit trail has to survive the user being deleted,
which is precisely the moment somebody wants to read it — a join returning NULL
for a departed employee is a log that forgets the people most worth
remembering. The same argument the egress ledger makes about workspaces.

``outcome`` distinguishes DENIED from FAILURE. A refused authorisation and a
crashed handler are different events to a reviewer, and collapsing them into
"not SUCCESS" hides the one they came to look for. DENIED rows are also the
reason ``app/services/audit_log.py`` commits in its own transaction: a denial is
usually recorded on a request that then raises 403 and rolls back, so enlisting
in the caller's session would erase every refused action and keep every
permitted one.

Purely additive: a new table, no change to any existing one, nothing to
backfill.

Revision ID: 0016_add_audit_event
Revises: 0015_add_egress_audit

Note: alembic_version.version_num is VARCHAR(32) and this id is 19 characters.
A longer one raises StringDataRightTruncation at the end of an otherwise
successful upgrade, on a real database only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0016_add_audit_event"
down_revision: str | None = "0015_add_egress_audit"
branch_labels: str | None = None
depends_on: str | None = None

_ACTIONS = (
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
_OUTCOMES = ("SUCCESS", "DENIED", "FAILURE")


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column(
            "audit_id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN (" + ", ".join(f"'{a}'" for a in _ACTIONS) + ")",
            name="ck_audit_event_action",
        ),
        sa.CheckConstraint(
            "outcome IN (" + ", ".join(f"'{o}'" for o in _OUTCOMES) + ")",
            name="ck_audit_event_outcome",
        ),
    )
    op.create_index("ix_audit_event_workspace", "audit_event", ["workspace_id"])
    op.create_index("ix_audit_event_actor", "audit_event", ["actor_user_id"])
    op.create_index("ix_audit_event_occurred", "audit_event", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_event_occurred", table_name="audit_event")
    op.drop_index("ix_audit_event_actor", table_name="audit_event")
    op.drop_index("ix_audit_event_workspace", table_name="audit_event")
    op.drop_table("audit_event")
