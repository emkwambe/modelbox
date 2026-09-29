"""No code reads a gateway URL, and the appliance ships no routing proxy.

The gateway is in-process (`app.services.llm_gateway`) and is the only path to
a provider. A separate LiteLLM proxy ran beside it with the provider keys and
no caller; a setting that points at it is an invitation to add one. The scan
covers every module under `app/`, in both the attribute form and the
environment-variable form.

The negative control hands the same scanner a synthetic module that reads the
setting and asserts it is found.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
APP = BACKEND / "app"
COMPOSE = ROOT / "docker" / "docker-compose.appliance.yml"

_READER = re.compile(r"llm_gateway_url", re.IGNORECASE)


def _readers(sources: dict[str, str]) -> list[str]:
    """`path:line` for every line that names the setting, in any case."""
    found: list[str] = []
    for path, text in sources.items():
        for number, line in enumerate(text.splitlines(), start=1):
            if _READER.search(line):
                found.append(f"{path}:{number}")
    return found


def _app_sources() -> dict[str, str]:
    return {
        str(path.relative_to(BACKEND)): path.read_text(encoding="utf-8")
        for path in sorted(APP.rglob("*.py"))
    }


def _check_no_reader(sources: dict[str, str]) -> None:
    """The check, shared by the test and its negative control."""
    assert sources, "fixture precondition: nothing to scan"
    readers = _readers(sources)
    assert not readers, f"llm_gateway_url is still read at {readers}"


def test_no_module_reads_a_gateway_url() -> None:
    _check_no_reader(_app_sources())


def test_the_scan_covers_the_gateway_module() -> None:
    """Precondition: a scan that missed the gateway itself would prove little."""
    assert "app/services/llm_gateway.py" in {
        key.replace("\\", "/") for key in _app_sources()
    }


def test_settings_has_no_gateway_url() -> None:
    assert "llm_gateway_url" not in Settings.model_fields


def test_the_appliance_ships_no_proxy() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    services = yaml.safe_load(text)["services"]
    assert not [name for name in services if "litellm" in name]
    assert "LLM_GATEWAY_URL" not in text
    assert not (ROOT / "config" / "litellm_config.yaml").exists()
    assert "LLM_GATEWAY_URL" not in (ROOT / ".env.example").read_text(encoding="utf-8")


# --- Negative control --------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "url = settings.llm_gateway_url",
        'url = os.environ["LLM_GATEWAY_URL"]',
    ],
    ids=["attribute", "environment"],
)
def test_negative_control_a_reader_fails_the_check(line: str) -> None:
    sources = {**_app_sources(), "app/services/synthetic_reader.py": line + "\n"}
    with pytest.raises(AssertionError, match="synthetic_reader.py:1"):
        _check_no_reader(sources)
