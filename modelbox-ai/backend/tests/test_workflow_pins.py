"""The release path's workflows: pinned actions, and no push without the gate.

Two structural rules over `.github/workflows/*.yml`, read as YAML rather than
matched as text:

* every third-party action is pinned to a full commit SHA, never a movable
  tag. GitHub's own `actions/*` are exempt, as they are across this repository;
* images are built in one place, `images.yml`, whose push is its `push` input,
  and the only caller that passes `push: true` is a job that needs the release
  gate, which runs `check_release_gate.py`. `release-dry-run.yml` exercises the
  same build with `push: false` whenever the release path changes.

Negative controls (Amendment 2) feed each check a synthetic workflow that
breaks its rule, and show the check then fails.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"
IMAGES = "./.github/workflows/images.yml"
FULL_SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _load_all() -> dict[str, dict[str, Any]]:
    files = sorted(WORKFLOWS.glob("*.yml"))
    # A missing directory would make every check below vacuous.
    assert files, f"no workflows found under {WORKFLOWS}"
    return {path.name: yaml.safe_load(path.read_text(encoding="utf-8")) for path in files}


def _uses(workflow: dict[str, Any]) -> list[str]:
    """Every `uses:` in a workflow: job-level (reusable) and step-level."""
    found: list[str] = []
    for job in (workflow.get("jobs") or {}).values():
        if "uses" in job:
            found.append(job["uses"])
        found.extend(step["uses"] for step in job.get("steps", []) if "uses" in step)
    return found


def _unpinned(workflows: dict[str, dict[str, Any]]) -> list[str]:
    """Third-party actions referenced by anything other than a full SHA."""
    return [
        f"{name}: {ref}"
        for name, workflow in workflows.items()
        for ref in _uses(workflow)
        if not ref.startswith(("./", "actions/")) and not FULL_SHA.match(ref)
    ]


def _ungated_pushes(workflows: dict[str, dict[str, Any]]) -> list[str]:
    """Calls of images.yml that push without needing a job that runs the gate."""
    problems: list[str] = []
    for name, workflow in workflows.items():
        jobs = workflow.get("jobs") or {}
        for job_id, job in jobs.items():
            if job.get("uses") != IMAGES or (job.get("with") or {}).get("push") is not True:
                continue
            needs = job.get("needs") or []
            needs = [needs] if isinstance(needs, str) else needs
            gated = any(
                "check_release_gate.py" in step.get("run", "")
                for need in needs
                for step in jobs.get(need, {}).get("steps", [])
            )
            if not gated:
                problems.append(f"{name}: job {job_id!r} pushes without the release gate")
    return problems


def test_every_third_party_action_is_pinned_to_a_commit() -> None:
    assert _unpinned(_load_all()) == []


def test_the_docker_actions_are_the_node_24_majors() -> None:
    """The versions chosen for Node 24, by the comment beside each pin."""
    text = (WORKFLOWS / "images.yml").read_text(encoding="utf-8")
    for action, major in (
        ("docker/setup-buildx-action", "v4"),
        ("docker/login-action", "v4"),
        ("docker/metadata-action", "v6"),
        ("docker/build-push-action", "v7"),
    ):
        assert re.search(rf"uses: {action}@[0-9a-f]{{40}} # {major}\.", text), action


def test_only_images_yml_builds_images_and_its_push_is_its_input() -> None:
    workflows = _load_all()
    builders = [
        name
        for name, workflow in workflows.items()
        if any(ref.startswith("docker/build-push-action@") for ref in _uses(workflow))
    ]
    assert builders == ["images.yml"]
    steps = workflows["images.yml"]["jobs"]["build"]["steps"]
    build = next(s for s in steps if s.get("uses", "").startswith("docker/build-push-action@"))
    assert build["with"]["push"] == "${{ inputs.push }}"


def test_only_a_gated_call_pushes() -> None:
    workflows = _load_all()
    assert _ungated_pushes(workflows) == []
    # The rule has something to hold: release.yml does push, and the dry run
    # calls the same build without pushing.
    assert workflows["release.yml"]["jobs"]["publish"]["with"]["push"] is True
    assert workflows["release-dry-run.yml"]["jobs"]["build-only"]["with"]["push"] is False


def test_negative_control_a_tag_pinned_action_fails_the_pin_check() -> None:
    workflow = {"jobs": {"j": {"steps": [{"uses": "docker/login-action@v4"}]}}}
    with pytest.raises(AssertionError):
        assert _unpinned({"synthetic.yml": workflow}) == []


def test_negative_control_a_push_without_the_gate_fails_the_gate_check() -> None:
    workflow = {
        "jobs": {
            "gate": {"steps": [{"run": "echo no gate here"}]},
            "publish": {"needs": "gate", "uses": IMAGES, "with": {"push": True}},
        }
    }
    with pytest.raises(AssertionError):
        assert _ungated_pushes({"synthetic.yml": workflow}) == []
