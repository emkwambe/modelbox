"""Migrations 0015 → head against a populated database, and ORM-vs-migration drift.

Sprint 7 Step 3.3. Requires Docker; skips without it unless
MODELBOX_MIGRATION_STRICT=1, where it fails instead (CI runs it strict).

**Populated upgrade.** Data is written at the revision where its tables looked
the way they did, then the database is upgraded to head and read back with raw
SQL, never through the ORM (register standard 1):

* at 0015, real models (the gold graphs) and egress-ledger rows;
* at 0019, audit rows with and without a workspace (no ``scope`` column yet),
  a user, and an API key (no ``role_cap`` column yet);
* then head, confirmed by reading ``alembic_version`` back (`_upgrade_to`).

After it: every model and ledger row is still there, ``scope`` was backfilled
from ``workspace_id``, the key was backfilled to ``VIEWER``, no existing user
became the appliance owner, and both ledgers refuse rewrites.

**0021's precondition.** A database holding a removed audit action refuses the
upgrade with a message, and leaves the row alone.

**Drift.** Alembic's autogenerate comparison between the ORM and the migrated
Postgres schema must be empty. It runs on Postgres, not SQLite, because the
SQLite tests build their schema from the ORM and cannot disagree with it.

Negative controls: with 0021's removed-action list replaced in-process by one
naming no real action, the precondition lets the row through; a table added to the database outside the
ORM makes the drift check fail.
"""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import time
import uuid
from collections.abc import Iterator
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.metadata_store import Base
from tests._docker_postgres import (
    POSTGRES_IMAGE,
    assert_reachable_from_host,
    published_port,
)
from tests.test_migration_0013_populated import (
    BACKEND,
    DOCKER,
    _alembic,
    _need_docker,
    _run_helper,
    _upgrade_to,
)

MIGRATION_0021 = BACKEND / "alembic" / "versions" / "0021_audit_scope_and_owner.py"


