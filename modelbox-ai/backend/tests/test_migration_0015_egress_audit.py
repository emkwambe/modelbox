"""Migration 0015 against a **populated** database (D3, D4).

An empty-database migration test proves the DDL parses. What matters for the
egress ledger is narrower and sharper than for 0013, because 0015 adds a table
and backfills nothing:

* the database actually *reaches* 0015 — read back from ``alembic current``,
  not inferred from an exit code (standard 2). This revision id is 21
  characters and ``alembic_version.version_num`` is ``VARCHAR(32)``; an id that
  overran would raise ``StringDataRightTruncation`` at the very end of an
  otherwise successful upgrade, on a real database only. Nothing but a real
  database can establish that it fits;
* the shape is checked with **raw SQL, not through the ORM** (standard 1). The
  ORM model and the migration are two independent statements of the same
  schema, and reading the table back through the model that declares it would
  let them agree with each other while both differ from the database;
* the two rulings that make this table an audit trail are asserted as
  behaviour, because both are deliberate deviations from the conventions used
  everywhere else in this schema and both are the kind of thing a later author
  tidies up. See ``test_deleting_a_workspace_does_not_erase_what_it_sent``.

Requires Docker. Skipped when unavailable, unless MODELBOX_MIGRATION_STRICT=1.
"""

from __future__ import annotations

import socket
import subprocess
import time
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

# Imported rather than copied. `_upgrade_to` carries the M1 fix — it resolves
# what `head` actually is and asserts the database reports it — and a second
# hand-written copy of a read-back guard is exactly how that defect would come
# back in a new disguise.
from tests.test_migration_0013_populated import (
    BACKEND,
    DOCKER,
    _need_docker,
    _run_helper,
    _upgrade_to,
)

PRE_LEDGER_REVISION = "0014_add_suggested_metrics"
LEDGER_REVISION = "0015_add_egress_audit"

EXPECTED_COLUMNS = {
    "egress_id": ("uuid", "NO"),
    "attempt_id": ("uuid", "NO"),
    "event": ("character varying", "NO"),
    "task": ("character varying", "NO"),
    "provider": ("character varying", "NO"),
    "egress_class": ("character varying", "NO"),
    "prompt_sha256": ("character varying", "NO"),
    "prompt_chars": ("integer", "NO"),
    "model_id": ("uuid", "YES"),
    "user_id": ("uuid", "YES"),
    "workspace_id": ("uuid", "YES"),
    "prompt_tokens": ("integer", "YES"),
    "completion_tokens": ("integer", "YES"),
    "error": ("character varying", "YES"),
    "occurred_at": ("timestamp with time zone", "NO"),
}


@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    """A throwaway Postgres, torn down whatever the outcome."""
    _need_docker()
    name = f"modelbox-egress-{uuid.uuid4().hex[:8]}"
    # An ephemeral port, not a fixed one: a fixed port silently binds to a
    # previous run's container, and the test then migrates one database while
    # asserting against another (Sprint 2 harness bug, register standard 2).
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = str(probe.getsockname()[1])
    subprocess.run(
        [DOCKER, "run", "-d", "--name", name,
         "-e", "POSTGRES_PASSWORD=verify", "-e", "POSTGRES_USER=verify",
         "-e", "POSTGRES_DB=verify", "-p", f"{port}:5432",
         "postgres:16-alpine"],
        check=True, capture_output=True, text=True,
    )
    try:
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
        yield f"postgresql+asyncpg://verify:verify@localhost:{port}/verify"
    finally:
        subprocess.run([DOCKER, "rm", "-f", name], capture_output=True, check=False)


@pytest.fixture(scope="module")
def populated_then_migrated(postgres_dsn: str) -> str:
    """Migrate to 0014, put real data in, *then* apply 0015.

    The ordering is the whole point of the word "populated". Applying 0015 to an
    empty database exercises the DDL and nothing else; the question is whether
    an appliance carrying a customer's models survives the upgrade, and that
    question cannot be asked of an empty schema.
    """
    _upgrade_to(BACKEND, postgres_dsn, PRE_LEDGER_REVISION)
    seeded = _run_helper(BACKEND, postgres_dsn, "seed-and-export")
    assert seeded["models"], "fixture sanity: nothing was seeded before the upgrade"
    _upgrade_to(BACKEND, postgres_dsn, LEDGER_REVISION)
    return postgres_dsn


async def _fetch(dsn: str, query: str, **params: object) -> list[dict]:
    """Raw SQL on a connection of its own — never through the application ORM."""
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


