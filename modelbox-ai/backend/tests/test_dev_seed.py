"""The dev account is seeded only in development, and only when asked for.

The account's password is published in this repository. The check runs the
real seeding function and asserts it never opens a database session, which is
the only way the account could come to exist. Its negative control switches
off exactly the gate this fix introduced, `dev_seed_allowed`, and asserts the
check then fails.
"""

from __future__ import annotations

from typing import Any

import pytest

from app import main
from app.core import database
from app.core.config import Settings

SECRETS = {
    "jwt_secret": "j" * 48,
    "encryption_key": "e" * 48,
    "database_url": (
        "postgresql+asyncpg://modelbox:" + "p" * 32 + "@postgres-db:5432/modelbox_metadata"
    ),
}


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**SECRETS, **overrides})  # type: ignore[call-arg]


class _SessionRecorder:
    """Stands in for `get_sessionmaker`; records the call, then fails.

    Failing is deliberate: the seed swallows its own errors, so a real session
    is not needed to learn whether one was asked for.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        raise RuntimeError("no database in this test")


@pytest.fixture
def sessions(monkeypatch: pytest.MonkeyPatch) -> _SessionRecorder:
    recorder = _SessionRecorder()
    monkeypatch.setattr(database, "get_sessionmaker", recorder)
    return recorder


async def _check_seed_refused(config: Settings, sessions: _SessionRecorder) -> None:
    """The check, shared by the tests and their negative control."""
    await main._seed_dev_user(config)
    assert sessions.calls == 0, "the seed opened a database session"


@pytest.mark.parametrize("environment", ["production", "staging"])
async def test_the_seed_is_refused_outside_development_even_when_asked(
    environment: str, sessions: _SessionRecorder
) -> None:
    await _check_seed_refused(
        _settings(environment=environment, seed_dev_user=True), sessions
    )


async def test_the_seed_is_refused_in_development_unless_asked(
    sessions: _SessionRecorder,
) -> None:
    await _check_seed_refused(
        _settings(environment="development", seed_dev_user=False), sessions
    )


async def test_the_seed_runs_in_development_when_asked(
    sessions: _SessionRecorder,
) -> None:
    """Precondition: the recorder sees a real seeding attempt.

    Without this, the refusals above would pass against a seed that never
    reaches the database at all.
    """
    await main._seed_dev_user(_settings(environment="development", seed_dev_user=True))
    assert sessions.calls == 1


def test_the_flag_reads_its_documented_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELBOX_SEED_DEV_USER", "true")
    assert _settings().seed_dev_user is True
    monkeypatch.delenv("MODELBOX_SEED_DEV_USER")
    assert _settings().seed_dev_user is False


@pytest.mark.parametrize(
    ("environment", "flag", "allowed"),
    [
        ("development", True, True),
        ("development", False, False),
        ("staging", True, False),
        ("production", True, False),
        ("production", False, False),
    ],
)
def test_the_gate_requires_both_conditions(
    environment: str, flag: bool, allowed: bool
) -> None:
    config = _settings(environment=environment, seed_dev_user=flag)
    assert main.dev_seed_allowed(config) is allowed


# --- Negative control --------------------------------------------------------


async def test_negative_control_without_the_gate_the_check_fails(
    monkeypatch: pytest.MonkeyPatch, sessions: _SessionRecorder
) -> None:
    monkeypatch.setattr(main, "dev_seed_allowed", lambda config: True)
    with pytest.raises(AssertionError, match="opened a database session"):
        await _check_seed_refused(
            _settings(environment="production", seed_dev_user=True), sessions
        )
