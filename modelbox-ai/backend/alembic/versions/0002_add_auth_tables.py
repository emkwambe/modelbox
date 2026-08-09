"""add auth tables — users + workspace_members (Slice 3A)

Introduces enterprise authentication & multi-tenancy scoping.

Revision ID: 0002_add_auth_tables
Revises: 0001_initial_schema
Create Date: 2026-08-09

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_auth_tables"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "workspace_members",
        sa.Column(
            "membership_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
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
            "role",
            sa.String(length=16),
            server_default=sa.text("'MEMBER'"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_member"
        ),
        sa.CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'MEMBER')",
            name="ck_workspace_members_role",
        ),
    )
    op.create_index(
        "ix_workspace_members_workspace_id",
        "workspace_members",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_members_user_id", "workspace_members", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_members_user_id", table_name="workspace_members"
    )
    op.drop_index(
        "ix_workspace_members_workspace_id", table_name="workspace_members"
    )
    op.drop_table("workspace_members")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
