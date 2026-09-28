"""The appliance publishes one port, the UI's, and nothing bakes in an API URL.

The backend, Postgres, Redis and Ollama publish nothing to the host; the UI
forwards `/api/*` over the compose network. The debug override may publish the
backend, and only on loopback. `NEXT_PUBLIC_API_URL` is gone from every place
that could set or read it, and the frontend image installs with `npm ci`.
The Ollama image is pinned to a version and a digest.

Each check is a function shared with a negative control that hands it a
synthetic copy with the control undone, and asserts it fails.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCKER = ROOT / "docker"
APPLIANCE = yaml.safe_load((DOCKER / "docker-compose.appliance.yml").read_text(encoding="utf-8"))
DEBUG = yaml.safe_load((DOCKER / "docker-compose.debug.yml").read_text(encoding="utf-8"))
FRONTEND_DOCKERFILE = DOCKER / "Dockerfile.frontend"

PUBLISHED_ALONE = "modelbox-ui"


def _ports(spec: dict[str, Any]) -> dict[str, list[str]]:
    return {
        name: [str(port) for port in service.get("ports") or []]
        for name, service in spec["services"].items()
    }


def _check_only_the_ui_publishes(spec: dict[str, Any]) -> None:
    ports = _ports(spec)
    assert ports.get(PUBLISHED_ALONE), "fixture precondition: the UI publishes a port"
    others = {name: mapped for name, mapped in ports.items() if mapped and name != PUBLISHED_ALONE}
    assert not others, f"services other than the UI publish ports: {others}"


def _check_debug_is_loopback_only(spec: dict[str, Any]) -> None:
    ports = _ports(spec)
    assert set(ports) == {"modelbox-backend"}, f"the override touches {sorted(ports)}"
    mapped = ports["modelbox-backend"]
    assert mapped, "fixture precondition: the override publishes the backend"
    wide = [port for port in mapped if not port.startswith("127.0.0.1:")]
    assert not wide, f"the debug override publishes beyond loopback: {wide}"


def _check_installs_from_the_lock(dockerfile: str) -> None:
    runs = [line.strip() for line in dockerfile.splitlines() if line.strip().startswith("RUN ")]
    assert any(re.search(r"\bnpm ci\b", run) for run in runs), "no RUN npm ci"
    installs = [run for run in runs if re.search(r"\bnpm (install|i)\b", run)]
    assert not installs, f"the image repairs the lock with {installs}"


def test_only_the_ui_publishes_a_port() -> None:
    _check_only_the_ui_publishes(APPLIANCE)


def test_the_ui_port_is_the_configurable_one() -> None:
    assert _ports(APPLIANCE)[PUBLISHED_ALONE] == ["${UI_PORT:-3000}:3000"]


def test_the_debug_override_publishes_the_backend_on_loopback_only() -> None:
    _check_debug_is_loopback_only(DEBUG)


def test_the_frontend_image_installs_from_the_lock() -> None:
    _check_installs_from_the_lock(FRONTEND_DOCKERFILE.read_text(encoding="utf-8"))


def test_no_build_time_api_url_remains() -> None:
    places = [
        DOCKER / "docker-compose.appliance.yml",
        FRONTEND_DOCKERFILE,
        ROOT / ".env.example",
        ROOT / "frontend" / "next.config.js",
        *sorted((ROOT / "frontend" / "src").rglob("*.ts")),
        *sorted((ROOT / "frontend" / "src").rglob("*.tsx")),
    ]
    found = [
        str(path.relative_to(ROOT))
        for path in places
        if "NEXT_PUBLIC_API_URL" in path.read_text(encoding="utf-8")
    ]
    assert not found, f"NEXT_PUBLIC_API_URL is still set or read in {found}"


# `<repo>:<numeric version>[-suffix]@sha256:<64 hex>`. A version with no digest
# can be re-pushed; a digest with no version cannot be read.
_DIGEST_PINNED = re.compile(r"^[a-z0-9./_-]+:\d+\.\d+(\.\d+)?(-[a-z0-9]+)?@sha256:[0-9a-f]{64}$")

# Services that pull someone else's image rather than building ours.
PULLED = {"ollama-engine", "postgres-db", "redis-cache"}


def _pulled(spec: dict[str, Any]) -> dict[str, str]:
    return {
        name: str(service["image"])
        for name, service in spec["services"].items()
        if "image" in service and "build" not in service
    }


def _check_pulled_images_are_pinned(spec: dict[str, Any]) -> None:
    unpinned = {
        name: image for name, image in _pulled(spec).items() if not _DIGEST_PINNED.fullmatch(image)
    }
    assert not unpinned, (
        f"pulled images must be <repo>:<version>@sha256:<digest>; unpinned: {unpinned}"
    )


def test_the_pulled_services_are_the_expected_three() -> None:
    """Precondition: a new pulled service would otherwise be covered silently."""
    assert set(_pulled(APPLIANCE)) == PULLED


def test_every_pulled_image_is_pinned_by_version_and_digest() -> None:
    _check_pulled_images_are_pinned(APPLIANCE)


def test_the_migration_gates_and_restore_script_use_the_shipped_postgres() -> None:
    """They exist to exercise the Postgres the appliance ships, so no restated tag."""
    from scripts import verify_restore
    from tests._docker_postgres import POSTGRES_IMAGE

    shipped = APPLIANCE["services"]["postgres-db"]["image"]
    assert POSTGRES_IMAGE == shipped
    assert verify_restore.IMAGE == shipped


# --- Negative controls -------------------------------------------------------


@pytest.mark.parametrize(
    ("service", "image"),
    [
        ("ollama-engine", "ollama/ollama:latest"),
        ("ollama-engine", "ollama/ollama:0.34.4"),
        ("ollama-engine", "ollama/ollama@sha256:" + "0" * 64),
        ("postgres-db", "postgres:16-alpine"),
        ("postgres-db", "postgres:16.15-alpine"),
        ("postgres-db", "postgres@sha256:" + "0" * 64),
        ("redis-cache", "redis:7-alpine"),
        ("redis-cache", "redis:7.4.11-alpine"),
        ("redis-cache", "redis@sha256:" + "0" * 64),
    ],
    ids=[
        "ollama-latest", "ollama-tag-only", "ollama-digest-only",
        "postgres-floating", "postgres-tag-only", "postgres-digest-only",
        "redis-floating", "redis-tag-only", "redis-digest-only",
    ],
)
def test_negative_control_an_unpinned_image_fails_the_check(service: str, image: str) -> None:
    spec = copy.deepcopy(APPLIANCE)
    spec["services"][service]["image"] = image
    with pytest.raises(AssertionError, match=service):
        _check_pulled_images_are_pinned(spec)


@pytest.mark.parametrize(
    ("service", "mapping"),
    [
        ("modelbox-backend", "8000:8000"),
        ("postgres-db", "5432:5432"),
        ("redis-cache", "6379:6379"),
        ("ollama-engine", "11434:11434"),
    ],
)
def test_negative_control_a_published_service_fails_the_check(
    service: str, mapping: str
) -> None:
    spec = copy.deepcopy(APPLIANCE)
    spec["services"][service]["ports"] = [mapping]
    with pytest.raises(AssertionError, match=service):
        _check_only_the_ui_publishes(spec)


def test_negative_control_a_wide_debug_mapping_fails_the_check() -> None:
    spec = copy.deepcopy(DEBUG)
    spec["services"]["modelbox-backend"]["ports"] = ["8000:8000"]
    with pytest.raises(AssertionError, match="beyond loopback"):
        _check_debug_is_loopback_only(spec)


def test_negative_control_npm_install_fails_the_check() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    mutated = text.replace("RUN npm ci", "RUN npm install", 1)
    assert mutated != text, "fixture precondition: RUN npm ci is present"
    with pytest.raises(AssertionError):
        _check_installs_from_the_lock(mutated)
