"""Configuration A: only `.env.example` copied to `.env`. Compose must refuse.

The four secrets are empty in `.env.example`, and the appliance compose file
reads each with `${VAR:?...}`, so `docker compose up` stops before any
container exists and names the variable. Runs before init-env in CI; it never
overwrites an existing `.env`.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from conftest import BASE_COMPOSE, ENV_FILE, ROOT, check

pytestmark = pytest.mark.config_a

SECRETS = ("JWT_SECRET", "ENCRYPTION_KEY", "POSTGRES_PASSWORD", "MODELBOX_APP_DB_PASSWORD")


def _project_containers() -> list[str]:
    listed = subprocess.run(
        ["docker", "ps", "-a", "-q", "--filter", "label=com.docker.compose.project=modelbox-ai"],
        capture_output=True, text=True, check=True,  # docker itself failing is a harness error
    )
    return listed.stdout.split()


def test_a_compose_refuses_with_only_the_example_env() -> None:
    assert not ENV_FILE.exists(), "setup: config A runs before init-env and never overwrites .env"
    assert _project_containers() == [], "fixture sanity: no appliance containers exist yet"
    shutil.copyfile(ROOT / ".env.example", ENV_FILE)
    try:
        result = subprocess.run(
            ["docker", "compose", "--env-file", str(ENV_FILE), "-f", str(BASE_COMPOSE),
             "up", "-d", "--no-build"],
            cwd=ROOT, capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if k not in SECRETS},
            check=False,  # the refusal is the result under test
            timeout=300,
        )
        named = [name for name in SECRETS if f"{name} must be set in .env" in result.stderr]
        check(result.returncode != 0, "docker compose up started with only .env.example")
        check(bool(named), f"the refusal names no missing secret: {result.stderr[-400:]!r}")
        check(_project_containers() == [], "containers exist after the refusal")
    finally:
        ENV_FILE.unlink()
