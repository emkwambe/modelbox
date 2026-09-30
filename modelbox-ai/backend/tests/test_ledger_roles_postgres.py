"""The ledgers are append-only at the database, and the app role is least privilege.

Sprint 7 Step 3.2, against a real, disposable Postgres. Requires Docker; skips
without it unless MODELBOX_MIGRATION_STRICT=1, where it fails instead.

* **The migrate service** (`python -m app.db_bootstrap`) runs for real, as the
  owner: it migrates to head and sets `modelbox_app`'s password, and its output
  holds no fragment of that password. Re-running it with a new password
  rotates it, and re-running it after the role has been dropped (the state of
  a dump restored into a fresh cluster) recreates the role with its grants.
* **As `modelbox_app`, through raw SQL:** INSERT into a ledger works; UPDATE and
  DELETE on both ledgers are refused; `SET session_replication_role`, the usual
  way to switch triggers off, is refused.
* **As the owner:** the trigger refuses UPDATE, DELETE and TRUNCATE.
* **Grants drift:** `modelbox_app` has full DML on every non-ledger table,
  SELECT and INSERT only on the ledgers, SELECT only on `alembic_version`, and
  a table the owner creates later is covered by the default privileges.

Negative controls: an extra UPDATE grant on a ledger fails the drift check; a
table created with the default privileges revoked fails it too.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest

from tests._docker_postgres import (
    POSTGRES_IMAGE,
    assert_reachable_from_host,
    published_port,
    wait_for_queries,
)
from tests.test_migration_0013_populated import DOCKER, _need_docker

BACKEND = Path(__file__).resolve().parents[1]
APP_ROLE = "modelbox_app"
LEDGERS = ("audit_event", "egress_audit", "mapping_decisions")  # the last since 0030
FULL = ("SELECT", "INSERT", "UPDATE", "DELETE")
FIRST_PASSWORD = "a1" * 32
SECOND_PASSWORD = "b2" * 32
THIRD_PASSWORD = "c3" * 32  # used only by the negative control that leaks it


def _fragments(secret: str) -> list[str]:
    return [secret[i : i + 8] for i in range(len(secret) - 7)]


def _bootstrap(owner_dsn: str, password: str) -> subprocess.CompletedProcess[str]:
    env = {
        **{k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "ENVIRONMENT")},
        "DATABASE_URL": owner_dsn,
        "MODELBOX_APP_DB_PASSWORD": password,
        "ENVIRONMENT": "development",
        "PYTHONPATH": str(BACKEND),
    }
    return subprocess.run(
        [sys.executable, "-m", "app.db_bootstrap"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300, check=False,
    )


@pytest.fixture(scope="module")
def database() -> Iterator[dict[str, str]]:
    _need_docker()
    name = f"modelbox-ledger-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [DOCKER, "run", "-d", "--name", name,
         "-e", "POSTGRES_PASSWORD=verify", "-e", "POSTGRES_USER=verify",
         "-e", "POSTGRES_DB=verify", "-p", "0:5432", POSTGRES_IMAGE],
        check=True, capture_output=True, text=True,
    )
    try:
        port = published_port(name)
        for _ in range(60):
            ready = subprocess.run(
                [DOCKER, "exec", name, "pg_isready", "-U", "verify", "-d", "verify"],
                capture_output=True, text=True, check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("postgres container never became ready")
        assert_reachable_from_host(port)
        wait_for_queries(port)
        owner = f"postgresql+asyncpg://verify:verify@localhost:{port}/verify"
        result = _bootstrap(owner, FIRST_PASSWORD)
        yield {
            "container": name,
            "owner": owner.replace("+asyncpg", ""),
            "app": f"postgresql://{APP_ROLE}:{FIRST_PASSWORD}@localhost:{port}/verify",
            "app_template": f"postgresql://{APP_ROLE}:{{password}}@localhost:{port}/verify",
            "owner_async": owner,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": str(result.returncode),
        }
    finally:
        subprocess.run([DOCKER, "rm", "-f", name], capture_output=True, check=False)


# --- The migrate service -----------------------------------------------------


async def test_the_migrate_service_succeeds_and_prints_no_password(database) -> None:
    assert database["returncode"] == "0", database["stderr"][-500:]
    output = database["stdout"] + database["stderr"]
    assert not [f for f in _fragments(FIRST_PASSWORD) if f in output]
    owner = await asyncpg.connect(database["owner"])
    try:
        version = await owner.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await owner.close()
    assert version == "0031_suggestions"


async def test_the_role_is_not_privileged(database) -> None:
    owner = await asyncpg.connect(database["owner"])
    try:
        row = await owner.fetchrow(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin "
            "FROM pg_roles WHERE rolname = $1", APP_ROLE
        )
        owns = await owner.fetchval(
            "SELECT count(*) FROM pg_tables WHERE tableowner = $1", APP_ROLE
        )
    finally:
        await owner.close()
    assert dict(row) == {
        "rolsuper": False, "rolcreaterole": False, "rolcreatedb": False,
        "rolbypassrls": False, "rolcanlogin": True,
    }
    assert owns == 0


# --- Raw SQL as the application role ----------------------------------------


async def _insert_event(connection) -> str:
    audit_id = str(uuid.uuid4())
    await connection.execute(
        "INSERT INTO audit_event (audit_id, action, outcome, scope) "
        "VALUES ($1, 'AUTH_LOGIN', 'SUCCESS', 'appliance')",
        uuid.UUID(audit_id),
    )
    return audit_id


async def test_the_app_role_appends_but_cannot_rewrite_either_ledger(database) -> None:
    app = await asyncpg.connect(database["app"])
    try:
        audit_id = await _insert_event(app)
        for sql in (
            f"UPDATE audit_event SET outcome = 'DENIED' WHERE audit_id = '{audit_id}'",
            f"DELETE FROM audit_event WHERE audit_id = '{audit_id}'",
            "UPDATE egress_audit SET event = event",
            "DELETE FROM egress_audit",
        ):
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app.execute(sql)
    finally:
        await app.close()


_DECISION = (
    "INSERT INTO mapping_decisions (workspace_id, document_id, decision, decided_by_user_id, "
    "decided_by_email, evidence) VALUES (gen_random_uuid(), gen_random_uuid(), 'authored', "
    "gen_random_uuid(), 'p@example.com', '{}') RETURNING decision_id"
)


async def test_the_mapping_decisions_ledger_is_append_only_for_everyone(database) -> None:
    """Migration 0030's ledger: the app role appends and cannot rewrite; the
    trigger refuses even the owner."""
    app = await asyncpg.connect(database["app"])
    try:
        decision_id = await app.fetchval(_DECISION)
        for sql in (f"UPDATE mapping_decisions SET decision = 'removed' WHERE decision_id = '{decision_id}'",
                    f"DELETE FROM mapping_decisions WHERE decision_id = '{decision_id}'"):
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app.execute(sql)
    finally:
        await app.close()
    owner = await asyncpg.connect(database["owner"])
    try:
        for sql in (f"UPDATE mapping_decisions SET decision = 'removed' WHERE decision_id = '{decision_id}'",
                    "TRUNCATE mapping_decisions"):
            with pytest.raises(asyncpg.exceptions.PostgresError, match="append-only"):
                await owner.execute(sql)
        # The database's own refusal of a decision without a person.
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await owner.execute(_DECISION.replace("gen_random_uuid(), 'p@example.com'", "NULL, 'p@example.com'"))
    finally:
        await owner.close()


async def test_the_app_role_cannot_switch_triggers_off(database) -> None:
    app = await asyncpg.connect(database["app"])
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await app.execute("SET session_replication_role = replica")
    finally:
        await app.close()


async def test_the_trigger_refuses_even_the_owner(database) -> None:
    owner = await asyncpg.connect(database["owner"])
    try:
        audit_id = await _insert_event(owner)
        for sql in (
            f"UPDATE audit_event SET outcome = 'DENIED' WHERE audit_id = '{audit_id}'",
            f"DELETE FROM audit_event WHERE audit_id = '{audit_id}'",
            "TRUNCATE audit_event",
            "TRUNCATE egress_audit",
        ):
            with pytest.raises(asyncpg.exceptions.PostgresError, match="append-only"):
                await owner.execute(sql)
    finally:
        await owner.close()


# --- Grants drift ------------------------------------------------------------


async def _grant_problems(connection) -> list[str]:
    """Every table's privileges for the app role, against what 0022 declares."""
    tables = [r["tablename"] for r in await connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )]
    problems: list[str] = []
    for table in tables:
        if table in LEDGERS:
            expected = {"SELECT", "INSERT"}
        elif table == "alembic_version":
            expected = {"SELECT"}
        else:
            expected = set(FULL)
        for privilege in FULL:
            held = await connection.fetchval(
                "SELECT has_table_privilege($1, $2, $3)", APP_ROLE, f"public.{table}", privilege
            )
            if held != (privilege in expected):
                problems.append(f"{table}: {privilege} {'held' if held else 'missing'}")
    assert len(tables) > 10, "precondition: the schema has its tables"
    return problems


