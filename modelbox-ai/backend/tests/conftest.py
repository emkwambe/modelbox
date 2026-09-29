"""Suite-wide fixtures. Kept to what every test needs; see ``_test_db.py``."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests._test_db import drop_test_databases


@pytest.fixture(autouse=True)
def _drop_test_databases() -> Iterator[None]:
    """Drop the databases a test created, once its own fixtures are done.

    Autouse fixtures are set up first and torn down last, so every engine the
    test's fixtures created has been disposed of by the time this runs. A no-op
    on SQLite.
    """
    yield
    drop_test_databases()
