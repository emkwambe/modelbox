"""An imported column's type, exactly as the file declared it.

Sprint 8 Step 2b (owner decision, 2026-09-29). `entity_columns.data_type`
holds the normalized type, which comparisons use; `source_data_type` holds the
declaration as written (`VARCHAR2(10 BYTE)`, `[nvarchar](60)`, `integer`),
which a data dictionary shows.

Additive and nullable, with no backfill: NULL means the column was not
imported from a file, which is true of every row written before this
migration.

Revision ID: 0024_column_source_type
Revises: 0023_import_reconciliation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0024_column_source_type"
down_revision: str | None = "0023_import_reconciliation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "entity_columns",
        sa.Column("source_data_type", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entity_columns", "source_data_type")
