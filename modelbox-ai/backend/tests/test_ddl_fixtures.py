"""The DDL fixtures say what they are: genuine tool exports, or documentation-derived.

`fixtures/ddl/{oracle,tsql,postgres}/` holds DDL written by the databases' own
export tools in CI (`.github/workflows/ddl-fixtures.yml`), never by hand. That
workflow regenerates them and fails unless the committed copies match; this
module holds what can be checked without a database:

* every expected fixture exists, so deleting one cannot turn that comparison
  into a silent skip;
* each genuine fixture opens with a complete provenance header: source, tool
  and version, image pinned by digest, and the date and run that generated it;
* each has a manifest whose counts come from the catalog views, and whose
  per-table rows add up to its totals.

`fixtures/ddl/snowflake/` is the exception. No Snowflake account runs in CI, so
its one fixture is hand-written from Snowflake's GET_DDL documentation. It must
say so, in its header and in its manifest, whose counts come from the file's own
text. While it is documentation-derived, nothing in the docs, the application or
the frontend may call Snowflake import certified.

Negative controls (Amendment 2): a header without an image digest, a manifest
whose rows disagree with its totals, the documentation-derived label removed,
and a sentence calling Snowflake import certified each fail their check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
APP = Path(__file__).resolve().parents[2]  # modelbox-ai/
EXPECTED = {
    "oracle": ("hr", "co"),
    "tsql": ("adventureworks",),
    "postgres": ("pagila",),
    "snowflake": ("ledger_schema",),
}
DOCUMENTATION_DERIVED = {("snowflake", "ledger_schema")}
HEADER_END = "-- end of provenance"
GENUINE_HEADER = {
    "source": re.compile(r"^-- source: \S.+\(MIT; see \.\./README\.md\)$"),
    "tool": re.compile(r"^-- tool: \S.+$"),
    "image": re.compile(r"^-- image: \S+@sha256:[0-9a-f]{64}$"),
    "generated": re.compile(r"^-- generated: \d{4}-\d{2}-\d{2} by https://github\.com/\S+/actions/runs/\d+$"),
}
DOCUMENTED_HEADER = {
    "label": re.compile(r"^-- ModelBox DDL fixture: DOCUMENTATION-DERIVED\. "),
    "provenance": re.compile(r"^-- provenance: documentation-derived$"),
    "source": re.compile(r"^-- source: Snowflake documentation, GET_DDL \(https://docs\.snowflake\.com/\S+\), retrieved \d{4}-\d{2}-\d{2}\. "),
    "certification": re.compile(r"^-- certification: Snowflake import is not certified while this fixture is documentation-derived$"),
}
COUNT_KEYS = ("columns", "primary_keys", "foreign_keys", "unique_constraints",
              "check_constraints", "table_descriptions", "column_descriptions")

# A sentence calling Snowflake import certified: one sentence naming all three,
# in any order. A negated statement ("is not certified") is not a claim.
_CLAIM_WORDS = (
    re.compile(r"snowflake", re.IGNORECASE),
    re.compile(r"\bimport", re.IGNORECASE),
    re.compile(r"\bcertif", re.IGNORECASE),
)
_SENTENCE_END = re.compile(r"(?<=[.;!?])\s+|\n")
_NEGATED = re.compile(r"\b(not|never|un)\s*[- ]?\s*(yet\s+)?certif|isn't certif|uncertified", re.IGNORECASE)
CLAIM_SURFACES = ("README.md", "docs/**/*.md", "backend/app/**/*.py",
                  "frontend/src/**/*.ts", "frontend/src/**/*.tsx")


def _header(text: str) -> list[str]:
    lines = text.splitlines()
    assert HEADER_END in lines, "no end-of-provenance marker"
    return lines[: lines.index(HEADER_END)]


def _header_problems(text: str, documentation_derived: bool = False) -> list[str]:
    header = _header(text)
    rules = DOCUMENTED_HEADER if documentation_derived else GENUINE_HEADER
    return [
        name for name, pattern in rules.items()
        if not any(pattern.match(line) for line in header)
    ]


def _manifest_problems(manifest: dict, fixture: str, documentation_derived: bool = False) -> list[str]:
    problems: list[str] = []
    if manifest.get("fixture") != fixture:
        problems.append(f"names {manifest.get('fixture')!r}, not {fixture!r}")
    counts_from = str(manifest.get("counts_from", ""))
    if documentation_derived:
        if manifest.get("provenance") != "documentation-derived":
            problems.append("manifest does not say it is documentation-derived")
        if not counts_from.startswith("fixture text (documentation-derived"):
            problems.append("counts do not say they come from the fixture text")
    elif not counts_from.startswith("catalog views"):
        problems.append("counts are not from the catalog views")
    counts, tables = manifest.get("counts", {}), manifest.get("tables", [])
    if counts.get("tables") != len(tables) or not tables:
        problems.append(f"counts.tables {counts.get('tables')} vs {len(tables)} rows")
    for key in COUNT_KEYS:
        total = sum(int(t[key]) for t in tables)
        if counts.get(key) != total:
            problems.append(f"{key}: total {counts.get(key)} but rows sum to {total}")
    return problems


def _certification_claims(sources: dict[str, str]) -> list[str]:
    return [
        f"{name}: {sentence.strip()}"
        for name, text in sources.items()
        for sentence in _SENTENCE_END.split(text)
        if all(word.search(sentence) for word in _CLAIM_WORDS) and not _NEGATED.search(sentence)
    ]


def _claim_surfaces() -> dict[str, str]:
    paths = {p for pattern in CLAIM_SURFACES for p in APP.glob(pattern) if p.is_file()}
    return {str(p.relative_to(APP)): p.read_text(encoding="utf-8", errors="replace") for p in sorted(paths)}


FIXTURES = [(dialect, stem) for dialect, stems in EXPECTED.items() for stem in stems]
IDS = [f"{d}-{s}" for d, s in FIXTURES]


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=IDS)
def test_every_expected_fixture_and_manifest_exists(dialect: str, stem: str) -> None:
    assert (DDL / dialect / f"{stem}.sql").is_file()
    assert (DDL / dialect / f"{stem}.manifest.json").is_file()


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=IDS)
def test_every_fixture_has_a_complete_provenance_header(dialect: str, stem: str) -> None:
    text = (DDL / dialect / f"{stem}.sql").read_text(encoding="utf-8")
    assert _header_problems(text, (dialect, stem) in DOCUMENTATION_DERIVED) == []


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=IDS)
def test_every_manifest_says_where_its_counts_come_from_and_adds_up(dialect: str, stem: str) -> None:
    manifest = json.loads((DDL / dialect / f"{stem}.manifest.json").read_text(encoding="utf-8"))
    assert _manifest_problems(manifest, f"{stem}.sql", (dialect, stem) in DOCUMENTATION_DERIVED) == []


def test_no_unexpected_fixture_files() -> None:
    """A new fixture is added to EXPECTED, so the checks above cover it."""
    found = {(p.parent.name, p.name.split(".")[0]) for p in DDL.glob("*/*.sql")}
    assert found == set(FIXTURES)


def test_only_snowflake_is_documentation_derived() -> None:
    """Every other dialect is held to the genuine-export rules."""
    assert {dialect for dialect, _ in DOCUMENTATION_DERIVED} == {"snowflake"}


def test_nothing_calls_snowflake_import_certified_while_its_fixture_is_documentation_derived() -> None:
    if not any(dialect == "snowflake" for dialect, _ in DOCUMENTATION_DERIVED):
        pytest.fail("no documentation-derived Snowflake fixture: this guard must be revisited, not skipped")
    sources = _claim_surfaces()
    assert "README.md" in sources and len(sources) > 20, "claim surfaces not found"
    assert _certification_claims(sources) == []


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


def test_negative_control_removing_the_documentation_derived_label_fails() -> None:
    text = (DDL / "snowflake" / "ledger_schema.sql").read_text(encoding="utf-8")
    unlabelled = text.replace("DOCUMENTATION-DERIVED", "genuine tool output").replace(
        "-- provenance: documentation-derived\n", ""
    )
    assert unlabelled != text
    with pytest.raises(AssertionError):
        assert _header_problems(unlabelled, documentation_derived=True) == []
    manifest = json.loads((DDL / "snowflake" / "ledger_schema.manifest.json").read_text(encoding="utf-8"))
    del manifest["provenance"]
    with pytest.raises(AssertionError):
        assert _manifest_problems(manifest, "ledger_schema.sql", documentation_derived=True) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Snowflake import is certified.",
        "Certified DDL import: Oracle, SQL Server, PostgreSQL and Snowflake.",
        "Import from Snowflake — certified on genuine exports.",
    ],
)
def test_negative_control_a_certification_claim_is_found(sentence: str) -> None:
    with pytest.raises(AssertionError):
        assert _certification_claims({"docs/synthetic.md": sentence}) == []


def test_a_negated_statement_is_not_a_claim() -> None:
    assert _certification_claims(
        {"docs/synthetic.md": "Snowflake import is not certified while its fixture is documentation-derived."}
    ) == []
