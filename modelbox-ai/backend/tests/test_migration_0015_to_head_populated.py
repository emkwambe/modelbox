"""Migrations 0015 → head against a populated database, and ORM-vs-migration drift.

Sprint 7 Step 3.3. Requires Docker; skips without it unless
MODELBOX_MIGRATION_STRICT=1, where it fails instead (CI runs it strict).

**Populated upgrade.** Data is written at the revision where its tables looked
the way they did, then the database is upgraded to head and read back with raw
SQL, never through the ORM (register standard 1):

* at 0015, real models (the gold graphs), written by the v1.11.1 release's
  own code from a worktree at its tag, and egress-ledger rows;
* at 0019, audit rows with and without a workspace (no ``scope`` column yet),
  a user, and an API key (no ``role_cap`` column yet);
* at 0024, a model in the shape keys had before 0025 (column flags and
  relationship column ids), covering every case 0025 converts or lists;
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
from pathlib import Path
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
    wait_for_queries,
)
from tests.test_migration_0013_populated import (
    BACKEND,
    DOCKER,
    _alembic,
    _need_docker,
    _run_helper,
    _upgrade_to,
    release_checkout,
)

MIGRATION_0021 = BACKEND / "alembic" / "versions" / "0021_audit_scope_and_owner.py"


@pytest.fixture(scope="module")
def release_worktree(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The models written at 0015 come from the code that shipped with that schema."""
    yield from release_checkout(tmp_path_factory)


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
        wait_for_queries(port)
        yield f"postgresql+asyncpg://verify:verify@localhost:{port}/{{db}}"
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
def upgraded(server: str, release_worktree: Path) -> dict:
    dsn = _database(server, "populated")
    seeded: dict = {"release_worktree": release_worktree}
    asyncio.run(_populate_and_upgrade(dsn, seeded))
    # The gold models, plus the one written in the pre-0025 shape at 0024.
    return {"dsn": dsn, "models": len(seeded["models"]) + 1, "legacy_model": seeded["legacy_model"]}


async def _populate_and_upgrade(dsn: str, seeded: dict) -> None:
    _upgrade_to(BACKEND, dsn, "0015_add_egress_audit")
    seeded.update(_run_helper(seeded["release_worktree"], dsn, "seed-and-export"))
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

    _upgrade_to(BACKEND, dsn, "0024_column_source_type")
    seeded["legacy_model"] = await _seed_legacy_keys(dsn, workspace_id)

    _upgrade_to(BACKEND, dsn, "head")


