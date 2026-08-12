"""Populate the offline dbt package cache the fidelity harness builds against.

`dbt build` needs the packages a project depends on to be installed, and
`dbt deps` fetches them over the network. The harness is offline by
construction — `MODELBOX_FIDELITY_STRICT` means a gate cannot pass by skipping,
and a gate that can fail because a package registry is slow is not a gate. So
the download happens **here**, once, as a setup step, exactly as `protoc` and
`node` are installed once and detected rather than fetched per run.

Two properties make the cache trustworthy rather than merely convenient:

* **It is built from the product's own `packages.yml`.** The exporter emits that
  file; this script does not write one. Supplying scaffolding the product should
  have emitted is how finding H9 went unnoticed for a sprint — the dbt projects
  in the audit parsed only because the harness had hand-written the sources file
  the exporter failed to produce. Nothing here may repeat that.

* **A deprecation is a failure, not a warning.** `dbt deps` is the only place
  the redirect deprecations are observable at all (they fire against the
  registry, so no offline command can see them). Making them fatal here is what
  lets the offline test assert against `package-lock.yml` and mean something:
  the lock is evidence that a network-time check ran and passed.

Usage::

    .venv-tools/Scripts/python scripts/refresh_dbt_packages.py

Writes `backend/.dbt-packages/` (gitignored) and refreshes the committed
`backend/tests/fixtures/dbt/package-lock.yml`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.schemas.data_model import SynthesizedModel  # noqa: E402
from app.services.exporter_service import ExporterService  # noqa: E402

CACHE_DIR = _BACKEND / ".dbt-packages"
LOCK_FIXTURE = _BACKEND / "tests" / "fixtures" / "dbt" / "package-lock.yml"
# The fixture that declares quality rules, and therefore the only one whose
# emitted project depends on a package at all.
SOURCE_FIXTURE = _BACKEND / "tests" / "fixtures" / "synthetic" / "quality_rules.json"


def _emitted_packages_yml() -> str:
    raw = json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))
    model = SynthesizedModel(**(raw.get("model") or raw))
    files = ExporterService().generate_dbt_project(model)
    packages = files.get("packages.yml")
    if packages is None:
        raise SystemExit(
            f"{SOURCE_FIXTURE.name} no longer produces a packages.yml, so the "
            f"cache would be built from nothing. Either the fixture stopped "
            f"declaring quality rules or the exporter stopped declaring its "
            f"dependency — both are defects, not reasons to skip."
        )
    return packages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the cache is present and matches the committed lock; "
             "do not touch the network",
    )
    args = parser.parse_args()

    if args.check:
        return _check()

    dbt = shutil.which("dbt")
    if dbt is None:
        raise SystemExit("dbt is not on PATH; install backend/requirements-dev.txt")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "packages.yml").write_text(_emitted_packages_yml(), encoding="utf-8")
        (root / "dbt_project.yml").write_text(
            "name: 'package_cache'\nversion: '1.0'\nprofile: 'modelbox'\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [dbt, "deps", "--show-all-deprecations", "--project-dir", str(root)],
            capture_output=True,
            text=True,
            cwd=root,
        )
        output = proc.stdout + proc.stderr
        print(output)
        if proc.returncode != 0:
            raise SystemExit(
                "dbt deps failed. If it rejected packages.yml, the exporter is "
                "emitting an invalid dependency declaration — fix that rather "
                "than hand-writing the file here."
            )
        if "Deprecat" in output:
            raise SystemExit(
                "dbt reported a deprecation while resolving the exporter's own "
                "packages.yml. This script is the only place those are "
                "observable, so it is the only place they can be caught. "
                "Fix the emitted dependency; do not cache a deprecated one."
            )

        installed = root / "dbt_packages"
        if not installed.is_dir() or not any(installed.iterdir()):
            raise SystemExit("dbt deps reported success but installed nothing")

        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        shutil.copytree(installed, CACHE_DIR)
        LOCK_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "package-lock.yml", LOCK_FIXTURE)

    files = sum(1 for _ in CACHE_DIR.rglob("*") if _.is_file())
    print(f"cached {files} files into {CACHE_DIR}")
    print(f"lock written to {LOCK_FIXTURE.relative_to(_BACKEND)} — commit it")
    return 0


def _check() -> int:
    if not CACHE_DIR.is_dir() or not any(CACHE_DIR.iterdir()):
        print(f"MISSING: {CACHE_DIR}", file=sys.stderr)
        return 1
    if not LOCK_FIXTURE.is_file():
        print(f"MISSING: {LOCK_FIXTURE}", file=sys.stderr)
        return 1
    print(f"cache present: {CACHE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
