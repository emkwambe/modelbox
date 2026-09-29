"""The backend image stops litellm fetching its cost map at import.

`import litellm` fetches a model cost map from GitHub unless
`LITELLM_LOCAL_MODEL_COST_MAP` is true: an outbound request on every boot that
no gateway records. The fix is an `ENV` line in `Dockerfile.backend`.

The check takes the value from that `ENV` line, sets it in this process, and
calls litellm's own `get_model_cost_map` with the remote fetch replaced by a
recorder. So it tests the installed litellm's reading of the variable, not
only its spelling in the Dockerfile, and a litellm upgrade that renamed it
would fail here. The negative control removes the variable and asserts the
check then fails.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from litellm.litellm_core_utils import get_model_cost_map as cost_map

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "Dockerfile.backend"
COMPOSE = ROOT / "docker" / "docker-compose.appliance.yml"
NAME = "LITELLM_LOCAL_MODEL_COST_MAP"


def _dockerfile_env(text: str) -> dict[str, str]:
    """`NAME=value` pairs from every ENV instruction, continuations joined."""
    joined = re.sub(r"\\\n", " ", text)
    env: dict[str, str] = {}
    for line in joined.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("ENV "):
            for pair in stripped[4:].split():
                name, sep, value = pair.partition("=")
                if sep:
                    env[name] = value
    return env


class _FetchRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise RuntimeError("no network in this test")


@pytest.fixture
def fetches(monkeypatch: pytest.MonkeyPatch) -> _FetchRecorder:
    recorder = _FetchRecorder()
    monkeypatch.setattr(
        cost_map.GetModelCostMap, "fetch_remote_model_cost_map", recorder
    )
    return recorder


def _check_no_fetch(fetches: _FetchRecorder) -> None:
    """The check, shared by the test and its negative control."""
    result = cost_map.get_model_cost_map(url="https://example.invalid/cost.json")
    assert result, "litellm returned no cost map at all"
    assert fetches.calls == 0, "litellm tried to fetch the cost map remotely"


def test_the_image_sets_the_variable() -> None:
    assert _dockerfile_env(DOCKERFILE.read_text(encoding="utf-8")).get(NAME) == "True"


def test_the_variable_is_not_left_to_compose() -> None:
    """The image carries it, so no compose file has to remember to."""
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for name, spec in services.items():
        entries = [str(entry) for entry in spec.get("environment") or []]
        assert not [entry for entry in entries if entry.startswith(NAME)], name


def test_with_the_image_value_litellm_does_not_fetch(
    monkeypatch: pytest.MonkeyPatch, fetches: _FetchRecorder
) -> None:
    value = _dockerfile_env(DOCKERFILE.read_text(encoding="utf-8"))[NAME]
    monkeypatch.setenv(NAME, value)
    _check_no_fetch(fetches)


# --- Negative control --------------------------------------------------------


def test_negative_control_without_the_variable_the_check_fails(
    monkeypatch: pytest.MonkeyPatch, fetches: _FetchRecorder
) -> None:
    monkeypatch.delenv(NAME, raising=False)
    with pytest.raises(AssertionError, match="tried to fetch"):
        _check_no_fetch(fetches)
    assert fetches.calls == 1
