"""Config parsing tests — CORS origins accept both formats without crashing."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_cors_origins_comma_separated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:13000"
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://localhost:13000",
    ]


def test_cors_origins_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS", '["http://localhost:3000","http://localhost:13000"]'
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://localhost:13000",
    ]


def test_cors_origins_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == ["http://localhost:3000"]
