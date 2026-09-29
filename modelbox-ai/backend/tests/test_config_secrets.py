"""Outside development, settings refuse every secret this repository ships.

Each case starts from a baseline that is asserted to start, then changes one
field. A refusal can therefore only come from that field, which is what lets a
case fail for the right reason rather than because the baseline was already
broken.

The negative controls at the end disable each control inside this process only
and assert the same check then fails. They run on every CI run, so the checks
are shown to discriminate continuously rather than once.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.config import (
    DEFAULT_ENCRYPTION_KEY,
    DEFAULT_JWT_SECRET,
    DEFAULT_POSTGRES_PASSWORD,
    Settings,
)

GOOD_JWT_SECRET = "j" * 48
GOOD_ENCRYPTION_KEY = "e" * 48
GOOD_PASSWORD = "p" * 32
SHORT_JWT_SECRET = "s" * 31


def _dsn(password: str) -> str:
    return f"postgresql+asyncpg://modelbox:{password}@postgres-db:5432/modelbox_metadata"


def _settings(cls: type[Settings] = Settings, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "production",
        "jwt_secret": GOOD_JWT_SECRET,
        "encryption_key": GOOD_ENCRYPTION_KEY,
        "database_url": _dsn(GOOD_PASSWORD),
    }
    values.update(overrides)
    return cls(_env_file=None, **values)  # type: ignore[call-arg]


REFUSALS = [
    pytest.param(
        {"jwt_secret": DEFAULT_JWT_SECRET},
        "JWT_SECRET is the shipped default",
        DEFAULT_JWT_SECRET,
        id="jwt_secret",
    ),
    pytest.param(
        {"encryption_key": DEFAULT_ENCRYPTION_KEY},
        "ENCRYPTION_KEY is the shipped default",
        DEFAULT_ENCRYPTION_KEY,
        id="encryption_key",
    ),
    pytest.param(
        {"database_url": _dsn(DEFAULT_POSTGRES_PASSWORD)},
        "POSTGRES_PASSWORD (the password in DATABASE_URL) is the shipped default",
        DEFAULT_POSTGRES_PASSWORD,
        id="postgres_password",
    ),
    pytest.param(
        {"jwt_secret": SHORT_JWT_SECRET},
        "JWT_SECRET is shorter than 32 bytes",
        SHORT_JWT_SECRET,
        id="short_jwt_secret",
    ),
]


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


def _check_refuses(
    cls: type[Settings],
    environment: str,
    override: dict[str, str],
    reason: str,
    value: str,
) -> None:
    """The check itself, shared by the tests and their negative controls."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(cls, environment=environment, **override)
    message = str(excinfo.value)
    assert reason in message
    _assert_no_secret_material(message, value)


def test_the_baseline_starts() -> None:
    """Precondition for every refusal below."""
    assert _settings().environment == "production"


@pytest.mark.parametrize("environment", ["production", "staging"])
@pytest.mark.parametrize(("override", "reason", "value"), REFUSALS)
def test_a_shipped_or_short_secret_refuses_to_start(
    environment: str, override: dict[str, str], reason: str, value: str
) -> None:
    _check_refuses(Settings, environment, override, reason, value)


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


def _check_unset_database_url_refused(cls: type[Settings]) -> None:
    """The check, shared by the test and its negative control."""
    with pytest.raises(ValidationError) as excinfo:
        cls(  # type: ignore[call-arg]
            _env_file=None,
            environment="production",
            jwt_secret=GOOD_JWT_SECRET,
            encryption_key=GOOD_ENCRYPTION_KEY,
        )
    assert "POSTGRES_PASSWORD (the password in DATABASE_URL) is the shipped default" in str(
        excinfo.value
    )


def test_an_unset_database_url_is_refused_as_the_shipped_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With DATABASE_URL unset, the shipped default DSN is refused by name.

    The other cases pass a DSN; this is the path an operator who forgot the
    variable takes, through the field's own default.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _check_unset_database_url_refused(Settings)


# --- Negative controls -------------------------------------------------------
#
# Pydantic compiles validators into the class when it is created, so patching
# the method afterwards disables nothing and a control built that way would
# pass while proving nothing. A subclass that redefines a validator under the
# same name replaces it, which switches off exactly the control the fix
# introduced, in this process only.


class _Unguarded(Settings):
    """`Settings` with `_refuse_shipped_secrets` replaced by a no-op."""

    @model_validator(mode="after")
    def _refuse_shipped_secrets(self) -> _Unguarded:
        return self


class _Echoing(Settings):
    """`Settings` with `hide_input_in_errors` switched back off.

    It inherits the real validator, so the refusal still fires and the echo is
    the only difference from `Settings`.
    """

    model_config = SettingsConfigDict(
        **{**Settings.model_config, "hide_input_in_errors": False}
    )


def test_negative_control_the_unguarded_class_is_unguarded() -> None:
    """Precondition: the override took. Otherwise the control below is vacuous."""
    settings = _settings(_Unguarded, jwt_secret=DEFAULT_JWT_SECRET)
    assert settings.jwt_secret == DEFAULT_JWT_SECRET


@pytest.mark.parametrize(("override", "reason", "value"), REFUSALS)
def test_negative_control_without_the_validator_the_check_fails(
    override: dict[str, str], reason: str, value: str
) -> None:
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        _check_refuses(_Unguarded, "production", override, reason, value)


def test_negative_control_an_unset_database_url_without_the_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        _check_unset_database_url_refused(_Unguarded)


@pytest.mark.parametrize(("override", "reason", "value"), REFUSALS)
def test_negative_control_with_input_echo_the_check_fails(
    override: dict[str, str], reason: str, value: str
) -> None:
    # The refusal still fires, so this fails at the leak check and nowhere else.
    with pytest.raises(AssertionError, match="input_value"):
        _check_refuses(_Echoing, "production", override, reason, value)
