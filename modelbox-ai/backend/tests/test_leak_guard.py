"""The leak guard (modelbox-ai/scripts/check_leak_guard.py) and what it catches.

The CI job runs the script over `git ls-files`. These tests pin each pattern
with a path it must catch and a nearby path it must not, and check the current
tree is clean.

Negative control (Amendment 2): with the pattern list emptied in-process, the
same synthetic private paths pass.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_leak_guard.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_leak_guard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIVATE = [
    "modelbox-ai/docs/SPRINT_8_PROMPT.md",
    "modelbox-ai/docs/research/interviews.md",
    "modelbox-ai/docs/marketing/Launch_PLAN.md",
    "modelbox-ai/docs/Security_Assessment_2026.md",
    "Market_Study_US.md",
    "modelbox-ai/docs/ModelBox_AI_Sprint_Plan.md",
]

PUBLIC = [
    "modelbox-ai/docs/sprint-6-progress.md",
    "modelbox-ai/docs/marketing/PROOF_LOG.md",
    "modelbox-ai/docs/SECURITY_FAQ.md",
    "modelbox-ai/STATE.md",
]


def _check_all_private_caught(module: ModuleType) -> None:
    """The check, shared by the test and its negative control."""
    caught = {path for path, _ in module.violations(PRIVATE)}
    missed = sorted(set(PRIVATE) - caught)
    assert not missed, f"the leak guard let private paths through: {missed}"


def test_each_pattern_catches_its_private_path() -> None:
    _check_all_private_caught(_load())


def test_public_paths_are_not_caught() -> None:
    assert _load().violations(PUBLIC) == []


def test_the_current_tree_is_clean() -> None:
    module = _load()
    paths = module.tracked_paths()
    assert len(paths) > 100, "fixture sanity: git ls-files saw almost nothing"
    assert module.violations(paths) == []


def test_negative_control_without_patterns_private_paths_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    monkeypatch.setattr(module, "PATTERNS", ())
    with pytest.raises(AssertionError, match="let private paths through"):
        _check_all_private_caught(module)
