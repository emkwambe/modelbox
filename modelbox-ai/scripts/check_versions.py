#!/usr/bin/env python3
"""Assert every version stamp in the repository agrees (M5).

Canonical value: ``backend/app/__version__.py``. Checked stamps:

* ``frontend/package.json`` -> ``version``
* ``docker/docker-compose.appliance.yml`` -> every ``image: modelbox/*:vX.Y.Z``
* ``docs/RELEASE_NOTES_v*.md`` -> the highest-numbered file must match

``/health`` is not checked textually: ``app/main.py`` imports ``__version__``
directly, so it cannot drift by construction.

Usage::

    python scripts/check_versions.py          # verify (exit 1 on drift)
    python scripts/check_versions.py --fix    # rewrite stamps to canonical

Run as a CI job so the four-way disagreement this sprint fixed cannot recur.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PY = ROOT / "backend" / "app" / "__version__.py"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
COMPOSE = ROOT / "docker" / "docker-compose.appliance.yml"
DOCS = ROOT / "docs"

_IMAGE_RE = re.compile(r"^(\s*image:\s*modelbox/[\w.-]+:v)(\d+\.\d+\.\d+)\s*$", re.M)
_RELEASE_RE = re.compile(r"^RELEASE_NOTES_v(\d+)\.(\d+)\.(\d+)\.md$")


def canonical_version() -> str:
    match = re.search(
        r'^__version__\s*=\s*"([^"]+)"', VERSION_PY.read_text(encoding="utf-8"), re.M
    )
    if not match:
        sys.exit(f"could not read __version__ from {VERSION_PY}")
    return match.group(1)


def latest_release_notes() -> tuple[Path, str] | None:
    candidates = []
    for path in DOCS.glob("RELEASE_NOTES_v*.md"):
        match = _RELEASE_RE.match(path.name)
        if match:
            candidates.append((tuple(int(g) for g in match.groups()), path))
    if not candidates:
        return None
    parts, path = max(candidates)
    return path, ".".join(str(p) for p in parts)


def check(fix: bool) -> int:
    version = canonical_version()
    problems: list[str] = []

    # --- frontend/package.json -------------------------------------------
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    if package.get("version") != version:
        if fix:
            text = PACKAGE_JSON.read_text(encoding="utf-8")
            PACKAGE_JSON.write_text(
                re.sub(
                    r'("version":\s*")[^"]+(")',
                    rf"\g<1>{version}\g<2>",
                    text,
                    count=1,
                ),
                encoding="utf-8",
                newline="\n",
            )
        else:
            problems.append(
                f"{PACKAGE_JSON.relative_to(ROOT)}: version="
                f"{package.get('version')!r}, expected {version!r}"
            )

    # --- compose image tags ----------------------------------------------
    compose_text = COMPOSE.read_text(encoding="utf-8")
    stale = [m.group(2) for m in _IMAGE_RE.finditer(compose_text) if m.group(2) != version]
    if stale:
        if fix:
            COMPOSE.write_text(
                _IMAGE_RE.sub(rf"\g<1>{version}", compose_text),
                encoding="utf-8",
                newline="\n",
            )
        else:
            problems.append(
                f"{COMPOSE.relative_to(ROOT)}: image tags {sorted(set(stale))} "
                f"!= {version}"
            )

    # --- release notes ----------------------------------------------------
    latest = latest_release_notes()
    if latest is None:
        problems.append("no docs/RELEASE_NOTES_v*.md found")
    else:
        path, notes_version = latest
        if notes_version != version:
            problems.append(
                f"newest release notes are {path.name} ({notes_version}) but the "
                f"canonical version is {version}; write "
                f"docs/RELEASE_NOTES_v{version}.md"
            )

    if problems:
        print(f"version drift against canonical {version}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        if not fix:
            print(
                "\nrun: python scripts/check_versions.py --fix", file=sys.stderr
            )
        return 1

    print(f"all version stamps agree: {version}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite stamps")
    raise SystemExit(check(parser.parse_args().fix))
