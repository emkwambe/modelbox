"""initial schema — metadata store (TRD §2.3)

Creates the five core tables: workspaces, data_models, model_entities,
entity_columns, entity_relationships. Mirrors app.models.metadata_store so a
fresh ``alembic upgrade head`` provisions the full schema without autogenerate.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-09

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column(
            "workspace_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
    )

    op.create_table(
        "data_models",
        sa.Column(
            "model_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column(
            "workspace_id",
            _UUID,
            sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("current_paradigm", sa.String(length=32), nullable=True),
        sa.Column(
            "target_dialect",
            sa.String(length=64),
            server_default=sa.text("'snowflake'"),
            nullable=False,
        ),
        sa.Column(
            "version_number",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.CheckConstraint(
            "current_paradigm IN ('3NF', 'KIMBALL', 'DATA_VAULT', 'OBT')",
            name="ck_data_models_current_paradigm",
        ),
    )
    op.create_index(
        "ix_data_models_workspace_id", "data_models", ["workspace_id"]
    )

    op.create_table(
        "model_entities",
        sa.Column(
            "entity_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column(
            "model_id",
            _UUID,
            sa.ForeignKey("data_models.model_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_name", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column(
            "canvas_position_x",
            sa.Float(),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "canvas_position_y",
            sa.Float(),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "model_id", "entity_name", name="uq_model_entity_name"
        ),
    )
    op.create_index(
        "ix_model_entities_model_id", "model_entities", ["model_id"]
    )

    op.create_table(
        "entity_columns",
        sa.Column(
            "column_id", _UUID, primary_key=True, server_default=_GEN_UUID
        ),
        sa.Column(
            "entity_id",
            _UUID,
            sa.ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("column_name", sa.String(length=128), nullable=False),
        sa.Column("data_type", sa.String(length=64), nullable=False),
        sa.Column(
            "is_primary_key",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_foreign_key",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_pii",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("pii_type", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_entity_columns_entity_id", "entity_columns", ["entity_id"]
    )

    op.create_table(
        "entity_relationships",
        sa.Column(
            "relationship_id",
            _UUID,
            primary_key=True,
            server_default=_GEN_UUID,
        ),
        sa.Column(
            "model_id",
            _UUID,
            sa.ForeignKey("data_models.model_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_entity_id",
            _UUID,
            sa.ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_column_id",
            _UUID,
            sa.ForeignKey("entity_columns.column_id"),
            nullable=True,
        ),
        sa.Column(
            "to_entity_id",
            _UUID,
            sa.ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_column_id",
            _UUID,
            sa.ForeignKey("entity_columns.column_id"),
            nullable=True,
        ),
        sa.Column("cardinality", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "cardinality IN ('1:1', '1:N', 'N:M')",
            name="ck_entity_relationships_cardinality",
        ),
    )
    op.create_index(
        "ix_entity_relationships_model_id",
        "entity_relationships",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entity_relationships_model_id", table_name="entity_relationships"
    )
    op.drop_table("entity_relationships")
    op.drop_index("ix_entity_columns_entity_id", table_name="entity_columns")
    op.drop_table("entity_columns")
    op.drop_index("ix_model_entities_model_id", table_name="model_entities")
    op.drop_table("model_entities")
    op.drop_index("ix_data_models_workspace_id", table_name="data_models")
    op.drop_table("data_models")
    op.drop_table("workspaces")
