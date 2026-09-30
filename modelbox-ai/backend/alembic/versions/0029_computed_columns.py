"""A computed column's expression, as an imported file declares it.

Sprint 9 Step 1b (owner decision, H3, 2026-09-30). The DDL importer kept a
computed column's expression in the import report only, so the model could
not export it. Two nullable columns on ``entity_columns`` hold it:

* ``computed_expression``: the expression exactly as the file declared it, in
  its source dialect;
* ``computed_persisted``: whether the source stores the value (SQL Server
  ``PERSISTED``).

Additive and nullable, so an existing populated database upgrades with no
destructive step and no backfill. NULL means the column is not computed, or
was imported before this revision. The downgrade drops both columns, and with
them what an import after this revision stored there.

Revision ID: 0029_computed_columns
Revises: 0028_identity_and_sequences
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0029_computed_columns"
down_revision: str | None = "0028_identity_and_sequences"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("entity_columns", sa.Column("computed_expression", sa.Text(), nullable=True))
    op.add_column("entity_columns", sa.Column("computed_persisted", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("entity_columns", "computed_persisted")
    op.drop_column("entity_columns", "computed_expression")
