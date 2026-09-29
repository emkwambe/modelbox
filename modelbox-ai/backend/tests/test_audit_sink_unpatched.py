"""The audit sink writes a row with nothing in its path patched.

Every other audit test binds the sink to its test database by patching
`app.core.database.get_sessionmaker`. That is right for those tests and blind
to one failure: a sink calling a name the database module does not have. The
sink imports inside a broad `except` that logs and swallows, so such a sink
records nothing outside tests while every patched test passes.

Here the only change is the database URL, set the way a deployment sets it,
with the engine caches cleared so the real `get_engine()` and
`get_sessionmaker()` build from it. The row is read back with the database's
own driver (`sqlite3`, or `psycopg2` on PostgreSQL), not through the ORM.

A write that fails is logged at ERROR and counted on `/health`, which reports
`degraded` while the count is non-zero.

Negative controls (Amendment 2): with `get_sessionmaker` removed from
`app.core.database` in-process, the unpatched write stores nothing and the
check fails; with the failure counter disabled in-process, `/health` stays
`ok` and its check fails.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from app.core import database
from app.models.metadata_store import Base
from app.services import audit_log
from tests._test_db import make_test_database_url


@pytest.fixture
async def real_sink_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[str]:
    """The real engine and session factory, built from a database URL."""
    url = make_test_database_url(tmp_path / "audit.db")
    monkeypatch.setattr(database.settings, "database_url", url)
    # Held directly: a negative control removes `get_sessionmaker` from the
    # module, and this teardown runs before monkeypatch restores it.
    get_engine, get_sessionmaker = database.get_engine, database.get_sessionmaker
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield url
    await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
def fresh_failure_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_log, "_failures", audit_log._WriteFailures())


def _raw_rows(url: str, email: str) -> list[tuple[str, str, str]]:
    """The audit rows for ``email``, read with the driver rather than the ORM."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        with sqlite3.connect(str(parsed.database)) as conn:
            return conn.execute(
                "SELECT action, outcome, scope FROM audit_event WHERE actor_email = ?", (email,)
            ).fetchall()
    import psycopg2

    conn = psycopg2.connect(
        host=parsed.host, port=parsed.port, user=parsed.username,
        password=parsed.password, dbname=parsed.database,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT action, outcome, scope FROM audit_event WHERE actor_email = %s", (email,)
            )
            return [tuple(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _check_row_written(url: str, email: str) -> None:
    """The check, shared by the test and its negative control."""
    rows = _raw_rows(url, email)
    assert rows == [("AUTH_LOGIN", "SUCCESS", "appliance")], (
        f"the unpatched sink stored {rows!r} for {email}"
    )


async def _health() -> dict:
    from app.main import create_app

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        response = await c.get("/health")
    assert response.status_code == 200
    return response.json()


async def _check_health_reports_one_failure() -> None:
    """The check, shared by the test and its negative control."""
    body = await _health()
    assert body["status"] == "degraded", f"/health reads {body['status']!r} after a failed write"
    assert body["audit"]["write_failures"] == 1
    assert body["audit"]["last_write_failure"]


# --- The unpatched write ------------------------------------------------------


async def test_the_unpatched_sink_writes_a_row(
    real_sink_database: str, fresh_failure_count: None
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    await audit_log.record(action="AUTH_LOGIN", actor_email=email)
    _check_row_written(real_sink_database, email)
    assert audit_log.write_failure_status()["write_failures"] == 0


# --- A failed write is loud ---------------------------------------------------


async def test_health_is_ok_with_no_failed_writes(fresh_failure_count: None) -> None:
    body = await _health()
    assert body["status"] == "ok"
    assert body["audit"] == {"write_failures": 0, "last_write_failure": None}


async def test_a_failed_write_logs_error_and_degrades_health(
    fresh_failure_count: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _unreachable() -> object:
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(database, "get_sessionmaker", _unreachable)
    with caplog.at_level(logging.ERROR, logger="app.services.audit_log"):
        await audit_log.record(action="AUTH_LOGIN", actor_email="a@example.com")
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.getMessage() for r in errors] == [
        "Failed to write audit event AUTH_LOGIN/SUCCESS for actor a@example.com"
    ]
    await _check_health_reports_one_failure()


# --- Negative controls --------------------------------------------------------


async def test_negative_control_without_get_sessionmaker_nothing_is_stored(
    real_sink_database: str, fresh_failure_count: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(database, "get_sessionmaker")
    email = f"{uuid.uuid4().hex}@example.com"
    await audit_log.record(action="AUTH_LOGIN", actor_email=email)
    with pytest.raises(AssertionError, match="the unpatched sink stored \\[\\]"):
        _check_row_written(real_sink_database, email)


async def test_negative_control_without_the_counter_health_stays_ok(
    fresh_failure_count: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _unreachable() -> object:
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(database, "get_sessionmaker", _unreachable)
    monkeypatch.setattr(audit_log, "note_write_failure", lambda: None)
    await audit_log.record(action="AUTH_LOGIN", actor_email="a@example.com")
    with pytest.raises(AssertionError, match="/health reads 'ok' after a failed write"):
        await _check_health_reports_one_failure()
