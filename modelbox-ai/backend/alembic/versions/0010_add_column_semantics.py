"""add is_metric + aggregation to entity_columns (Semantic Sprint 2)

Persists declared semantic roles (measure + aggregation) so they survive the
save/reload round-trip and drive the semantic-layer exports.

Revision ID: 0010_add_column_semantics
Revises: 0009_add_api_keys
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_add_column_semantics"
down_revision: str | None = "0009_add_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entity_columns",
        sa.Column(
            "is_metric",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "entity_columns",
        sa.Column("aggregation", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entity_columns", "aggregation")
    op.drop_column("entity_columns", "is_metric")
