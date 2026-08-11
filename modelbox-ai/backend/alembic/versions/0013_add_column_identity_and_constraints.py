"""Add stable column identity, physical constraints, and the aggregation time axis.

Sprint 2 (findings Q6, H4, M6, B1). Additive only — every column is added
nullable, backfilled, then tightened, so an existing populated database
upgrades without a destructive step and every model keeps its present meaning.

The backfill of ``entity_columns.stable_id`` is the load-bearing part. Today's
Protobuf field tags come from ``enumerate(entity.columns, start=1)`` over
columns the ORM orders by ``ordinal_position``, so the current tag *is* the
ordinal rank. Numbering the backfill the same way means the tags emitted after
this migration are byte-identical to the ones emitted before it — which is the
whole point of a field whose purpose is wire stability. ``column_id`` breaks
ties because ``ordinal_position`` carries no uniqueness constraint.

Revision ID: 0013_add_column_identity_and_constraints
Revises: 0012_add_column_quality_rules
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0013_add_column_identity_and_constraints"
down_revision: str | None = "0012_add_column_quality_rules"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- entity-level: aggregation time axis + stable-id high-water mark ----
    op.add_column(
        "model_entities",
        sa.Column("agg_time_column", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "model_entities",
        sa.Column(
            "next_stable_id",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # --- column-level: stable identity ---------------------------------------
    op.add_column(
        "entity_columns", sa.Column("stable_id", sa.Integer(), nullable=True)
    )
    op.execute(
        """
        UPDATE entity_columns AS c
        SET stable_id = ranked.rank
        FROM (
            SELECT column_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY entity_id
                       ORDER BY ordinal_position, column_id
                   ) AS rank
            FROM entity_columns
        ) AS ranked
        WHERE c.column_id = ranked.column_id
        """
    )
    op.alter_column("entity_columns", "stable_id", nullable=False)
    op.create_unique_constraint(
        "uq_entity_column_stable_id", "entity_columns", ["entity_id", "stable_id"]
    )

    # The watermark starts one past the highest id actually handed out, so no
    # existing id can ever be reissued.
    op.execute(
        """
        UPDATE model_entities AS e
        SET next_stable_id = COALESCE(highest.max_id, 0) + 1
        FROM (
            SELECT entity_id, MAX(stable_id) AS max_id
            FROM entity_columns
            GROUP BY entity_id
        ) AS highest
        WHERE e.entity_id = highest.entity_id
        """
    )

    # --- column-level: physical constraints (H4) -----------------------------
    op.add_column(
        "entity_columns",
        sa.Column(
            "is_nullable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "entity_columns",
        sa.Column(
            "is_unique",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "entity_columns",
        sa.Column("default_value", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "entity_columns",
        sa.Column("check_expression", sa.String(length=512), nullable=True),
    )
    # Nullable defaults to true — the SQL default, and what the DDL emitter
    # already implied by emitting no NOT NULL — so existing models acquire no
    # claim nobody made. A primary key is the one column that cannot be NULL.
    op.execute(
        "UPDATE entity_columns SET is_nullable = false WHERE is_primary_key"
    )

    # --- column-level: FK target (M6) ----------------------------------------
    # Named reference_target because REFERENCES is a reserved SQL word; the IR
    # field keeps the name `references`.
    op.add_column(
        "entity_columns",
        sa.Column("reference_target", sa.String(length=257), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entity_columns", "reference_target")
    op.drop_column("entity_columns", "check_expression")
    op.drop_column("entity_columns", "default_value")
    op.drop_column("entity_columns", "is_unique")
    op.drop_column("entity_columns", "is_nullable")
    op.drop_constraint(
        "uq_entity_column_stable_id", "entity_columns", type_="unique"
    )
    op.drop_column("entity_columns", "stable_id")
    op.drop_column("model_entities", "next_stable_id")
    op.drop_column("model_entities", "agg_time_column")
