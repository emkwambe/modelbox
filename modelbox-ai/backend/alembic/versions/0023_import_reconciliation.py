"""An imported model's reconciliation status and report.

Sprint 8 Step 2a (owner decision, 2026-09-29). A model built from an uploaded
DDL file records whether the import reconciled against counts taken from the
file independently of the parser, and keeps the full reconciliation report:
the counts on both sides, every gap by statement, what was not imported and
why, and what the model cannot yet hold (each parent table's partitions, and
constraints over several columns).

Additive and nullable, so an existing populated database upgrades with no
destructive step and no backfill. NULL means the model was not imported from
a file, which is true of every row written before this migration.

Revision ID: 0023_import_reconciliation
Revises: 0022_append_only_ledgers
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0023_import_reconciliation"
down_revision: str | None = "0022_append_only_ledgers"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "data_models",
        sa.Column("reconciliation_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "data_models",
        sa.Column("import_report", sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        "ck_data_models_reconciliation_status",
        "data_models",
        "reconciliation_status IN ('reconciled', 'unreconciled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_data_models_reconciliation_status", "data_models", type_="check")
    op.drop_column("data_models", "import_report")
    op.drop_column("data_models", "reconciliation_status")
