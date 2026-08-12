"""Persist suggested metrics on the model (M1).

Sprint 4. `SynthesisEngine._to_response` hardcoded `suggested_metrics=[]` on
the reload path, so metrics survived synthesis, reached the canvas, and
vanished on save. The visible cost was in the diff engine:
`DiffEngine._semantic_breaks` carries a branch that reports "this metric's
formula references a column you just dropped", and through the API that branch
could never fire, because a diff of two persisted models always compared two
empty formula lists. Working code, unreachable in production.

Additive and nullable, so an existing populated database upgrades with no
destructive step and no backfill. There is deliberately no backfill: a row
written before this migration genuinely has no metrics, and NULL says exactly
that. Defaulting them to `[]` would assert that we know the model had none,
which we do not — the data was discarded, not observed to be empty.

Stored as JSON on `data_models` rather than decomposed into rows. A metric is
a name, an opaque formula string and a description, with no foreign keys into
the graph; a table would add joins nobody performs and a delete-orphan cascade
to maintain.

Revision ID: 0014_add_suggested_metrics

Note: alembic_version.version_num is VARCHAR(32), and this id is 26
characters. A longer one raises StringDataRightTruncation at the *end* of an
otherwise successful upgrade, on a real database only — an empty-database test
does not catch it, because the failure is in stamping the version rather than
in the DDL. Caught that way once, in 0013.
Revises: 0013_add_column_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014_add_suggested_metrics"
down_revision: str | None = "0013_add_column_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "data_models",
        sa.Column("suggested_metrics", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_models", "suggested_metrics")
