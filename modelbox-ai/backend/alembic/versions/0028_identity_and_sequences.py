"""Identity columns and sequences, as an imported file declares them.

Sprint 9 Step 1a (owner decision, H3, 2026-09-30). The DDL importer kept no
identity property and skipped every CREATE SEQUENCE, so the model held no seed
or increment, and an export could only name the loss. Two nullable JSON
columns hold them:

* ``entity_columns.identity``: an identity column's generation (ALWAYS or BY
  DEFAULT), seed and increment, or, for an Oracle column a trigger fills from a
  sequence, the trigger's and the sequence's names;
* ``data_models.sequences``: the sequences the file creates, each with its
  start, increment, bounds, cache and cycle.

Additive and nullable, so an existing populated database upgrades with no
destructive step and no backfill. NULL means none, which is true of every row
written before this migration. The downgrade drops both columns, and with them
what an import after this revision stored there.

Revision ID: 0028_identity_and_sequences
Revises: 0027_member_audit_actions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0028_identity_and_sequences"
down_revision: str | None = "0027_member_audit_actions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("entity_columns", sa.Column("identity", sa.JSON(), nullable=True))
    op.add_column("data_models", sa.Column("sequences", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("data_models", "sequences")
    op.drop_column("entity_columns", "identity")
