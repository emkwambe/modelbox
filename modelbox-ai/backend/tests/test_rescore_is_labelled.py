"""A re-scored conformance report never passes for a run (D10).

`rescore_conformance` exists so a metric fix can be applied to candidates
already paid for. The saving is real and so is the hazard: its output is
byte-for-byte the same shape as a report written by twelve live provider calls,
and lands at the same path. Nothing in the numbers distinguishes them.

The failure that would follow is not a wrong score — the scores are right, and
better than the ones they replace. It is a reader concluding the provider was
called on the day the file says, when it was not. `docs/marketing/` is where
public claims are sourced from, so a re-score that looked like a run would put a
fabricated call history behind a published figure.

Two properties keep them distinguishable, and both are easy to lose to a
plausible edit — stamping `run_started_at` with `now()` looks like freshness,
and dropping the `rescored` block looks like tidying:

* `run_started_at` stays the **original** call time. Re-scoring does not move it.
* `rescored` is present, and says why.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
_MARKETING = _REPO / "docs" / "marketing"
_CANDIDATES = _MARKETING / "conformance-report.candidates.json"
_REPORT = _MARKETING / "conformance-report.json"


@pytest.fixture(scope="module")
def rescored(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Re-score into a temp copy, never over the tracked report."""
    if not _CANDIDATES.exists():
        pytest.skip("no candidates file checked in")

    work = tmp_path_factory.mktemp("rescore")
    candidates = work / _CANDIDATES.name
    out = work / _REPORT.name
    shutil.copy(_CANDIDATES, candidates)
    shutil.copy(_REPORT, out)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.rescore_conformance",
            "--candidates",
            str(candidates),
            "--out",
            str(out),
            "--reason",
            "test",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        # The assertion below reports stderr; `check=True` would raise first and
        # hide it behind a bare exit code.
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_it_keeps_the_original_call_time(rescored: dict) -> None:
    """The answer to "when were these calls made" is unchanged by re-scoring."""
    original = json.loads(_CANDIDATES.read_text(encoding="utf-8"))["run_started_at"]
    assert rescored["run_started_at"] == original


def test_it_says_it_was_rescored(rescored: dict) -> None:
    """Present, and carrying a reason — an unexplained flag is barely better."""
    assert "rescored" in rescored, (
        "a re-scored report is shaped exactly like a fresh run; without this "
        "block nothing on the page says the provider was not called"
    )
    assert rescored["rescored"]["reason"]
    assert rescored["rescored"]["at"] != rescored["run_started_at"]


def test_no_provider_call_can_have_happened() -> None:
    """The precondition, asserted rather than assumed.

    Both fail-closed gates are unset under pytest, so the fixture above could
    not have reached a provider even if the script tried. That is what makes
    "re-scored offline" a fact about the run rather than a label on it.
    """
    source = (_BACKEND / "scripts" / "rescore_conformance.py").read_text(
        encoding="utf-8"
    )
    assert "structured_completion" not in source
    assert "llm_gateway" not in source


def test_the_shipped_reports_are_labelled() -> None:
    """The two files actually in `docs/marketing/` carry the block.

    The tests above prove the script behaves; this proves the artifacts on disk
    were produced by it, which is the thing a reader depends on.
    """
    for name in ("conformance-report.json", "conformance-report-sonnet-5.json"):
        path = _MARKETING / name
        if not path.exists():
            pytest.skip(f"{name} not checked in")
        report = json.loads(path.read_text(encoding="utf-8"))
        assert "rescored" in report, f"{name} does not say it was re-scored"
        assert report["providers"][0]["passed"] is False, (
            f"{name} reports a pass; D10 is open and no surface may claim "
            "conformance until a run actually meets the threshold"
        )
