#!/usr/bin/env python3
"""Fail unless a committed DDL fixture is what the tool produces today.

``ddl-fixtures.yml`` regenerates every fixture and runs this against the
committed copies. Only the generation date and run are allowed to differ: the
``-- generated:`` header line, and the manifest's ``generated`` and ``run``
keys. Anything else, one edited statement or one changed count, is a
difference, so a committed fixture can only be what the tool wrote.

Usage::

    python compare_fixture.py COMMITTED_DIR REGENERATED_DIR

Every ``*.sql`` and ``*.manifest.json`` in REGENERATED_DIR must exist in
COMMITTED_DIR and match; a committed file with no regenerated counterpart is
also a failure. Exits 1 on any difference.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

VOLATILE_KEYS = ("generated", "run")


def _sql_lines(path: Path) -> list[str]:
    return [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("-- generated: ")
    ]


def _manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if key not in VOLATILE_KEYS}


def compare(committed: Path, regenerated: Path) -> list[str]:
    problems: list[str] = []
    new = {p.name for p in regenerated.iterdir() if p.suffix in (".sql", ".json")}
    old = {p.name for p in committed.iterdir() if p.suffix in (".sql", ".json")} if committed.is_dir() else set()
    for name in sorted(new - old):
        problems.append(f"{name}: regenerated but not committed")
    for name in sorted(old - new):
        problems.append(f"{name}: committed but not regenerated")
    for name in sorted(new & old):
        if name.endswith(".sql"):
            a, b = _sql_lines(committed / name), _sql_lines(regenerated / name)
            if a != b:
                diff = list(difflib.unified_diff(a, b, "committed", "regenerated", lineterm="", n=1))
                problems.append(f"{name}: differs\n" + "\n".join(diff[:40]))
        elif _manifest(committed / name) != _manifest(regenerated / name):
            problems.append(f"{name}: manifest differs")
    return problems


def main() -> int:
    committed, regenerated = Path(sys.argv[1]), Path(sys.argv[2])
    problems = compare(committed, regenerated)
    for problem in problems:
        print(f"::error::{problem}")
    if not problems:
        print(f"{committed}: every fixture matches its regeneration")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
