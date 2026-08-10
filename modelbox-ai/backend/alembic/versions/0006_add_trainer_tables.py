"""add ModelBox Trainer tables (Pillar 3, isolated)

trainer_assignments + trainer_submissions — kept in dedicated tables so the
Trainer module never pollutes core ERD/synthesis schema (isolation matrix).

Revision ID: 0006_add_trainer_tables
Revises: 0005_add_synthesis_jobs
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_add_trainer_tables"
down_revision: str | None = "0005_add_synthesis_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "trainer_assignments",
        sa.Column(
            "assignment_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column(
            "workspace_id",
            _UUID,
            sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("flawed_graph_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "expected_graph_invariants", postgresql.JSONB(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_trainer_assignments_workspace_id",
        "trainer_assignments",
        ["workspace_id"],
    )

    op.create_table(
        "trainer_submissions",
        sa.Column(
            "submission_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column(
            "assignment_id",
            _UUID,
            sa.ForeignKey(
                "trainer_assignments.assignment_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            _UUID,
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("submitted_graph_json", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("feedback_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_trainer_submissions_assignment_id",
        "trainer_submissions",
        ["assignment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trainer_submissions_assignment_id",
        table_name="trainer_submissions",
    )
    op.drop_table("trainer_submissions")
    op.drop_index(
        "ix_trainer_assignments_workspace_id",
        table_name="trainer_assignments",
    )
    op.drop_table("trainer_assignments")
