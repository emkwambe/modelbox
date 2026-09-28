"""The migrate service never shows the application role's password.

`app.db_bootstrap` sets `modelbox_app`'s password from `.env` on every run.
These tests need no database: a fake connection records what is sent. They
check the password travels only as a bind parameter (Postgres quotes it with
`format(%L)`), that the server's statement logging is turned down first, and
that neither the success nor the failure path prints any fragment of it, even
when the driver's error message contains it. `test_ledger_roles_postgres.py`
runs the same service against a real Postgres.

Negative control: a failure path that reports the exception's message prints
the password, and the output check catches it.
"""

from __future__ import annotations

from typing import Any

import pytest

from app import db_bootstrap

PASSWORD = "0123456789abcdef" * 4  # 64 characters, like init-env's


class _FakeConnection:
    def __init__(self, fail_with: str | None = None) -> None:
        self.executed: list[str] = []
        self.fetched: list[tuple[str, tuple[Any, ...]]] = []
        self.fail_with = fail_with

    async def execute(self, sql: str, *args: Any) -> None:
        if self.fail_with and sql.startswith("ALTER ROLE"):
            raise RuntimeError(self.fail_with)
        self.executed.append(sql)

    async def fetchval(self, sql: str, *args: Any) -> str:
        self.fetched.append((sql, args))
        # What Postgres's format(%L) would return.
        return f"ALTER ROLE modelbox_app WITH LOGIN PASSWORD '{args[0]}'"

    async def close(self) -> None:
        return None


def _fragments(secret: str) -> list[str]:
    return [secret[i : i + 8] for i in range(len(secret) - 7)]


def _assert_no_password(output: str) -> None:
    leaked = [f for f in _fragments(PASSWORD) if f in output]
    assert not leaked, "the migrate service printed password material"


async def test_the_password_is_a_bind_parameter_and_logging_is_off_first() -> None:
    connection = _FakeConnection()
    await db_bootstrap.set_app_password(connection, PASSWORD)
    assert connection.executed[:2] == [
        "SET log_statement = 'none'",
        "SET log_min_error_statement = 'panic'",
    ]
    (sql, args), = connection.fetched
    assert PASSWORD not in sql, "the password was assembled into SQL here"
    assert args == (PASSWORD,)
    assert "format(" in sql and "%L" in sql


@pytest.mark.parametrize(
    ("password", "reason"),
    # Not a word the message itself uses, so the absence check means something.
    [("", "is empty"), ("q7x-pw", "is shorter than 32 bytes")],
)
def test_an_unusable_password_is_refused_by_name(
    password: str, reason: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MODELBOX_APP_DB_PASSWORD", password)
    assert db_bootstrap.main() == 2
    err = capsys.readouterr().err
    assert f"MODELBOX_APP_DB_PASSWORD {reason}" in err
    if password:
        assert password not in err


def _run_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], connection: _FakeConnection
) -> tuple[int, str]:
    monkeypatch.setenv("MODELBOX_APP_DB_PASSWORD", PASSWORD)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://owner:x@db:5432/m")
    monkeypatch.setattr(db_bootstrap, "_migrate", lambda: None)

    async def connect(dsn: str) -> _FakeConnection:
        return connection

    monkeypatch.setattr(db_bootstrap, "_connect", connect)
    code = db_bootstrap.main()
    out = capsys.readouterr()
    return code, out.out + out.err


def test_success_prints_no_password(monkeypatch, capsys) -> None:
    code, output = _run_main(monkeypatch, capsys, _FakeConnection())
    assert code == 0
    _assert_no_password(output)


def _check_failure_prints_no_password(monkeypatch, capsys) -> None:
    """The check, shared by the test and its negative control."""
    failing = _FakeConnection(fail_with=f"role update failed for '{PASSWORD}'")
    code, output = _run_main(monkeypatch, capsys, failing)
    assert code == 1
    _assert_no_password(output)


def test_a_failure_whose_message_holds_the_password_prints_none(monkeypatch, capsys) -> None:
    _check_failure_prints_no_password(monkeypatch, capsys)


def test_negative_control_reporting_the_message_leaks_the_password(monkeypatch, capsys) -> None:
    monkeypatch.setattr(db_bootstrap, "describe_failure", str)
    with pytest.raises(AssertionError, match="printed password material"):
        _check_failure_prints_no_password(monkeypatch, capsys)
