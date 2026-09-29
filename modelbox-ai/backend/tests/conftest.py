"""Suite-wide fixtures. Kept to what every test needs; see ``_test_db.py``.

This file is loaded for every test, including the fidelity harness, which runs
in the separate tools environment (``requirements-dev.txt``) where SQLAlchemy
is not installed. So it imports nothing beyond pytest at module level, and
reaches ``_test_db`` only when a test database server is configured.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# The same name as `_test_db.DATABASE_ENV`; test_test_database.py asserts it.
DATABASE_ENV = "MODELBOX_TEST_DATABASE_URL"


@pytest.fixture(autouse=True)
def _drop_test_databases() -> Iterator[None]:
    """Drop the databases a test created, once its own fixtures are done.

    Autouse fixtures are set up first and torn down last, so every engine the
    test's fixtures created has been disposed of by the time this runs. A no-op
    unless a PostgreSQL test server is configured.
    """
    yield
    if not os.environ.get(DATABASE_ENV):
        return
    from tests._test_db import drop_test_databases

    drop_test_databases()
