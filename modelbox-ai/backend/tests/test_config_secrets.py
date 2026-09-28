"""Outside development, settings refuse every secret this repository ships.

Each case starts from a baseline that is asserted to start, then changes one
field. A refusal can therefore only come from that field, which is what lets a
case fail for the right reason rather than because the baseline was already
broken.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_ENCRYPTION_KEY,
    DEFAULT_JWT_SECRET,
    DEFAULT_POSTGRES_PASSWORD,
    Settings,
)

GOOD_JWT_SECRET = "j" * 48
GOOD_ENCRYPTION_KEY = "e" * 48
GOOD_PASSWORD = "p" * 32


def _dsn(password: str) -> str:
    return f"postgresql+asyncpg://modelbox:{password}@postgres-db:5432/modelbox_metadata"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "production",
        "jwt_secret": GOOD_JWT_SECRET,
        "encryption_key": GOOD_ENCRYPTION_KEY,
        "database_url": _dsn(GOOD_PASSWORD),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_the_baseline_starts() -> None:
    """Precondition for every refusal below."""
    assert _settings().environment == "production"


@pytest.mark.parametrize("environment", ["production", "staging"])
@pytest.mark.parametrize(
    ("override", "variable", "value"),
    [
        ({"jwt_secret": DEFAULT_JWT_SECRET}, "JWT_SECRET", DEFAULT_JWT_SECRET),
        (
            {"encryption_key": DEFAULT_ENCRYPTION_KEY},
            "ENCRYPTION_KEY",
            DEFAULT_ENCRYPTION_KEY,
        ),
        (
            {"database_url": _dsn(DEFAULT_POSTGRES_PASSWORD)},
            "POSTGRES_PASSWORD",
            DEFAULT_POSTGRES_PASSWORD,
        ),
    ],
    ids=["jwt_secret", "encryption_key", "postgres_password"],
)
def test_a_shipped_default_refuses_to_start(
    environment: str, override: dict[str, str], variable: str, value: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _settings(environment=environment, **override)
    message = str(excinfo.value)
    assert variable in message
    _assert_no_secret_material(message, value)


def _assert_no_secret_material(message: str, *refused: str) -> None:
    """No configured value, nor any 8-character piece of one, is in the error.

    Whole-string absence is not enough: pydantic's default error text echoes
    the input truncated to a head and a tail, so a check for the full value
    passes while the last characters of whichever secret sits at the end are
    printed. That is how this test first passed against a leaking error.
    """
    assert "input_value" not in message
    stripped = message.replace("JWT_SECRET", "").replace("POSTGRES_PASSWORD", "")
    for secret in (GOOD_JWT_SECRET, GOOD_ENCRYPTION_KEY, GOOD_PASSWORD, *refused):
        for start in range(max(1, len(secret) - 7)):
            assert secret[start : start + 8] not in stripped


def test_a_short_jwt_secret_refuses_to_start() -> None:
    short = "s" * 31
    with pytest.raises(ValidationError) as excinfo:
        _settings(jwt_secret=short)
    message = str(excinfo.value)
    assert "JWT_SECRET is shorter than 32 bytes" in message
    _assert_no_secret_material(message, short)


def test_the_length_is_counted_in_bytes() -> None:
    # 16 two-byte characters: 16 characters, 32 bytes. Accepted.
    assert _settings(jwt_secret="é" * 16).jwt_secret == "é" * 16


def test_every_problem_is_named_at_once() -> None:
    """An operator fixing one variable per restart would take three restarts."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(
            jwt_secret=DEFAULT_JWT_SECRET,
            encryption_key=DEFAULT_ENCRYPTION_KEY,
            database_url=_dsn(DEFAULT_POSTGRES_PASSWORD),
        )
    message = str(excinfo.value)
    for variable in ("JWT_SECRET", "ENCRYPTION_KEY", "POSTGRES_PASSWORD"):
        assert variable in message


def test_development_keeps_the_defaults() -> None:
    settings = _settings(
        environment="development",
        jwt_secret=DEFAULT_JWT_SECRET,
        encryption_key=DEFAULT_ENCRYPTION_KEY,
        database_url=_dsn(DEFAULT_POSTGRES_PASSWORD),
    )
    assert settings.jwt_secret == DEFAULT_JWT_SECRET