# ---------------------------------------------------------------------------
# The database reached 0015, and the models that were there still are
# ---------------------------------------------------------------------------
@pytest.mark.slow
async def test_the_upgrade_preserves_the_persisted_models(
    populated_then_migrated: str,
) -> None:
    """0015 is purely additive, so every seeded model must still be there.

    Counted with SQL rather than re-running the exporter: this migration adds a
    table and touches no emitter, so the property at stake is that nothing was
    lost, not that artifacts are byte-stable (which 0013's gate covers, and
    which standard 6 says must not be fused into one assertion).
    """
    rows = await _fetch(
        populated_then_migrated,
        "SELECT count(*) AS n FROM data_models",
    )
    assert rows[0]["n"] > 0, "the upgrade ran against an empty database"

    entities = await _fetch(
        populated_then_migrated,
        "SELECT count(*) AS n FROM model_entities",
    )
    assert entities[0]["n"] > 0


@pytest.mark.slow
async def test_the_ledger_table_has_the_declared_shape(
    populated_then_migrated: str,
) -> None:
    """Checked against ``information_schema``, outside the ORM entirely."""
    rows = await _fetch(
        populated_then_migrated,
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'egress_audit'
        """,
    )
    actual = {
        r["column_name"]: (r["data_type"], r["is_nullable"]) for r in rows
    }
    assert actual == EXPECTED_COLUMNS


@pytest.mark.slow
async def test_the_event_check_constraint_rejects_an_unknown_event(
    populated_then_migrated: str,
) -> None:
    """The guard is pointed at something that must fail (standard 13).

    A CHECK constraint that was never observed rejecting anything is an
    untested claim — and this one is easy to get wrong, since a constraint
    written against the wrong column name still creates cleanly and then
    permits everything.
    """
    good = {
        "attempt_id": uuid.uuid4(), "event": "ATTEMPT", "task": "synthesis",
        "provider": "local_ollama", "egress_class": "local",
        "prompt_sha256": "0" * 64, "prompt_chars": 12,
    }
    insert = """
        INSERT INTO egress_audit
            (attempt_id, event, task, provider, egress_class,
             prompt_sha256, prompt_chars)
        VALUES
            (:attempt_id, :event, :task, :provider, :egress_class,
             :prompt_sha256, :prompt_chars)
    """
    # The permitted value must succeed, or the rejection below proves nothing
    # about the constraint — a broken INSERT would fail identically.
    await _execute(populated_then_migrated, insert, **good)

    with pytest.raises(Exception, match="ck_egress_audit_event"):
        await _execute(populated_then_migrated, insert, **{**good, "event": "EDITED"})


@pytest.mark.slow
async def test_the_ledger_carries_no_foreign_keys(
    populated_then_migrated: str,
) -> None:
    """Deliberately unlike every other table here, and asserted so it stays that way.

    Every other relationship in this schema cascades, correctly. This one must
    not, and the reason is not visible from the column names — which is exactly
    why a future author applying the house convention would add them.
    """
    rows = await _fetch(
        populated_then_migrated,
        """
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = 'egress_audit' AND constraint_type = 'FOREIGN KEY'
        """,
    )
    assert rows == [], (
        "a foreign key on the ledger would let a cascade delete the record of "
        f"what was sent: {rows}"
    )


@pytest.mark.slow
async def test_deleting_a_workspace_does_not_erase_what_it_sent(
    populated_then_migrated: str,
) -> None:
    """The property the no-foreign-key ruling exists for, asserted as behaviour.

    Stronger than reading constraint metadata: this fails if a cascade is ever
    introduced by any route — a foreign key, a trigger, or application code —
    rather than only if someone adds the specific constraint the previous test
    looks for.
    """
    dsn = populated_then_migrated
    workspace_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    await _execute(
        dsn,
        "INSERT INTO workspaces (workspace_id, name) VALUES (:id, :name)",
        id=workspace_id, name="doomed",
    )
    await _execute(
        dsn,
        """
        INSERT INTO egress_audit
            (attempt_id, event, task, provider, egress_class,
             prompt_sha256, prompt_chars, workspace_id)
        VALUES
            (:attempt_id, 'ATTEMPT', 'synthesis', 'anthropic_cloud', 'cloud',
             :digest, 42, :workspace_id)
        """,
        attempt_id=attempt_id, digest="a" * 64, workspace_id=workspace_id,
    )

    await _execute(
        dsn, "DELETE FROM workspaces WHERE workspace_id = :id", id=workspace_id
    )

    gone = await _fetch(
        dsn, "SELECT count(*) AS n FROM workspaces WHERE workspace_id = :id",
        id=workspace_id,
    )
    assert gone[0]["n"] == 0, "fixture sanity: the workspace was not deleted"

    survived = await _fetch(
        dsn,
        "SELECT workspace_id FROM egress_audit WHERE attempt_id = :id",
        id=attempt_id,
    )
    assert len(survived) == 1, (
        "deleting a workspace erased the record of what it sent to a provider"
    )
    assert survived[0]["workspace_id"] == workspace_id, (
        "the attribution was nulled out, which loses the answer to 'who sent this'"
    )
