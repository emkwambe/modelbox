"""The migrate service: migrate as the owner, then set the application role's password.

    python -m app.db_bootstrap

Run by the ``modelbox-migrate`` compose service on every start, before the
backend and worker, with the owner's ``DATABASE_URL`` and
``MODELBOX_APP_DB_PASSWORD``. It:

1. refuses an empty or short application password, naming the variable and
   never its value;
2. applies migrations (``alembic upgrade head``) as the owner;
3. re-asserts ``modelbox_app`` and its grants (``app.db_roles``), which is what
   lets a database restored from a dump start: the role is not in the dump;
4. sets ``modelbox_app`` to LOGIN with the password from ``.env``, so rotating
   the password is changing ``.env`` and re-running this service.

**The password never appears in output or logs.** Postgres quotes it: the
statement is built server-side with ``format('... %L', $1)`` and the password
travels as a bind parameter, so this code never assembles SQL around it. The
session sets ``log_min_error_statement = panic`` first, so a failing statement
is not written to the server log with the password in it. Errors are reported
by type, never by message, since a driver's message may echo its input.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

APP_ROLE = "modelbox_app"
PASSWORD_VARIABLE = "MODELBOX_APP_DB_PASSWORD"
MIN_PASSWORD_BYTES = 32


class BootstrapRefused(Exception):
    """A refusal whose message names no secret."""


def app_password_problem(password: str) -> str | None:
    """Why ``password`` is unusable, naming only the variable, or None."""
    if not password:
        return f"{PASSWORD_VARIABLE} is empty"
    if len(password.encode("utf-8")) < MIN_PASSWORD_BYTES:
        return f"{PASSWORD_VARIABLE} is shorter than {MIN_PASSWORD_BYTES} bytes"
    return None


def describe_failure(exc: BaseException) -> str:
    """What to print for a failure: its type only, never its message."""
    return type(exc).__name__


async def ensure_app_role(connection: Any) -> None:
    """Re-assert the role and its grants (``app.db_roles``); safe to repeat."""
    from app.db_roles import app_role_statements

    for statement in app_role_statements():
        await connection.execute(statement)


async def set_app_password(connection: Any, password: str) -> None:
    """Make the application role LOGIN with ``password``, quoted by Postgres."""
    await connection.execute("SET log_min_error_statement = 'panic'")
    statement = await connection.fetchval(
        f"SELECT format('ALTER ROLE {APP_ROLE} WITH LOGIN PASSWORD %L', $1::text)", password
    )
    await connection.execute(statement)


def _migrate() -> None:
    from alembic.config import Config

    from alembic import command

    config = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    command.upgrade(config, "head")


async def _connect(dsn: str) -> Any:
    import asyncpg

    return await asyncpg.connect(dsn.replace("postgresql+asyncpg://", "postgresql://"))


async def _set_password(dsn: str, password: str) -> None:
    connection = await _connect(dsn)
    try:
        await ensure_app_role(connection)
        await set_app_password(connection, password)
    finally:
        await connection.close()


def main() -> int:
    password = os.environ.get(PASSWORD_VARIABLE, "")
    if (problem := app_password_problem(password)) is not None:
        print(f"db-bootstrap refused: {problem}.", file=sys.stderr)
        return 2
    dsn = os.environ.get("DATABASE_URL", "")
    try:
        _migrate()
        asyncio.run(_set_password(dsn, password))
    except Exception as exc:  # noqa: BLE001 - reported by type; see the module docstring
        print(f"db-bootstrap failed: {describe_failure(exc)}.", file=sys.stderr)
        return 1
    print(f"db-bootstrap: migrated to head; {APP_ROLE} may log in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
