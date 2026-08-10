"""add api_keys (programmatic access — Step 1)

Workspace-scoped API keys, SHA-256 hashed at rest. Authenticate as the creating
user (X-API-Key), inheriting that user's memberships/RBAC.

Revision ID: 0009_add_api_keys
Revises: 0008_add_mysql_engine
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_add_api_keys"
down_revision: str | None = "0008_add_mysql_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("api_key_id", _UUID, primary_key=True, server_default=_GEN_UUID),
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
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_workspace_id", "api_keys", ["workspace_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_workspace_id", table_name="api_keys")
    op.drop_table("api_keys")