async def _seed_legacy_keys(dsn: str, workspace_id: uuid.UUID) -> uuid.UUID:
    """A model in the shape keys had before 0025: column flags and column ids.

    Every case 0025 converts, and every case it can only list:
    customer  id PK; email UNIQUE with a CHECK             -> exact
    invoice   customer_id: a relationship with no columns   -> kept unresolved, listed
    note      customer_ref: reference_target, no relationship -> becomes a relationship, listed
              ghost_ref: reference_target to a missing entity -> listed
              loose_fk: is_foreign_key, no target at all      -> listed
    shipment  half_id: a relationship with only its from column -> kept with that column, listed
              wrong_ref: reference_target contradicting its relationship -> relationship kept, listed
    """
    model_id = uuid.uuid4()
    await _execute(dsn, "INSERT INTO data_models (model_id, workspace_id, title, target_dialect) "
                        "VALUES (:m, :w, 'legacy keys', 'postgres')", m=model_id, w=workspace_id)
    entities = {name: uuid.uuid4() for name in ("customer", "invoice", "note", "shipment")}
    for name, entity_id in entities.items():
        await _execute(dsn, "INSERT INTO model_entities (entity_id, model_id, entity_name, entity_type) "
                            "VALUES (:e, :m, :n, 'TABLE')", e=entity_id, m=model_id, n=name)
    columns: dict[tuple[str, str], uuid.UUID] = {}
    spec = [  # (entity, column, is_pk, is_fk, is_unique, check, reference)
        ("customer", "id", True, False, False, None, None),
        ("customer", "email", False, False, True, "email LIKE '%@%'", None),
        ("invoice", "id", True, False, False, None, None),
        ("invoice", "customer_id", False, True, False, None, None),
        ("note", "id", True, False, False, None, None),
        ("note", "customer_ref", False, True, False, None, "customer.id"),
        ("note", "ghost_ref", False, True, False, None, "ghost.id"),
        ("note", "loose_fk", False, True, False, None, None),
        ("shipment", "id", True, False, False, None, None),
        ("shipment", "half_id", False, True, False, None, None),
        ("shipment", "wrong_ref", False, True, False, None, "invoice.id"),
    ]
    for position, (entity, column, pk, fk, unique, check, reference) in enumerate(spec):
        column_id = columns[(entity, column)] = uuid.uuid4()
        await _execute(
            dsn,
            "INSERT INTO entity_columns (column_id, entity_id, column_name, data_type, is_primary_key, "
            "is_foreign_key, is_unique, check_expression, reference_target, is_nullable, ordinal_position, "
            "stable_id) VALUES (:c, :e, :n, 'INTEGER', :pk, :fk, :u, :ck, :ref, :nullable, :pos, :sid)",
            c=column_id, e=entities[entity], n=column, pk=pk, fk=fk, u=unique, ck=check, ref=reference,
            nullable=not pk, pos=position, sid=position + 1)
    relationships = [  # (from entity, from column, to entity, to column)
        ("invoice", None, "customer", None),
        ("shipment", "half_id", "invoice", None),
        ("shipment", "wrong_ref", "customer", "id"),
    ]
    for from_entity, from_column, to_entity, to_column in relationships:
        await _execute(
            dsn,
            "INSERT INTO entity_relationships (relationship_id, model_id, from_entity_id, from_column_id, "
            "to_entity_id, to_column_id, cardinality) VALUES (:r, :m, :fe, :fc, :te, :tc, 'N:1')",
            r=uuid.uuid4(), m=model_id, fe=entities[from_entity],
            fc=columns.get((from_entity, from_column or "")), te=entities[to_entity],
            tc=columns.get((to_entity, to_column or "")))
    return model_id


async def test_0025_converts_flags_into_constraints_exactly(upgraded) -> None:
    rows = await _fetch(
        upgraded["dsn"],
        "SELECT e.entity_name, k.kind, k.expression, "
        "  (SELECT string_agg(column_name, ',' ORDER BY position) FROM entity_constraint_columns "
        "   WHERE constraint_id = k.constraint_id) AS columns "
        "FROM entity_constraints k JOIN model_entities e ON e.entity_id = k.entity_id "
        "WHERE e.model_id = :m ORDER BY e.entity_name, k.position",
        m=upgraded["legacy_model"])
    assert [(r["entity_name"], r["kind"], r["expression"], r["columns"]) for r in rows] == [
        ("customer", "PRIMARY KEY", None, "id"),
        ("customer", "UNIQUE", None, "email"),
        ("customer", "CHECK", "email LIKE '%@%'", "email"),
        ("invoice", "PRIMARY KEY", None, "id"),
        ("note", "PRIMARY KEY", None, "id"),
        ("shipment", "PRIMARY KEY", None, "id"),
    ]


