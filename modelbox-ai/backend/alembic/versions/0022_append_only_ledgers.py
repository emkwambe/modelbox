"""Append-only ledgers, and the least-privilege role the application runs as.

Sprint 7 Step 3 (owner decisions, 2026-09-28). After 0021's backfill, because
locking has to come after the last write to existing rows.

**The role.** ``modelbox_app`` is created NOLOGIN, not a superuser, and owns
nothing. The migrate service sets its password and LOGIN on every run
(``app.db_bootstrap``), so the password lives in ``.env`` only and rotating it
is re-running the service. The backend and worker connect as this role; only
the migrate service connects as the owner.

**Grants.** Full DML on every table except:

* ``audit_event`` and ``egress_audit`` — SELECT and INSERT only;
* ``alembic_version`` — SELECT only: the application never changes its own
  schema version.

``ALTER DEFAULT PRIVILEGES`` gives the role the same full DML on tables and
sequences the owner creates later, so a future table is not silently out of
reach. A drift test on Postgres checks the whole grant set.

**Append-only.** A ``BEFORE UPDATE OR DELETE`` row trigger and a ``BEFORE
TRUNCATE`` statement trigger raise on both ledgers, for every role, the owner
included. The REVOKE stops the application role; the trigger stops a mistake
by anyone else who can reach the database short of a superuser disabling it.

Revision ID: 0022_append_only_ledgers
Revises: 0021_audit_scope_and_owner
"""

from __future__ import annotations

from alembic import op
from app.db_roles import APP_ROLE, LEDGERS, app_role_statements

revision: str = "0022_append_only_ledgers"
down_revision: str | None = "0021_audit_scope_and_owner"
branch_labels: str | None = None
depends_on: str | None = None

_FUNCTION = "modelbox_ledger_append_only"


def upgrade() -> None:
    # The role and its grants: one definition, shared with the migrate service,
    # which re-asserts it on every start (app/db_roles.py explains why).
    for statement in app_role_statements():
        op.execute(statement)

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$;
        """
    )
    for ledger in LEDGERS:
        op.execute(
            f"CREATE TRIGGER {ledger}_append_only BEFORE UPDATE OR DELETE ON {ledger} "
            f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()"
        )
        op.execute(
            f"CREATE TRIGGER {ledger}_no_truncate BEFORE TRUNCATE ON {ledger} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION}()"
        )


def downgrade() -> None:
    for ledger in LEDGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {ledger}_no_truncate ON {ledger}")
        op.execute(f"DROP TRIGGER IF EXISTS {ledger}_append_only ON {ledger}")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(
        f"DO $$ BEGIN EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM {APP_ROLE}', "
        "current_database()); END $$;"
    )
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
