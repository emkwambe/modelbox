#!/usr/bin/env python3
"""Fail if a tracked file belongs to the private repository.

This repository is public. Sprint prompts and plans, research, marketing plans,
assessments and market studies live in a separate private repository, and this
check keeps them from coming back. Every path `git ls-files` reports, from the
repository root, is matched case-insensitively against:

* ``docs/SPRINT_*``            sprint prompts (progress logs, ``sprint-*``, stay public)
* ``docs/research/``           research
* ``docs/marketing/*PLAN*``    marketing plans
* ``*assessment*``             assessments, anywhere
* ``*Market_Study*``           the market study, anywhere
* ``*Sprint_Plan*``            sprint plans, anywhere

Usage::

    python modelbox-ai/scripts/check_leak_guard.py    # exit 1 on any match
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable

# (description, pattern). Matched against the whole path, case-insensitively.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("docs/SPRINT_*", re.compile(r"(?:^|/)docs/SPRINT_[^/]*$", re.IGNORECASE)),
    ("docs/research/", re.compile(r"(?:^|/)docs/research/", re.IGNORECASE)),
    ("docs/marketing/*PLAN*", re.compile(r"(?:^|/)docs/marketing/[^/]*PLAN[^/]*$", re.IGNORECASE)),
    ("*assessment*", re.compile(r"assessment", re.IGNORECASE)),
    ("*Market_Study*", re.compile(r"market_study", re.IGNORECASE)),
    ("*Sprint_Plan*", re.compile(r"sprint_plan", re.IGNORECASE)),
)


def violations(paths: Iterable[str]) -> list[tuple[str, str]]:
    """(path, pattern) for every path that matches a private-repository pattern."""
    found: list[tuple[str, str]] = []
    for path in paths:
        normalised = path.replace("\\", "/")
        for description, pattern in PATTERNS:
            if pattern.search(normalised):
                found.append((normalised, description))
                break
    return found


def tracked_paths() -> list[str]:
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,  # no repository is a hard error
    ).stdout.strip()
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in listing.split("\0") if p]


def main() -> int:
    paths = tracked_paths()
    if not paths:
        # An empty listing would pass vacuously; it means the check saw nothing.
        print("leak guard: git ls-files returned no paths", file=sys.stderr)
        return 1
    found = violations(paths)
    for path, description in found:
        print(f"::error file={path}::matches {description}; this belongs in the private repository")
    print(f"leak guard: {len(paths)} tracked paths checked, {len(found)} violations")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
