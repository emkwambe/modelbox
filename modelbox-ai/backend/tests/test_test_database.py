"""The suite runs on the database it says it runs on.

"Backend Pytest (Postgres)" runs this whole suite with
``MODELBOX_TEST_DATABASE_URL`` pointing at the appliance's PostgreSQL image.
Two ways it could report green having tested nothing on PostgreSQL:

* the variable is missing, so every engine quietly falls back to SQLite. The
  job therefore also sets ``MODELBOX_TEST_DATABASE_EXPECT=postgresql``, and the
  engine ``_test_db`` hands out must be that dialect and answer a query as it;
* a module builds its own SQLite engine and never asks ``_test_db``. No test
  file but ``_test_db.py`` may name a SQLite URL.

Negative controls (Amendment 2): with the URL removed in-process, the dialect
check fails; given a module that builds its own SQLite engine, the structural
check fails.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._test_db import DATABASE_ENV, make_test_engine

EXPECT_ENV = "MODELBOX_TEST_DATABASE_EXPECT"
TESTS = Path(__file__).resolve().parent
SQLITE_URL = "sqlite+" + "aiosqlite"  # split so this file does not match its own check


async def _check_dialect(expected: str) -> None:
    """The check, shared by the test and its negative control."""
    engine = make_test_engine()
    try:
        assert engine.dialect.name == expected, (
            f"tests ran on {engine.dialect.name}, not {expected}"
        )
        # Answered by the server itself, not by the dialect SQLAlchemy chose.
        query = "SELECT version()" if expected == "postgresql" else "SELECT sqlite_version()"
        async with engine.connect() as conn:
            version = str((await conn.execute(text(query))).scalar())
        assert version, "the database answered no version"
    finally:
        await engine.dispose()


def _modules_naming_sqlite(sources: dict[str, str]) -> list[str]:
    return sorted(
        name for name, source in sources.items() if name != "_test_db.py" and SQLITE_URL in source
    )


async def test_the_suite_runs_on_the_expected_database() -> None:
    await _check_dialect(os.environ.get(EXPECT_ENV, "sqlite"))


def test_no_test_module_builds_its_own_sqlite_engine() -> None:
    sources = {p.name: p.read_text(encoding="utf-8") for p in TESTS.glob("*.py")}
    assert "_test_db.py" in sources and len(sources) > 20, "test sources not found"
    assert _modules_naming_sqlite(sources) == []


async def test_negative_control_without_the_url_postgresql_is_not_what_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Empty reads as unset in `_test_db`, and setenv cannot pass silently.
    monkeypatch.setenv(DATABASE_ENV, "")
    with pytest.raises(AssertionError, match="tests ran on sqlite, not postgresql"):
        await _check_dialect("postgresql")


def test_negative_control_a_module_with_its_own_sqlite_engine_fails() -> None:
    rogue = f'engine = create_async_engine("{SQLITE_URL}://")'
    with pytest.raises(AssertionError):
        assert _modules_naming_sqlite({"test_rogue.py": rogue}) == []
