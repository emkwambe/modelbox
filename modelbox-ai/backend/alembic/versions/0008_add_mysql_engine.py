"""Allow MYSQL as a database_connections engine (Pick 3).

Revision ID: 0008_add_mysql_engine
Revises: 0007_add_database_connections
Create Date: 2026-08-10

"""

from __future__ import annotations

from alembic import op

revision: str = "0008_add_mysql_engine"
down_revision: str | None = "0007_add_database_connections"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_database_connections_engine"
_WITH_MYSQL = "engine IN ('POSTGRESQL', 'SNOWFLAKE', 'BIGQUERY', 'MYSQL', 'DUCKDB')"
_WITHOUT_MYSQL = "engine IN ('POSTGRESQL', 'SNOWFLAKE', 'BIGQUERY', 'DUCKDB')"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "database_connections", type_="check")
    op.create_check_constraint(_CONSTRAINT, "database_connections", _WITH_MYSQL)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "database_connections", type_="check")
    op.create_check_constraint(_CONSTRAINT, "database_connections", _WITHOUT_MYSQL)
