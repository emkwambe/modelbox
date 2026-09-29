"""The database every test runs on: SQLite by default, PostgreSQL on request.

Every test that needs a database gets its engine here, so one switch moves the
whole suite. With ``MODELBOX_TEST_DATABASE_URL`` unset, a test gets a private
in-memory SQLite database, as it always has. With it set to a PostgreSQL URL
(the CI job "Backend Pytest (Postgres)"), each call creates a fresh database on
that server, so tests stay as isolated as they are on SQLite; the autouse
fixture in ``conftest.py`` drops them after each test.

A module that builds its own SQLite engine would run on SQLite in the Postgres
job and report green having proved nothing about PostgreSQL, so
``test_test_database.py`` fails on any SQLite URL outside this file, and on a
Postgres job whose engine is not PostgreSQL.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

DATABASE_ENV = "MODELBOX_TEST_DATABASE_URL"

# Databases created during the current test, dropped by drop_test_databases().
_created: list[str] = []


def _server_url() -> str | None:
    return os.environ.get(DATABASE_ENV) or None


def _admin_connection(server: str) -> Any:
    import psycopg2

    url = make_url(server)
    connection = psycopg2.connect(
        host=url.host, port=url.port, user=url.username, password=url.password,
        dbname=url.database or "postgres",
    )
    # CREATE and DROP DATABASE cannot run inside a transaction.
    connection.autocommit = True
    return connection


def _new_database(server: str) -> str:
    """Create an empty database on ``server`` and return its async URL."""
    name = f"mbtest_{uuid.uuid4().hex[:16]}"
    connection = _admin_connection(server)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{name}"')
    finally:
        connection.close()
    _created.append(name)
    return make_url(server).set(database=name).render_as_string(hide_password=False)


def make_test_database_url(sqlite_path: Path) -> str:
    """A URL for code that builds its own engine from settings.

    SQLite: a file at ``sqlite_path``. PostgreSQL: a fresh database.
    """
    server = _server_url()
    if server is None:
        return f"sqlite+aiosqlite:///{sqlite_path}"
    return _new_database(server)


def make_test_engine() -> AsyncEngine:
    """An engine on an empty database of its own."""
    server = _server_url()
    if server is None:
        return create_async_engine(
            "sqlite+aiosqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(_new_database(server))


def drop_test_databases() -> None:
    """Drop every database created during this test (PostgreSQL only)."""
    server = _server_url()
    if server is None or not _created:
        return
    connection = _admin_connection(server)
    try:
        with connection.cursor() as cursor:
            while _created:
                cursor.execute(f'DROP DATABASE IF EXISTS "{_created.pop()}" WITH (FORCE)')
    finally:
        connection.close()
