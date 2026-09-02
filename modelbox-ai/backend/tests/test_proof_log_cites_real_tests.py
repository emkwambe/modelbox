"""Every test the Proof Log names exists (E2, enforced rather than promised).

`CLAUDE.md` states the rule plainly: *"A Proof Log entry requires a passing
test. Not a plausible argument, not a finding that is merely interesting — a
named test that passes. An entry without one is the exact failure the document
exists to prevent."*

Until this file, nothing checked it. `test_security_faq_cites_real_proof.py`
guards the **FAQ → Proof Log** direction — the FAQ may not cite a `PL-` id that
does not exist — and that is one link of a two-link chain. The other link, the
one the rule is actually about, was unguarded: a Proof Log entry could name
`test_odcs_apiverison_is_current` and no run anywhere would notice. The claim
would read as evidenced, the citation would be unfollowable, and the document
would be doing the opposite of its job.

That is not hypothetical arithmetic. Four entries were added in one commit on
2026-09-01 citing roughly thirty test names, transcribed by hand.

**What this asserts and what it does not.** It asserts every cited name is
defined in `tests/`. It does not assert the test passes — the suite does that,
and a citation to a test that exists and fails is caught by the run rather than
by a grep. It also cannot see a test that is collected but skipped; the fidelity
tests skip without `.venv-tools`, which is why `MODELBOX_FIDELITY_STRICT=1`
exists one layer out.

A static scan rather than pytest's collector, deliberately: the collector cannot
run here without importing the fidelity toolchain, and this check must work in
the environment the app suite already uses. The cost is that a commented-out
`def test_x` would satisfy it — which is a narrower hole than the one it closes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROOF_LOG = TESTS_DIR.parents[1] / "docs" / "marketing" / "PROOF_LOG.md"

# `::test_name` or a bare `test_name` inside backticks — both forms the document
# uses. A parametrised citation (`test_x[gold]`) resolves to the function name.
#
# The `(?!\.py)` is not decoration. The document's usual form is
# `test_artifact_fidelity.py::test_odcs_apiversion_is_current`, and without the
# lookahead the leading backtick match captures the *file* name — so the first
# run of this check reported eight "missing tests" that were all module names.
# A scanner that cannot tell a file from a function would have made every entry
# in the document look broken.
# `(?![a-z0-9_])` comes first and is load-bearing: with only `(?!\.py)` the
# greedy `+` simply gives back a character to satisfy the lookahead, so
# `test_artifact_fidelity.py` matched as `test_artifact_fidelit`. The first
# lookahead pins the end of the identifier; the second then rejects a file.
_CITATION = re.compile(r"(?:::|`)(test_[a-z0-9_]+)(?![a-z0-9_])(?!\.py)")


def _cited_test_names() -> set[str]:
    return set(_CITATION.findall(PROOF_LOG.read_text(encoding="utf-8")))


def _defined_test_names() -> set[str]:
    defined: set[str] = set()
    for path in TESTS_DIR.rglob("test_*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        defined.update(re.findall(r"^\s*(?:async )?def (test_[a-z0-9_]+)", source, re.MULTILINE))
    return defined


def test_the_proof_log_is_readable_and_cites_something() -> None:
    """Precondition, and the one that matters.

    A moved or renamed `PROOF_LOG.md`, or a citation format this regex stopped
    recognising, would yield an empty set — and an empty set satisfies every
    assertion below by iterating nothing. This repository has shipped that
    shape four times, which is why standard 8 exists.
    """
    assert PROOF_LOG.exists(), f"Proof Log not found at {PROOF_LOG}"
    cited = _cited_test_names()
    assert len(cited) >= 20, f"only {len(cited)} citations parsed — has the format changed?"


def test_the_scan_finds_the_test_suite() -> None:
    """The other half of the same precondition.

    If `_defined_test_names` returned nothing, every citation would look broken
    and this file would fail loudly rather than pass quietly — but it would be
    failing for the wrong reason, and a reader would chase the Proof Log instead
    of the scanner.
    """
    defined = _defined_test_names()
    assert len(defined) > 200, f"only {len(defined)} test definitions found"
    # A name this file itself defines, so the scanner is checked against a known
    # answer rather than only against a count.
    assert "test_the_scan_finds_the_test_suite" in defined


MARKETING = PROOF_LOG.parent
_PL_ID = re.compile(r"\bPL-(\d{3})\b")


def _defined_pl_ids() -> set[str]:
    return set(
        re.findall(r"^## (PL-\d{3})", PROOF_LOG.read_text(encoding="utf-8"), re.MULTILINE)
    )


def _surfaces() -> list[Path]:
    """Public-facing marketing documents other than the Proof Log itself.

    `.html` is included because the customer-facing page is one — the rule is
    about what a buyer reads, not about a file extension, and a claim sheet that
    checked only Markdown would miss the single surface most likely to be sent
    to a prospect.
    """
    return [
        p
        for suffix in ("*.md", "*.html")
        for p in MARKETING.rglob(suffix)
        if p.name != PROOF_LOG.name and "superseded" not in p.parts
    ]


def test_there_are_marketing_surfaces_and_entries_to_check() -> None:
    """Precondition for the rule below, which is a loop over two globs."""
    assert _defined_pl_ids(), "no PL- entries parsed from the Proof Log"
    assert _surfaces(), "no marketing surfaces found to check"


def test_every_pl_id_a_public_surface_cites_is_defined() -> None:
    """Register G3, enforced: every landing-page claim traces to a Proof Log ID.

    `VALUE_NARRATIVE.md` cites a dozen ids by hand. A typo — `PL-015`, or a
    number kept after an entry was renumbered — would read to a buyer as
    evidence and resolve to nothing, which is the precise failure the Claims
    rule exists to prevent, committed on the one surface a customer actually
    reads.

    Deliberately *not* the inverse assertion. An entry nothing cites yet is
    fine: the Proof Log is the register of what we have earned, and the
    marketing is a selection from it.
    """
    defined = _defined_pl_ids()
    broken: list[str] = []
    for surface in _surfaces():
        for number in _PL_ID.findall(surface.read_text(encoding="utf-8")):
            if f"PL-{number}" not in defined:
                broken.append(f"{surface.name} cites PL-{number}")
    assert not broken, f"public surfaces cite undefined Proof Log ids: {broken}"


@pytest.mark.parametrize("name", sorted(_cited_test_names()))
def test_every_test_the_proof_log_names_exists(name: str) -> None:
    """One case per citation, so a failure names the broken one.

    Parametrised rather than asserted as a set difference because the useful
    output is *which* citation is unfollowable — a set-difference failure prints
    a blob and a reader has to diff it by eye.
    """
    assert name in _defined_test_names(), (
        f"PROOF_LOG.md cites `{name}`, which is not defined anywhere in tests/. "
        f"A claim whose evidence cannot be followed is the failure the Proof Log "
        f"exists to prevent."
    )