async def _check_grants(dsn: str) -> None:
    """The check, shared by the tests and their negative controls."""
    owner = await asyncpg.connect(dsn)
    try:
        problems = await _grant_problems(owner)
    finally:
        await owner.close()
    assert not problems, "grant drift: " + "; ".join(problems)


async def test_the_app_role_has_exactly_the_declared_grants(database) -> None:
    await _check_grants(database["owner"])


async def test_a_table_created_later_is_covered_by_default_privileges(database) -> None:
    owner = await asyncpg.connect(database["owner"])
    try:
        await owner.execute("CREATE TABLE later_table (id int)")
        try:
            await _check_grants(database["owner"])
        finally:
            await owner.execute("DROP TABLE later_table")
    finally:
        await owner.close()


def _docker_logs(container: str) -> str:
    result = subprocess.run(
        [DOCKER, "logs", container], capture_output=True, text=True, check=False
    )
    return result.stdout + result.stderr


def _check_server_log_clean(container: str, password: str) -> None:
    """The check, shared by the test and its negative control."""
    logs = _docker_logs(container)
    leaked = [f for f in _fragments(password) if f in logs]
    assert not leaked, "the postgres server log holds password material"


@contextlib.asynccontextmanager
async def _ddl_logging(owner_dsn: str, container: str):
    """Turn on `log_statement = ddl` server-wide, prove it logs, and restore it."""
    owner = await asyncpg.connect(owner_dsn)
    try:
        await owner.execute("ALTER SYSTEM SET log_statement = 'ddl'")
        await owner.execute("SELECT pg_reload_conf()")
        probe = f"log_probe_{uuid.uuid4().hex[:8]}"
        fresh = await asyncpg.connect(owner_dsn)
        try:
            assert await fresh.fetchval("SHOW log_statement") == "ddl"
            await fresh.execute(f"CREATE TABLE {probe} (id int)")
            await fresh.execute(f"DROP TABLE {probe}")
        finally:
            await fresh.close()
        await asyncio.sleep(1)
        assert probe in _docker_logs(container), "precondition: DDL logging is not on"
        yield
    finally:
        await owner.execute("ALTER SYSTEM RESET log_statement")
        await owner.execute("SELECT pg_reload_conf()")
        await owner.close()


