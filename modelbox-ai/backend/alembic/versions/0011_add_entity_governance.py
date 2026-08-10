"""add grain + tier + freshness_sla to model_entities (Sprint U2)

Persists entity grain and governance metadata (asset tier + freshness SLA) so
they survive save/reload and propagate to contract/dbt exports.

Revision ID: 0011_add_entity_governance
Revises: 0010_add_column_semantics
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_add_entity_governance"
down_revision: str | None = "0010_add_column_semantics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_entities", sa.Column("grain", sa.Text(), nullable=True))
    op.add_column(
        "model_entities", sa.Column("tier", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "model_entities",
        sa.Column("freshness_sla", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_entities", "freshness_sla")
    op.drop_column("model_entities", "tier")
    op.drop_column("model_entities", "grain")
