"""The release gate's decision (modelbox-ai/scripts/check_release_gate.py).

`release.yml` publishes only when the tagged commit is on main and the latest
CI run for that exact commit concluded success. The decision is a pure
function of those two facts, tested here case by case; the discrimination
against real commits is a dry run of the script, recorded in the verification
file.

Negative controls (Amendment 2): with each condition switched off in-process,
a commit that fails it is let through.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_release_gate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_release_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(run_id: int, created: str, status: str = "completed", conclusion: str | None = "success") -> dict:
    return {"id": run_id, "created_at": created, "status": status, "conclusion": conclusion}


GREEN = [_run(1, "2026-09-28T10:00:00Z")]
RED = [_run(2, "2026-09-28T10:00:00Z", conclusion="failure")]


def _check_refused(module: ModuleType, on_main: bool, runs: list[dict], reason: str) -> None:
    """The check, shared by the tests and their negative controls."""
    reasons = module.decide(on_main, runs)
    assert any(reason in r for r in reasons), f"the gate allowed it: {reasons}"


def test_a_green_commit_on_main_may_release() -> None:
    assert _load().decide(True, GREEN) == []


@pytest.mark.parametrize(
    ("on_main", "runs", "reason"),
    [
        pytest.param(False, GREEN, "not reachable from origin/main", id="off-main"),
        pytest.param(True, RED, "concluded failure", id="red"),
        pytest.param(True, [], "no ci.yml run", id="no-run"),
        pytest.param(True, [_run(3, "2026-09-28T10:00:00Z", "in_progress", None)], "has not completed", id="running"),
        pytest.param(
            True,
            [_run(4, "2026-09-28T10:00:00Z"), _run(5, "2026-09-28T11:00:00Z", conclusion="failure")],
            "concluded failure",
            id="latest-red",
        ),
    ],
)
def test_the_gate_refuses(on_main: bool, runs: list[dict], reason: str) -> None:
    _check_refused(_load(), on_main, runs, reason)


def test_both_reasons_are_named_at_once() -> None:
    reasons = _load().decide(False, RED)
    assert len(reasons) == 2


def test_negative_control_without_the_ci_condition_a_red_commit_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    original = module.decide
    monkeypatch.setattr(module, "decide", lambda on_main, runs: original(on_main, GREEN))
    with pytest.raises(AssertionError, match="the gate allowed it"):
        _check_refused(module, True, RED, "concluded failure")


def test_negative_control_without_the_main_condition_an_off_main_commit_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    original = module.decide
    monkeypatch.setattr(module, "decide", lambda on_main, runs: original(True, runs))
    with pytest.raises(AssertionError, match="the gate allowed it"):
        _check_refused(module, False, GREEN, "not reachable from origin/main")
