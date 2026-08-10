"""add database_connections (brownfield introspection — FR-2.1)

Isolated table for encrypted external DB credentials, scoped to a workspace.

Revision ID: 0007_add_database_connections
Revises: 0006_add_trainer_tables
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_add_database_connections"
down_revision: str | None = "0006_add_trainer_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "database_connections",
        sa.Column(
            "connection_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column(
            "workspace_id",
            _UUID,
            sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("engine", sa.String(length=30), nullable=False),
        sa.Column("connection_uri_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_database_connections_workspace_name"
        ),
        sa.CheckConstraint(
            "engine IN ('POSTGRESQL', 'SNOWFLAKE', 'BIGQUERY', 'DUCKDB')",
            name="ck_database_connections_engine",
        ),
    )
    op.create_index(
        "ix_database_connections_workspace_id",
        "database_connections",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_database_connections_workspace_id",
        table_name="database_connections",
    )
    op.drop_table("database_connections")
