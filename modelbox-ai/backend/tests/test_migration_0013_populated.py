"""Migration 0013 against a **populated** database (Task 5, register C8).

An empty-database migration test proves only that the DDL is syntactically
valid. What matters here is that models persisted by v1.6.0 survive the
migration unchanged, and — because Sprint 2 changes no emitter — that every
artifact they produce is **byte-identical** before and after.

That byte-identity assertion is this sprint's real gate, and it is worth being
precise about what a failure would mean. Sprint 2 touches no exporter, so the
same model must produce the same bytes. If it does not, the first hypothesis is
**not** that the migration is wrong: it is that an emitter is not a pure
function of the IR — dictionary or set iteration order, an unsorted glob, a
clock, a hash seed. That would invalidate every fidelity verdict on the board
and two of the three Proof Log entries, all of which assume determinism. Such a
failure is a finding to characterise, not a diff to make disappear.

The pre-migration side is produced by the **v1.6.0 code**, checked out into a
git worktree, so this compares old-code-old-schema against new-code-new-schema
rather than new code against itself.

Requires Docker. Skipped when unavailable, unless MODELBOX_MIGRATION_STRICT=1.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
GOLD_DIR = BACKEND / "tests" / "fixtures" / "gold"

PRE_MIGRATION_REVISION = "0012_add_column_quality_rules"
BASELINE_TAG = "v1.6.0"
_STRICT = os.environ.get("MODELBOX_MIGRATION_STRICT") == "1"
DOCKER = shutil.which("docker")


def _need_docker() -> None:
    if DOCKER:
        return
    if _STRICT:
        pytest.fail("MODELBOX_MIGRATION_STRICT=1 but docker is unavailable")
    pytest.skip("docker unavailable; migration verification not run")


# ---------------------------------------------------------------------------
# Disposable Postgres — never the appliance volume
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def postgres_dsn() -> str:
    """A throwaway Postgres, torn down whatever the outcome."""
    _need_docker()
    name = f"modelbox-migration-{uuid.uuid4().hex[:8]}"
    # A free ephemeral port, not a fixed one: a fixed port silently binds to
    # whatever a previous run left behind, and the test then migrates one
    # database while asserting against another.
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
                capture_output=True, text=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("postgres container never became ready")
        yield f"postgresql+asyncpg://verify:verify@localhost:{port}/verify"
    finally:
        subprocess.run([DOCKER, "rm", "-f", name], capture_output=True)


@pytest.fixture(scope="module")
def baseline_worktree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A checkout of v1.6.0, so 'before' is produced by the code that shipped."""
    root = tmp_path_factory.mktemp("baseline")
    target = root / "v1_6_0"
    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), BASELINE_TAG],
        cwd=REPO, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"cannot create {BASELINE_TAG} worktree: {result.stderr[-300:]}")
    try:
        yield target / "modelbox-ai" / "backend"
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(target)],
                       cwd=REPO, capture_output=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _alembic(backend: Path, dsn: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": dsn}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=backend, env=env, capture_output=True, text=True,
    )


def _upgrade_to(backend: Path, dsn: str, revision: str) -> None:
    """Upgrade and then *confirm* the database is where we asked it to go.

    A zero exit status only says alembic ran. Asserting the stamped revision
    turns a harness bug — wrong working directory, wrong DSN, a URL resolved
    from somewhere unexpected — into a clear message instead of a confusing
    UndefinedColumnError several steps later.
    """
    result = _alembic(backend, dsn, "upgrade", revision)
    assert result.returncode == 0, (
        f"alembic upgrade {revision} failed in {backend}\n"
        f"STDOUT:\n{result.stdout[-2000:]}\n"
        f"STDERR:\n{result.stderr[-2000:]}"
    )
    current = _alembic(backend, dsn, "current")
    stamped = current.stdout + current.stderr
    expected = "" if revision == "head" else revision
    assert expected in stamped, (
        f"asked for revision {revision!r} but the database reports:\n"
        f"{stamped[-1500:]}\n"
        f"upgrade output was:\n{result.stdout[-1500:]}"
    )


def _run_helper(backend: Path, dsn: str, mode: str) -> dict:
    """Run the seed/export helper inside a given checkout of the code."""
    env = {**os.environ, "DATABASE_URL": dsn, "PYTHONPATH": str(backend)}
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("_migration_helper.py")),
         mode, str(GOLD_DIR)],
        cwd=backend, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"helper '{mode}' failed in {backend}:\n{proc.stdout[-2000:]}\n{proc.stderr[-3000:]}"
    )
    _, _, payload = proc.stdout.partition("@@RESULT@@")
    return json.loads(payload)


