"""The least-privilege application role, as one idempotent list of statements.

Used twice, so the grants have one definition:

* migration ``0022_append_only_ledgers`` runs it once, when the role first
  appears;
* the migrate service (``app.db_bootstrap``) runs it on every start, before
  setting the role's password.

The second is what makes a restore work. A role belongs to the Postgres
cluster, not the database, so ``pg_dump`` does not carry it: a dump restored
into a fresh cluster has no ``modelbox_app``, its GRANTs fail, and Alembic is
already at head so no migration would recreate it. Re-asserting the role and
its grants on every start repairs that, and any other drift, before the
backend connects.

Every statement is safe to repeat.
"""

from __future__ import annotations

APP_ROLE = "modelbox_app"
# The ledgers migration 0022 made append-only. It loops over this tuple to
# create their triggers, so it never grows: a later ledger is added below.
LEDGERS = ("audit_event", "egress_audit")
# Ledgers created by later migrations, each of which creates its own triggers
# (0030: mapping_decisions, Sprint 9 Step 3). Their REVOKE is guarded on the
# table existing, because 0022 runs these statements before the table does.
LATER_LEDGERS = ("mapping_decisions",)
ALL_LEDGERS = (*LEDGERS, *LATER_LEDGERS)


def app_role_statements() -> list[str]:
    """Create the role if missing, then grant exactly the declared privileges."""
    statements = [
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOREPLICATION NOBYPASSRLS;
            END IF;
        END
        $$;
        """,
        (
            f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {APP_ROLE}', "
            "current_database()); END $$;"
        ),
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
        *(f"REVOKE UPDATE, DELETE, TRUNCATE ON {ledger} FROM {APP_ROLE}, PUBLIC" for ledger in LEDGERS),
        *(
            f"DO $$ BEGIN IF to_regclass('public.{ledger}') IS NOT NULL THEN "
            f"REVOKE UPDATE, DELETE, TRUNCATE ON {ledger} FROM {APP_ROLE}, PUBLIC; END IF; END $$;"
            for ledger in LATER_LEDGERS
        ),
        f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON alembic_version FROM {APP_ROLE}",
        (
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
        ),
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
    ]
    return statements