async def test_0025_keeps_every_relationship_and_lists_what_it_could_not_convert(upgraded) -> None:
    dsn, model = upgraded["dsn"], upgraded["legacy_model"]
    relationships = await _fetch(
        dsn,
        "SELECT f.entity_name AS from_entity, t.entity_name AS to_entity, "
        "  (SELECT string_agg(coalesce(from_column_name, '?') || '>' || coalesce(to_column_name, '?'), ',' "
        "   ORDER BY position) FROM relationship_columns WHERE relationship_id = r.relationship_id) AS pairs "
        "FROM entity_relationships r JOIN model_entities f ON f.entity_id = r.from_entity_id "
        "JOIN model_entities t ON t.entity_id = r.to_entity_id WHERE r.model_id = :m "
        "ORDER BY f.entity_name, t.entity_name", m=model)
    assert [(r["from_entity"], r["to_entity"], r["pairs"]) for r in relationships] == [
        ("invoice", "customer", None),              # kept, unresolved
        ("note", "customer", "customer_ref>id"),    # a reference that became a relationship
        ("shipment", "customer", "wrong_ref>id"),   # the relationship wins over its reference
        ("shipment", "invoice", "half_id>?"),       # kept with the one column it had
    ]
    findings = await _fetch(
        dsn, "SELECT kind, entity_name, revision FROM model_conversion_findings WHERE model_id = :m "
             "ORDER BY kind, entity_name", m=model)
    assert [(f["kind"], f["entity_name"]) for f in findings] == [
        # invoice.customer_id was flagged, but its relationship names no column.
        ("foreign_key_without_target", "invoice"),
        ("foreign_key_without_target", "note"),
        ("partly_resolved_relationship", "shipment"),
        ("reference_became_relationship", "note"),
        ("reference_contradicts_relationship", "shipment"),
        ("reference_target_missing", "note"),
        ("unresolved_relationship", "invoice"),
    ]
    assert {f["revision"] for f in findings} == {"0025_keys_and_constraints"}


async def test_0025_converts_the_seeded_gold_models_with_nothing_to_list(upgraded) -> None:
    """The models v1.11.1 wrote convert with nothing listed: no finding, and
    every relationship has a complete column pair. (Key order and whole-graph
    equality across a release boundary are test_migration_0013_populated's.)"""
    dsn = upgraded["dsn"]
    findings = await _fetch(dsn, "SELECT count(*) AS n FROM model_conversion_findings WHERE model_id <> :m",
                            m=upgraded["legacy_model"])
    assert findings[0]["n"] == 0
    unpaired = await _fetch(
        dsn, "SELECT count(*) AS n FROM entity_relationships r WHERE r.model_id <> :m AND NOT EXISTS "
             "(SELECT 1 FROM relationship_columns p WHERE p.relationship_id = r.relationship_id "
             " AND p.from_column_name IS NOT NULL AND p.to_column_name IS NOT NULL)",
        m=upgraded["legacy_model"])
    assert unpaired[0]["n"] == 0
    keys = await _fetch(
        dsn, "SELECT count(*) AS n FROM entity_constraints k JOIN model_entities e ON e.entity_id = k.entity_id "
             "WHERE k.kind = 'PRIMARY KEY' AND e.model_id <> :m", m=upgraded["legacy_model"])
    assert keys[0]["n"] > 0, "fixture sanity: the seeded models have primary keys"


async def test_the_database_reached_head(upgraded) -> None:
    rows = await _fetch(upgraded["dsn"], "SELECT version_num FROM alembic_version")
    assert rows == [{"version_num": "0025_keys_and_constraints"}]


async def test_models_from_before_0023_are_not_marked_imported(upgraded) -> None:
    """0023 adds no backfill: an existing model was not imported, and NULL says so."""
    rows = await _fetch(
        upgraded["dsn"],
        "SELECT count(*) AS n FROM data_models "
        "WHERE reconciliation_status IS NULL AND import_report IS NULL",
    )
    assert rows[0]["n"] == upgraded["models"]


async def test_columns_from_before_0024_have_no_source_type(upgraded) -> None:
    """0024 adds no backfill: a column that was not imported declared no type text."""
    rows = await _fetch(
        upgraded["dsn"],
        "SELECT count(*) AS n, count(source_data_type) AS typed FROM entity_columns",
    )
    assert rows[0]["n"] > 0, "fixture sanity: the seed created no columns"
    assert rows[0]["typed"] == 0


async def test_0023_refuses_an_unknown_reconciliation_status(upgraded) -> None:
    with pytest.raises(sa.exc.IntegrityError, match="ck_data_models_reconciliation_status"):
        await _execute(upgraded["dsn"], "UPDATE data_models SET reconciliation_status = 'partly'")


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
