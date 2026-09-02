"""Prove the appliance can be restored from a backup (G12).

G12 asks for a written availability position with a **tested** restore. A
runbook nobody has executed is a hypothesis, and the failure it hides is the
common one: a backup that dumps cleanly and restores into a database the
application then refuses to start against, because the schema version and the
code no longer agree.

So this script does the whole loop against a real PostgreSQL 16 — the same image
the appliance ships — and fails loudly at every step it cannot complete:

    1. start a database
    2. bring it to head with the real Alembic migrations
    3. write a known row
    4. pg_dump
    5. **destroy the database and its volume entirely**
    6. start a new one, restore, and verify

Step 5 is the point. A restore tested by dropping a table proves the dump
contains that table; a restore tested by destroying the volume proves the dump
is sufficient on its own, which is the claim an operator actually needs.

Step 6 verifies two things, not one. The row is the obvious check. The Alembic
revision is the check that matters, because a restored database at the wrong
revision accepts a connection, serves reads, and fails the next deployment — the
failure arrives days later and looks like a release problem.

Run:  .venv/Scripts/python -m scripts.verify_restore
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]

IMAGE = "postgres:16-alpine"
CONTAINER = "modelbox-restore-test"
VOLUME = "modelbox-restore-test-data"
PASSWORD = "restoretest"
DB = "modelbox_metadata"
USER = "modelbox"
PORT = "55432"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def must(cmd: list[str], what: str, **kw) -> subprocess.CompletedProcess:
    """Run a step, and stop the moment it fails.

    Every step here is a precondition for the next, so a failure that is
    tolerated produces a "restore verified" line that means nothing — which is
    the exact shape of claim this repository refuses to make.
    """
    proc = run(cmd, **kw)
    if proc.returncode != 0:
        print(f"FAILED: {what}\n$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
        sys.exit(1)
    return proc


def teardown() -> None:
    run(["docker", "rm", "-f", CONTAINER])
    run(["docker", "volume", "rm", "-f", VOLUME])


def start_db() -> None:
    must(
        [
            "docker", "run", "-d", "--name", CONTAINER,
            "-e", f"POSTGRES_USER={USER}",
            "-e", f"POSTGRES_PASSWORD={PASSWORD}",
            "-e", f"POSTGRES_DB={DB}",
            "-v", f"{VOLUME}:/var/lib/postgresql/data",
            "-p", f"{PORT}:5432",
            IMAGE,
        ],
        "start postgres",
    )
    for _ in range(60):
        if run(
            ["docker", "exec", CONTAINER, "pg_isready", "-U", USER, "-d", DB]
        ).returncode == 0:
            return
        time.sleep(1)
    print("FAILED: postgres never became ready")
    sys.exit(1)


def main() -> int:
    if run(["docker", "version"]).returncode != 0:
        print("FAILED: docker is not available")
        return 1

    url = f"postgresql+asyncpg://{USER}:{PASSWORD}@localhost:{PORT}/{DB}"
    marker = str(uuid.uuid4())
    dump = _BACKEND / ".restore-test.sql"

    teardown()
    try:
        print("1. starting a database")
        start_db()

        print("2. migrating to head")
        must(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            "alembic upgrade",
            cwd=_BACKEND,
            env={**_env(), "DATABASE_URL": url},
        )
        head = must(
            ["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", DB, "-tAc",
             "SELECT version_num FROM alembic_version"],
            "read alembic version",
        ).stdout.strip()
        print(f"   at revision {head}")

        print("3. writing a known row")
        must(
            ["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", DB, "-c",
             f"INSERT INTO workspaces (workspace_id, name) VALUES (gen_random_uuid(), '{marker}')"],
            "insert marker row",
        )

        print("4. pg_dump")
        out = must(
            ["docker", "exec", CONTAINER, "pg_dump", "-U", USER, "-d", DB],
            "pg_dump",
        ).stdout
        dump.write_text(out, encoding="utf-8")
        print(f"   {len(out.splitlines())} lines, {dump.stat().st_size} bytes")

        print("5. destroying the database AND its volume")
        teardown()
        if run(["docker", "volume", "inspect", VOLUME]).returncode == 0:
            print("FAILED: the volume still exists; the test would be meaningless")
            return 1

        print("6. restoring into a new database")
        start_db()
        restore = run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", USER, "-d", DB],
            input=dump.read_text(encoding="utf-8"),
        )
        if restore.returncode != 0:
            print(f"FAILED: restore\n{restore.stderr}")
            return 1

        rows = must(
            ["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", DB, "-tAc",
             f"SELECT count(*) FROM workspaces WHERE name = '{marker}'"],
            "read marker row back",
        ).stdout.strip()
        after = must(
            ["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", DB, "-tAc",
             "SELECT version_num FROM alembic_version"],
            "read alembic version after restore",
        ).stdout.strip()

        ok = rows == "1" and after == head
        print(f"   marker rows: {rows} (want 1)")
        print(f"   revision:    {after} (want {head})")
        print("RESTORE VERIFIED" if ok else "RESTORE FAILED")
        return 0 if ok else 1
    finally:
        teardown()
        dump.unlink(missing_ok=True)


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
