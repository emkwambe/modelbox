"""add min_value + max_value + regex_pattern to entity_columns (Sprint U3)

Persists per-column quality rules (numeric bounds + text format pattern) so
they survive save/reload and propagate to dbt tests / ODCS quality blocks.

Revision ID: 0012_add_column_quality_rules
Revises: 0011_add_entity_governance
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_add_column_quality_rules"
down_revision: str | None = "0011_add_entity_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entity_columns", sa.Column("min_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "entity_columns", sa.Column("max_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "entity_columns",
        sa.Column("regex_pattern", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entity_columns", "regex_pattern")
    op.drop_column("entity_columns", "max_value")
    op.drop_column("entity_columns", "min_value")
