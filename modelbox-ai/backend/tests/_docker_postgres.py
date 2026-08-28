"""Host-port handling for the throwaway Postgres the migration gates use.

Shared rather than copied into both migration modules. The port logic has now
been wrong twice in two different ways, and a copy in each file is how one gets
fixed and the other quietly keeps the defect.

**Why publishing port 0 and reading it back, rather than probing.** Sprint 2
found a *fixed* port silently binding to a previous run's container, so the test
migrated one database while asserting against another. The fix was to probe for
a free ephemeral port. But probing binds a socket, reads its number, and closes
it before Docker binds — and in that window anything else may take the port.
That is the same defect an order smaller: still a race, just a shorter one. The
migration gate failed once in Sprint 4 and once in Sprint 5, both times while
other containers were starting, and passed on every isolated re-run.

Publishing `0:5432` removes the interval instead of shortening it. Docker binds
first and reports what it bound; there is no moment when the port is chosen but
unheld.

**Why reachability is asserted separately.** `docker exec … pg_isready` asks the
server *inside* the container whether it is accepting connections. That is true
whether or not the published mapping works, while the test connects through
`localhost:<port>`. A readiness check that cannot fail for the reason the test
would fail is register standard 2 — a test must verify its own preconditions —
and it is what let a broken publish read as a healthy database.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time

import pytest

DOCKER = shutil.which("docker")


def published_port(container: str, container_port: int = 5432) -> str:
    """The host port Docker actually bound for ``container_port``.

    ``docker port`` may report both an IPv4 and an IPv6 mapping; either answers
    the question, so the first line wins. It can also be briefly empty straight
    after ``docker run -d``, before the port bookkeeping settles.
    """
    for _ in range(30):
        result = subprocess.run(
            [DOCKER, "port", container, str(container_port)],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        if lines:
            return lines[0].rsplit(":", 1)[1].strip()
        time.sleep(0.5)
    pytest.fail(
        f"docker published no host port for {container}:{container_port}, so the "
        f"database the test would connect to does not exist"
    )


def assert_reachable_from_host(port: str, timeout_seconds: int = 30) -> None:
    """Fail unless the published port answers on the host.

    This is the path the test's DSN actually uses. Asserting it here means a
    publish that did not take fails as itself, rather than surfacing later as a
    connection error inside a migration step and reading like a migration bug.

    Mutation, 2026-08-28: returning ``published_port() + 1`` — a port nothing is
    listening on, which is exactly what losing the race would produce — fails
    here with "reported ready inside the container but 127.0.0.1:32771 is not
    reachable from the host", naming the port. Without this check that mutant
    reaches the first migration step and fails there instead, where it reads as
    a migration defect rather than a harness one.
    """
    deadline = time.time() + timeout_seconds
    last: OSError | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
                return
        except OSError as exc:
            last = exc
            time.sleep(0.5)
    pytest.fail(
        f"postgres reported ready inside the container but 127.0.0.1:{port} is "
        f"not reachable from the host: {last}"
    )


__all__ = ["DOCKER", "assert_reachable_from_host", "published_port"]
