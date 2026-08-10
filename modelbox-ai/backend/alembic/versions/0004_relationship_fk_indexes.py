"""index entity_relationships FK columns (cascade-delete performance)

The from/to entity FK columns carry ON DELETE CASCADE but lacked indexes, so
deleting a model_entities row seq-scanned entity_relationships. Add indexes.

Revision ID: 0004_relationship_fk_indexes
Revises: 0003_add_n1_cardinality
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_relationship_fk_indexes"
down_revision: str | None = "0003_add_n1_cardinality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_entity_relationships_from_entity_id",
        "entity_relationships",
        ["from_entity_id"],
    )
    op.create_index(
        "ix_entity_relationships_to_entity_id",
        "entity_relationships",
        ["to_entity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entity_relationships_to_entity_id",
        table_name="entity_relationships",
    )
    op.drop_index(
        "ix_entity_relationships_from_entity_id",
        table_name="entity_relationships",
    )
