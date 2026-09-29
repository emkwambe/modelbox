"""The DDL fixtures are genuine tool exports, and say so.

`fixtures/ddl/{oracle,tsql}/` holds DDL written by the databases' own export
tools in CI (`.github/workflows/ddl-fixtures.yml`), never by hand. That
workflow regenerates them and fails unless the committed copies match; this
module holds what can be checked without a database:

* every expected fixture exists, so deleting one cannot turn that comparison
  into a silent skip;
* each opens with a complete provenance header: source, tool and version,
  image pinned by digest, and the date and run that generated it;
* each has a manifest whose counts come from the catalog views, and whose
  per-table rows add up to its totals.

Negative controls (Amendment 2): a header without an image digest, and a
manifest whose rows disagree with its totals, each fail their check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
EXPECTED = {
    "oracle": ("hr", "co"),
    "tsql": ("adventureworks",),
}
HEADER_END = "-- end of provenance"
REQUIRED_HEADER = {
    "source": re.compile(r"^-- source: \S.+\(MIT; see \.\./README\.md\)$"),
    "tool": re.compile(r"^-- tool: \S.+$"),
    "image": re.compile(r"^-- image: \S+@sha256:[0-9a-f]{64}$"),
    "generated": re.compile(r"^-- generated: \d{4}-\d{2}-\d{2} by https://github\.com/\S+/actions/runs/\d+$"),
}
COUNT_KEYS = ("columns", "primary_keys", "foreign_keys", "unique_constraints",
              "check_constraints", "table_descriptions", "column_descriptions")


def _header(text: str) -> list[str]:
    lines = text.splitlines()
    assert HEADER_END in lines, "no end-of-provenance marker"
    return lines[: lines.index(HEADER_END)]


def _header_problems(text: str) -> list[str]:
    header = _header(text)
    return [
        name for name, pattern in REQUIRED_HEADER.items()
        if not any(pattern.match(line) for line in header)
    ]


def _manifest_problems(manifest: dict, fixture: str) -> list[str]:
    problems: list[str] = []
    if manifest.get("fixture") != fixture:
        problems.append(f"names {manifest.get('fixture')!r}, not {fixture!r}")
    if not str(manifest.get("counts_from", "")).startswith("catalog views"):
        problems.append("counts are not from the catalog views")
    counts, tables = manifest.get("counts", {}), manifest.get("tables", [])
    if counts.get("tables") != len(tables) or not tables:
        problems.append(f"counts.tables {counts.get('tables')} vs {len(tables)} rows")
    for key in COUNT_KEYS:
        total = sum(int(t[key]) for t in tables)
        if counts.get(key) != total:
            problems.append(f"{key}: total {counts.get(key)} but rows sum to {total}")
    return problems


FIXTURES = [(dialect, stem) for dialect, stems in EXPECTED.items() for stem in stems]


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[f"{d}-{s}" for d, s in FIXTURES])
def test_every_expected_fixture_and_manifest_exists(dialect: str, stem: str) -> None:
    assert (DDL / dialect / f"{stem}.sql").is_file()
    assert (DDL / dialect / f"{stem}.manifest.json").is_file()


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[f"{d}-{s}" for d, s in FIXTURES])
def test_every_fixture_has_a_complete_provenance_header(dialect: str, stem: str) -> None:
    text = (DDL / dialect / f"{stem}.sql").read_text(encoding="utf-8")
    assert _header_problems(text) == []


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[f"{d}-{s}" for d, s in FIXTURES])
def test_every_manifest_is_catalog_derived_and_adds_up(dialect: str, stem: str) -> None:
    manifest = json.loads((DDL / dialect / f"{stem}.manifest.json").read_text(encoding="utf-8"))
    assert _manifest_problems(manifest, f"{stem}.sql") == []


def test_no_unexpected_fixture_files() -> None:
    """A new fixture is added to EXPECTED, so the checks above cover it."""
    found = {(p.parent.name, p.name.split(".")[0]) for p in DDL.glob("*/*.sql")}
    assert found == set(FIXTURES)


def test_negative_control_a_header_without_an_image_digest_fails() -> None:
    text = (DDL / "oracle" / "hr.sql").read_text(encoding="utf-8")
    weakened = re.sub(r"@sha256:[0-9a-f]{64}", ":latest", text, count=1)
    assert weakened != text
    with pytest.raises(AssertionError):
        assert _header_problems(weakened) == []


def test_negative_control_a_manifest_that_does_not_add_up_fails() -> None:
    manifest = json.loads((DDL / "oracle" / "hr.manifest.json").read_text(encoding="utf-8"))
    manifest["tables"][0]["columns"] += 1
    with pytest.raises(AssertionError):
        assert _manifest_problems(manifest, "hr.sql") == []