async def test_rotating_the_password_takes_effect_and_logs_nothing(database) -> None:
    """Rotation works, and with DDL logging on the server log still holds no password.

    Quoting alone would not be enough here: the statement Postgres executes
    holds the password as a literal, so `log_statement = ddl` would log it.
    The migrate service turns statement logging off for its own session
    (`db_bootstrap.LOG_SUPPRESSION`), and this runs the real service with DDL
    logging switched on to show it.
    """
    try:
        async with _ddl_logging(database["owner"], database["container"]):
            result = _bootstrap(database["owner_async"], SECOND_PASSWORD)
            assert result.returncode == 0, result.stderr[-500:]
            assert not [f for f in _fragments(SECOND_PASSWORD) if f in result.stdout + result.stderr]
            await asyncio.sleep(1)
            _check_server_log_clean(database["container"], SECOND_PASSWORD)
        new = await asyncpg.connect(database["app_template"].format(password=SECOND_PASSWORD))
        await new.close()
        with pytest.raises(asyncpg.exceptions.InvalidPasswordError):
            await asyncpg.connect(database["app_template"].format(password=FIRST_PASSWORD))
    finally:
        restored = _bootstrap(database["owner_async"], FIRST_PASSWORD)
        assert restored.returncode == 0
    _check_server_log_clean(database["container"], FIRST_PASSWORD)