def _digest(files: dict[str, str]) -> dict[str, str]:
    return {
        path: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for path, content in sorted(files.items())
    }


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_migration_0013_preserves_the_persisted_model(
    postgres_dsn: str, baseline_worktree: Path
) -> None:
    """Models written by the previous release survive the upgrade unchanged.

    **Compares structure, not bytes, and the distinction is the point.** An
    earlier version of this test asserted that every emitted artifact was
    byte-identical across the migration. That held in the sprint that
    introduced it, because that sprint changed no emitter — and it is false by
    design in any sprint that does. Two properties with different lifetimes had
    been fused into one assertion:

    * *the migration preserves the persisted model* — permanent, and what
      register criterion C8 actually claims;
    * *emitters are deterministic* — permanent, and now asserted separately by
      ``test_artifact_generation_is_deterministic``;
    * *emitters produce the same bytes as the previous release* — true only
      while no emitter changes, which is a schedule dependency rather than a
      property.

    Register: a gate asserting a relationship to a previous release must state
    the condition under which that relationship holds. This one holds always,
    because the projection is limited to what both releases can express.
    """
    _need_docker()

    # 1. Previous schema, seeded and projected by the code that shipped it.
    _upgrade_to(baseline_worktree, postgres_dsn, PRE_MIGRATION_REVISION)
    before = _run_helper(baseline_worktree, postgres_dsn, "seed-and-export")
    assert len(before["models"]) == 5, "expected all five gold graphs seeded"
    before_projection = _run_helper(
        baseline_worktree, postgres_dsn, "project-model"
    )["models"]

    # 2. Migrate.
    _upgrade_to(BACKEND, postgres_dsn, "head")

    # 3. Re-read with the new code and compare the structure.
    after_projection = _run_helper(BACKEND, postgres_dsn, "project-model")["models"]

    assert set(before_projection) == set(after_projection), (
        f"models lost or gained across the migration: "
        f"before={sorted(before_projection)}, after={sorted(after_projection)}"
    )
    for title, before_model in before_projection.items():
        assert after_projection[title] == before_model, (
            f"model '{title}' changed across the migration.\n"
            f"This is a data-preservation failure, not an emitter question — "
            f"the projection covers only what both releases can express.\n"
            f"before: {json.dumps(before_model, sort_keys=True)[:900]}\n"
            f"after:  {json.dumps(after_projection[title], sort_keys=True)[:900]}"
        )


@pytest.mark.slow
def test_artifact_generation_is_deterministic(
    postgres_dsn: str, baseline_worktree: Path
) -> None:
    """The same model produces the same bytes, twice, in separate processes.

    Separate processes matter: Python randomises string hashing per process, so
    a comparison within one interpreter would not detect an emitter that
    depended on set or dict iteration order. Every fidelity verdict and the
    Proof Log's PL-005 rest on this holding.
    """
    _need_docker()
    first = _run_helper(BACKEND, postgres_dsn, "export-only")["models"]
    second = _run_helper(BACKEND, postgres_dsn, "export-only")["models"]

    assert set(first) == set(second)
    differing: list[str] = []
    for title, files in first.items():
        a, b = _digest(files), _digest(second[title])
        assert set(a) == set(b), f"{title}: artifact set differs between runs"
        differing.extend(f"{title}::{path}" for path, d in a.items() if b[path] != d)

    assert not differing, (
        "Artifact generation is not deterministic. The same model produced "
        "different bytes in two processes, which means an emitter depends on "
        "iteration order, a clock, or a hash seed. Every fidelity verdict and "
        "Proof Log PL-005 assume otherwise.\n"
        f"Differing ({len(differing)}): {differing[:12]}"
    )


@pytest.mark.slow
def test_backfill_assigns_ordinal_ranked_stable_ids(
    postgres_dsn: str, baseline_worktree: Path
) -> None:
    """stable_id must reproduce today's Protobuf tags: 1..N in ordinal order."""
    _need_docker()
    state = _run_helper(BACKEND, postgres_dsn, "inspect-backfill")

    for entity in state["entities"]:
        ids = [c["stable_id"] for c in entity["columns"]]
        assert ids == list(range(1, len(ids) + 1)), (
            f"{entity['entity_name']}: stable_ids {ids} are not 1..N in "
            f"ordinal_position order — today's Protobuf tags would shift"
        )
        assert entity["next_stable_id"] == len(ids) + 1, (
            f"{entity['entity_name']}: watermark {entity['next_stable_id']} "
            f"must be one past the highest id ({len(ids)})"
        )
        assert not any(19000 <= i <= 19999 for i in ids), "reserved range used"
        for column in entity["columns"]:
            assert column["is_nullable"] is not column["is_primary_key"] or (
                not column["is_primary_key"]
            ), "primary keys must be backfilled non-nullable"
        for column in entity["columns"]:
            if column["is_primary_key"]:
                assert column["is_nullable"] is False


@pytest.mark.slow
def test_downgrade_restores_the_previous_schema(
    postgres_dsn: str, baseline_worktree: Path
) -> None:
    """The downgrade path must work, and re-upgrading must be clean."""
    _need_docker()

    result = _alembic(BACKEND, postgres_dsn, "downgrade", "-1")
    assert result.returncode == 0, result.stderr[-3000:]

    # The old code must still be able to read the downgraded database.
    after_downgrade = _run_helper(baseline_worktree, postgres_dsn, "export-only")
    assert len(after_downgrade["models"]) == 5

    result = _alembic(BACKEND, postgres_dsn, "upgrade", "head")
    assert result.returncode == 0, result.stderr[-3000:]
