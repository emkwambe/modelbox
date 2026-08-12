"""Append-only egress ledger (D3, D4).

Sprint 5. Every outbound provider request is recorded at the gateway choke
point, which an import scan proves is the only path to a provider — so ledger
completeness is structural rather than a claim about call sites.

One row per *event*, not per request. The ATTEMPT is written before the call
and never updated; the outcome arrives as a second row correlated by
``attempt_id``. An UPDATE would be simpler and wrong: it permits a later write
to revise the record of something that already left the network.

No foreign keys on ``model_id``, ``user_id`` or ``workspace_id``. The ledger
must outlive the things it describes — deleting a workspace must not erase the
record of what that workspace sent, and a cascade would do exactly that. This
is deliberately different from every other table here, where cascades are
correct.

For the same reason, rows are committed in a transaction of their own rather
than the caller's (see ``app/services/egress_ledger.py``). Egress is not undone
by a rollback, so the record of it must not be either: a ledger enlisted in the
caller's session would erase precisely the requests made during work that later
failed — the ones an auditor most wants to see. Stated here because the schema
gives no hint of it, and because writing an audit row inside the surrounding
unit of work is the obvious-looking thing to do.

Purely additive: a new table, no change to any existing one, nothing to
backfill.

Revision ID: 0015_add_egress_audit

Note: alembic_version.version_num is VARCHAR(32) and this id is 21 characters.
A longer one raises StringDataRightTruncation at the end of an otherwise
successful upgrade, on a real database only.
Revises: 0014_add_suggested_metrics
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0015_add_egress_audit"
down_revision: str | None = "0014_add_suggested_metrics"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "egress_audit",
        sa.Column(
            "egress_id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("egress_class", sa.String(length=32), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_chars", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event IN ('ATTEMPT', 'SUCCESS', 'FAILURE')",
            name="ck_egress_audit_event",
        ),
    )
    op.create_index("ix_egress_audit_attempt", "egress_audit", ["attempt_id"])
    op.create_index("ix_egress_audit_occurred", "egress_audit", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_egress_audit_occurred", table_name="egress_audit")
    op.drop_index("ix_egress_audit_attempt", table_name="egress_audit")
    op.drop_table("egress_audit")
