"""allow N:1 cardinality on entity_relationships

Widens the cardinality CHECK constraint to include 'N:1' (Fact->Dimension
in Kimball star schemas). Additive: existing values remain valid.

Revision ID: 0003_add_n1_cardinality
Revises: 0002_add_auth_tables
Create Date: 2026-08-09

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_n1_cardinality"
down_revision: str | None = "0002_add_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_entity_relationships_cardinality"
_TABLE = "entity_relationships"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "cardinality IN ('1:1', '1:N', 'N:1', 'N:M')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "cardinality IN ('1:1', '1:N', 'N:M')",
    )
