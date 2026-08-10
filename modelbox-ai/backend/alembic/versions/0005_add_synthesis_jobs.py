"""add synthesis_jobs table (async synthesis — FR-1.1)

Phase 1 of the v2.0 expansion. Only the async job-tracking table is added here;
the other v2 tables (database_connections, trainer_*) land with their pillars
so each migration ships alongside the code that uses it.

Revision ID: 0005_add_synthesis_jobs
Revises: 0004_relationship_fk_indexes
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_add_synthesis_jobs"
down_revision: str | None = "0004_relationship_fk_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "synthesis_jobs",
        sa.Column("job_id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "workspace_id",
            _UUID,
            sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            _UUID,
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("paradigm", sa.String(length=32), nullable=False),
        sa.Column(
            "dialect",
            sa.String(length=64),
            server_default=sa.text("'snowflake'"),
            nullable=False,
        ),
        sa.Column(
            "result_model_id",
            _UUID,
            sa.ForeignKey("data_models.model_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_synthesis_jobs_status",
        ),
        sa.CheckConstraint(
            "paradigm IN ('3NF', 'KIMBALL', 'DATA_VAULT', 'OBT')",
            name="ck_synthesis_jobs_paradigm",
        ),
    )
    op.create_index(
        "ix_synthesis_jobs_workspace_id", "synthesis_jobs", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_synthesis_jobs_workspace_id", table_name="synthesis_jobs"
    )
    op.drop_table("synthesis_jobs")
