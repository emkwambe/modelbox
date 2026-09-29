#!/usr/bin/env python3
"""Refuse a release unless its commit is on main and CI passed on it.

`release.yml` runs this before building anything. Both conditions must hold:

* the tagged commit is reachable from ``origin/main``
  (``git merge-base --is-ancestor``), so a tag on an unmerged branch cannot
  publish;
* the most recent run of the CI workflow (``ci.yml``) for that exact commit
  completed with conclusion ``success``. No run, a run still going, or a
  latest run that failed are all refusals. A pull request's runs are for its
  merge commit, not this one, so only runs of this commit count.

Usage::

    python modelbox-ai/scripts/check_release_gate.py --sha <commit> --repo owner/name

It exits 1 with every reason it found. `gh` must be authenticated (`GH_TOKEN`
in Actions).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

CI_WORKFLOW = "ci.yml"


def decide(on_main: bool, runs: list[dict[str, Any]]) -> list[str]:
    """Every reason to refuse; an empty list means the release may proceed."""
    reasons: list[str] = []
    if not on_main:
        reasons.append("the commit is not reachable from origin/main")
    if not runs:
        reasons.append(f"no {CI_WORKFLOW} run exists for the commit")
    else:
        latest = max(runs, key=lambda run: run["created_at"])
        if latest["status"] != "completed":
            reasons.append(f"the latest {CI_WORKFLOW} run ({latest['id']}) has not completed")
        elif latest["conclusion"] != "success":
            reasons.append(
                f"the latest {CI_WORKFLOW} run ({latest['id']}) concluded {latest['conclusion']}"
            )
    return reasons


def on_main(sha: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
        capture_output=True, text=True,
        check=False,  # exit 1 is the answer "no"; anything else is raised below
    )
    if result.returncode not in (0, 1):
        raise SystemExit(f"git merge-base failed: {result.stderr.strip()}")
    return result.returncode == 0


def ci_runs(repo: str, sha: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/workflows/{CI_WORKFLOW}/runs?head_sha={sha}&per_page=100"],
        capture_output=True, text=True,
        check=True,  # an API failure must stop the release, not read as "no runs"
    )
    runs = json.loads(result.stdout)["workflow_runs"]
    return [
        {"id": r["id"], "created_at": r["created_at"], "status": r["status"], "conclusion": r["conclusion"]}
        for r in runs
        if r["head_sha"] == sha
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    reasons = decide(on_main(args.sha), ci_runs(args.repo, args.sha))
    for reason in reasons:
        print(f"::error::release refused for {args.sha[:12]}: {reason}")
    if not reasons:
        print(f"release gate: {args.sha[:12]} is on main and {CI_WORKFLOW} passed on it")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