def _load_0021() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0021", MIGRATION_0021)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """A disposable Postgres; yields a DSN template with a `{db}` placeholder."""
    _need_docker()
    name = f"modelbox-head-{uuid.uuid4().hex[:8]}"
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
        template = f"postgresql+asyncpg://verify:verify@localhost:{port}/{{db}}"
        _wait_for_queries(template.format(db="verify"))
        yield template
    finally:
        subprocess.run([DOCKER, "rm", "-f", name], capture_output=True, check=False)


async def _fetch(dsn: str, query: str, **params: object) -> list[dict]:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(sa.text(query), params)
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


async def _execute(dsn: str, query: str, **params: object) -> None:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text(query), params)
    finally:
        await engine.dispose()


def _wait_for_queries(dsn: str, attempts: int = 30) -> None:
    """Wait until a query succeeds over the host port.

    The image's entrypoint initialises the cluster on a temporary server, stops
    it, and starts the real one, so `pg_isready` and an open port can both
    answer during that window and the next connection is reset. A completed
    query is the readiness this module actually needs.
    """
    last: BaseException | None = None
    for _ in range(attempts):
        try:
            asyncio.run(_fetch(dsn, "SELECT 1"))
            return
        except (OSError, sa.exc.DBAPIError) as error:
            last = error
            time.sleep(1)
    pytest.fail(f"postgres never answered a query over the host port: {last!r}")


async def _create_database(admin_dsn: str, name: str) -> None:
    # CREATE DATABASE cannot run inside a transaction block.
    engine = create_async_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f"CREATE DATABASE {name}"))
    finally:
        await engine.dispose()


def _database(server: str, name: str) -> str:
    """A fresh database on the shared server. Synchronous: each call makes and
    disposes its own engine, so no event loop is shared across fixtures."""
    asyncio.run(_create_database(server.format(db="verify"), name))
    return server.format(db=name)


# --- The populated upgrade ----------------------------------------------------


@pytest.fixture(scope="module")
def upgraded(server: str) -> dict:
    dsn = _database(server, "populated")
    seeded: dict = {}
    asyncio.run(_populate_and_upgrade(dsn, seeded))
    return {"dsn": dsn, "models": len(seeded["models"])}


async def _populate_and_upgrade(dsn: str, seeded: dict) -> None:
    _upgrade_to(BACKEND, dsn, "0015_add_egress_audit")
    seeded.update(_run_helper(BACKEND, dsn, "seed-and-export"))
    assert seeded["models"], "fixture sanity: nothing was seeded"
    for i in range(3):
        await _execute(
            dsn,
            "INSERT INTO egress_audit (egress_id, attempt_id, event, task, provider, "
            "egress_class, prompt_sha256, prompt_chars) VALUES "
            "(:e, :a, 'ATTEMPT', 'synthesis', 'anthropic', 'cloud', :sha, 10)",
            e=uuid.uuid4(), a=uuid.uuid4(), sha=f"{i:064d}",
        )

    _upgrade_to(BACKEND, dsn, "0019_scim_audit_actions")
    workspace_id = (await _fetch(dsn, "SELECT workspace_id FROM workspaces LIMIT 1"))[0]["workspace_id"]
    user_id = uuid.uuid4()
    await _execute(
        dsn,
        "INSERT INTO users (user_id, email, hashed_password) VALUES (:u, 'old@example.com', 'x')",
        u=user_id,
    )
    await _execute(
        dsn,
        "INSERT INTO api_keys (api_key_id, workspace_id, user_id, name, key_prefix, key_hash) "
        "VALUES (:k, :w, :u, 'ci', 'mb_old', :h)",
        k=uuid.uuid4(), w=workspace_id, u=user_id, h="f" * 64,
    )
    await _execute(
        dsn,
        "INSERT INTO audit_event (audit_id, action, outcome, workspace_id) VALUES "
        "(:a1, 'MODEL_UPDATED', 'SUCCESS', :w), (:a2, 'AUTH_LOGIN', 'SUCCESS', NULL)",
        a1=uuid.uuid4(), a2=uuid.uuid4(), w=workspace_id,
    )

    _upgrade_to(BACKEND, dsn, "head")


async def test_the_database_reached_head(upgraded) -> None:
    rows = await _fetch(upgraded["dsn"], "SELECT version_num FROM alembic_version")
    assert rows == [{"version_num": "0022_append_only_ledgers"}]


async def test_models_and_ledger_rows_survive(upgraded) -> None:
    models = await _fetch(upgraded["dsn"], "SELECT count(*) AS n FROM data_models")
    egress = await _fetch(upgraded["dsn"], "SELECT count(*) AS n FROM egress_audit")
    audit = await _fetch(upgraded["dsn"], "SELECT count(*) AS n FROM audit_event")
    assert models[0]["n"] == upgraded["models"]
    assert egress[0]["n"] == 3
    assert audit[0]["n"] == 2


async def test_scope_was_backfilled_from_workspace(upgraded) -> None:
    rows = await _fetch(upgraded["dsn"], "SELECT action, scope, workspace_id FROM audit_event")
    by_action = {r["action"]: r for r in rows}
    assert by_action["MODEL_UPDATED"]["scope"] == "workspace"
    assert by_action["AUTH_LOGIN"]["scope"] == "appliance"
    assert by_action["AUTH_LOGIN"]["workspace_id"] is None


async def test_existing_keys_became_viewer_and_no_one_became_appliance_owner(upgraded) -> None:
    keys = await _fetch(upgraded["dsn"], "SELECT role_cap FROM api_keys")
    owners = await _fetch(upgraded["dsn"], "SELECT count(*) AS n FROM users WHERE is_appliance_owner")
    assert keys == [{"role_cap": "VIEWER"}]
    assert owners[0]["n"] == 0


async def test_the_ledgers_refuse_rewrites_after_the_upgrade(upgraded) -> None:
    for sql in ("UPDATE audit_event SET outcome = 'DENIED'", "DELETE FROM egress_audit"):
        with pytest.raises(sa.exc.DBAPIError, match="append-only"):
            await _execute(upgraded["dsn"], sql)


# --- 0021's precondition ------------------------------------------------------


@pytest.fixture(scope="module")
def with_removed_action(server: str) -> str:
    dsn = _database(server, "removed_action")
    _upgrade_to(BACKEND, dsn, "0020_api_key_role_cap")
    asyncio.run(
        _execute(
            dsn,
            "INSERT INTO audit_event (audit_id, action, outcome) "
            "VALUES (:a, 'AUTH_LOGOUT', 'SUCCESS')",
            a=uuid.uuid4(),
        )
    )
    return dsn


async def _check_precondition_refuses(dsn: str, module: ModuleType) -> None:
    """The check, shared by the test and its negative control."""
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            with pytest.raises(RuntimeError, match="use an action this migration removes"):
                await conn.run_sync(module.assert_no_removed_actions)
    finally:
        await engine.dispose()


async def test_the_upgrade_refuses_a_removed_action_and_keeps_the_row(with_removed_action) -> None:
    await _check_precondition_refuses(with_removed_action, _load_0021())
    result = _alembic(BACKEND, with_removed_action, "upgrade", "head")
    assert result.returncode != 0
    assert "use an action this migration removes" in result.stdout + result.stderr
    rows = await _fetch(with_removed_action, "SELECT action FROM audit_event")
    assert rows == [{"action": "AUTH_LOGOUT"}], "the row was not left alone"
    version = await _fetch(with_removed_action, "SELECT version_num FROM alembic_version")
    assert version == [{"version_num": "0020_api_key_role_cap"}]


# --- ORM vs migrations ----------------------------------------------------------


def _drift(connection: sa.engine.Connection) -> list:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return [
        diff for diff in compare_metadata(context, Base.metadata)
        if not (isinstance(diff, tuple) and diff[0] == "remove_table"
                and getattr(diff[1], "name", None) == "alembic_version")
    ]


async def _check_no_drift(dsn: str) -> None:
    """The check, shared by the test and its negative control."""
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            differences = await conn.run_sync(_drift)
    finally:
        await engine.dispose()
    assert not differences, f"ORM and migrations disagree: {differences}"


def test_the_orm_matches_the_migrated_schema(server: str) -> None:
    dsn = _database(server, "drift")
    _upgrade_to(BACKEND, dsn, "head")
    asyncio.run(_check_no_drift(dsn))


# --- Negative controls ----------------------------------------------------------


async def test_negative_control_without_the_removed_actions_the_row_gets_through(
    with_removed_action, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_0021()
    # Not empty: an empty list renders `IN ()`, a syntax error, and the control
    # would fail for that reason instead of the one it is for.
    monkeypatch.setattr(module, "REMOVED", ("NOT_AN_ACTION",))
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        await _check_precondition_refuses(with_removed_action, module)


def test_negative_control_a_table_outside_the_orm_fails_the_drift_check(server: str) -> None:
    dsn = _database(server, "drift_control")
    _upgrade_to(BACKEND, dsn, "head")
    asyncio.run(_execute(dsn, "CREATE TABLE not_in_the_orm (id int)"))
    with pytest.raises(AssertionError, match="not_in_the_orm"):
        asyncio.run(_check_no_drift(dsn))
