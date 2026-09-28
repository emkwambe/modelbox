"""API keys carry a role cap (Sprint 7, Step 2.3).

A key authenticates as its creator, limited to its own workspace and to the
lower of this cap and the creator's current role, re-read on every use.

Existing keys are backfilled to ``VIEWER`` (owner decision, 2026-09-28): a key
nobody chose a cap for gets the least privilege, and one that needs more is
recreated. The server default does the backfill in the same statement that adds
the column, so there is no moment at which a key has no cap.

Revision ID: 0020_api_key_role_cap
Revises: 0019_scim_audit_actions
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0020_api_key_role_cap"
down_revision: str | None = "0019_scim_audit_actions"
branch_labels: str | None = None
depends_on: str | None = None

_ROLES = ("OWNER", "ADMIN", "APPROVER", "MEMBER", "VIEWER")


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("role_cap", sa.String(16), nullable=False, server_default="VIEWER"),
    )
    op.create_check_constraint(
        "ck_api_keys_role_cap",
        "api_keys",
        "role_cap IN (" + ", ".join(f"'{r}'" for r in _ROLES) + ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_api_keys_role_cap", "api_keys", type_="check")
    op.drop_column("api_keys", "role_cap")
