"""Under MODELBOX_MIGRATION_STRICT=1, a migration gate that cannot run fails.

The strict flag exists so a CI run cannot report green having migrated
nothing. It covered the Docker check but not the baseline worktree: when the
v1.6.0 checkout could not be created, the 0013 gate skipped even under strict.
Every stop now goes through `_unavailable`, which fails under strict.

These run without Docker. The worktree test asks git for a tag that does not
exist, which is the real failure path, not a simulation of it.

Negative control: replacing `_unavailable` with the old always-skip
behaviour makes the strict worktree check fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import test_migration_0013_populated as gate

MISSING_TAG = "v0.0.0-does-not-exist"


def test_strict_turns_an_unavailable_gate_into_a_failure() -> None:
    with pytest.raises(pytest.fail.Exception, match="MODELBOX_MIGRATION_STRICT=1"):
        gate._unavailable("docker is unavailable", strict=True)


def test_without_strict_an_unavailable_gate_skips() -> None:
    with pytest.raises(pytest.skip.Exception):
        gate._unavailable("docker is unavailable", strict=False)


def _check_strict_worktree_failure_fails(tmp_path: Path) -> None:
    """The check, shared by the test and its negative control."""
    with pytest.raises(pytest.fail.Exception, match=MISSING_TAG):
        gate._add_baseline_worktree(tmp_path / "baseline", MISSING_TAG)


def test_a_missing_baseline_worktree_fails_under_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "_STRICT", True)
    _check_strict_worktree_failure_fails(tmp_path)


def test_the_docker_check_goes_through_the_same_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "DOCKER", None)
    monkeypatch.setattr(gate, "_STRICT", True)
    with pytest.raises(pytest.fail.Exception, match="docker is unavailable"):
        gate._need_docker()


# --- Negative control -------------------------------------------------------


def test_negative_control_an_always_skip_path_fails_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_skip(reason: str, strict: bool | None = None) -> None:
        pytest.skip(reason)

    monkeypatch.setattr(gate, "_STRICT", True)
    monkeypatch.setattr(gate, "_unavailable", always_skip)
    with pytest.raises(pytest.skip.Exception):
        _check_strict_worktree_failure_fails(tmp_path)