async def test_the_migrate_service_recreates_a_missing_role(database) -> None:
    """A dump restored into a fresh cluster has no role: the next start repairs it.

    `pg_dump` does not carry roles, and Alembic is already at head after a
    restore, so no migration would recreate one. Dropping the role here is that
    state; the real migrate service must bring back the role, its exact grants,
    and a working login.
    """
    owner = await asyncpg.connect(database["owner"])
    try:
        await owner.execute(f"DROP OWNED BY {APP_ROLE}")
        await owner.execute(f"DROP ROLE {APP_ROLE}")
        gone = await owner.fetchval("SELECT count(*) FROM pg_roles WHERE rolname = $1", APP_ROLE)
    finally:
        await owner.close()
    assert gone == 0, "precondition: the role is gone"

    result = _bootstrap(database["owner_async"], FIRST_PASSWORD)
    assert result.returncode == 0, result.stderr[-500:]
    await _check_grants(database["owner"])
    app = await asyncpg.connect(database["app"])
    await app.close()


# --- Negative controls -------------------------------------------------------


async def test_negative_control_without_log_suppression_ddl_logging_leaks(
    database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the session suppression removed in-process, the server log gets the password."""
    from app import db_bootstrap

    monkeypatch.setattr(db_bootstrap, "LOG_SUPPRESSION", ())
    try:
        async with _ddl_logging(database["owner"], database["container"]):
            owner = await asyncpg.connect(database["owner"])
            try:
                await db_bootstrap.set_app_password(owner, THIRD_PASSWORD)
            finally:
                await owner.close()
            await asyncio.sleep(1)
            with pytest.raises(AssertionError, match="server log holds password material"):
                _check_server_log_clean(database["container"], THIRD_PASSWORD)
    finally:
        restored = _bootstrap(database["owner_async"], FIRST_PASSWORD)
        assert restored.returncode == 0


async def test_negative_control_an_extra_ledger_grant_fails_the_check(database) -> None:
    owner = await asyncpg.connect(database["owner"])
    try:
        await owner.execute(f"GRANT UPDATE ON audit_event TO {APP_ROLE}")
        try:
            with pytest.raises(AssertionError, match="audit_event: UPDATE held"):
                await _check_grants(database["owner"])
        finally:
            await owner.execute(f"REVOKE UPDATE ON audit_event FROM {APP_ROLE}")
    finally:
        await owner.close()


async def test_negative_control_without_default_privileges_a_new_table_fails(database) -> None:
    owner = await asyncpg.connect(database["owner"])
    revoke = f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}"
    restore = (
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    try:
        await owner.execute(revoke)
        await owner.execute("CREATE TABLE ungranted_table (id int)")
        try:
            with pytest.raises(AssertionError, match="ungranted_table: SELECT missing"):
                await _check_grants(database["owner"])
        finally:
            await owner.execute("DROP TABLE ungranted_table")
            await owner.execute(restore)
    finally:
        await owner.close()
