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


_DIGEST_PINNED = re.compile(r"^ollama/ollama:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$")


def _check_ollama_is_pinned(spec: dict[str, Any]) -> None:
    image = str(spec["services"]["ollama-engine"]["image"])
    assert _DIGEST_PINNED.fullmatch(image), (
        f"ollama-engine is {image!r}; it must be ollama/ollama:<version>@sha256:<digest>"
    )


def test_the_ollama_image_is_pinned_by_digest() -> None:
    _check_ollama_is_pinned(APPLIANCE)


# --- Negative controls -------------------------------------------------------


@pytest.mark.parametrize(
    "image",
    [
        "ollama/ollama:latest",
        "ollama/ollama:0.34.4",
        "ollama/ollama@sha256:" + "0" * 64,
    ],
    ids=["latest", "tag-only", "digest-without-version"],
)
def test_negative_control_an_unpinned_ollama_fails_the_check(image: str) -> None:
    spec = copy.deepcopy(APPLIANCE)
    spec["services"]["ollama-engine"]["image"] = image
    with pytest.raises(AssertionError, match="ollama-engine is"):
        _check_ollama_is_pinned(spec)


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
