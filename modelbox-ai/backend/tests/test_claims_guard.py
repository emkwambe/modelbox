"""The claims guard: wording no public surface may use (Sprint 8, owner decision).

This repository is public, so everything in it is a public surface. Barred:

* "BCBS 239 compliant" in any form, and "BCBS 239 requires ...": BCBS 239
  binds G-SIBs and says little about dictionaries; what may be said is
  "definitions, owners, sources and validation rules of the kind BCBS 239
  expects";
* "meets regulatory requirements";
* "industry-standard STTM": there is no such standard;
* any citation of the superseded model-risk letter. The current guidance is
  SR 26-2 (April 2026), which is what a document cites;
* an accuracy figure for finding PII (Sprint 9 Step 4, owner: "No accuracy
  figures anywhere"): no reliable published precision or recall exists for
  metadata-only PII detection, and ours is not measured. A line naming PII
  with a percentage, or with precision, recall, accuracy or F1 and a number,
  is barred.

This file names the barred wording in order to bar it, so it is the one
surface not scanned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]  # modelbox-ai/
SURFACES = ("*.md", "docs/**/*.md", "backend/app/**/*.py", "backend/tests/**/*.py",
            "frontend/src/**/*.ts", "frontend/src/**/*.tsx", "frontend/public/**/*.md", "e2e/**/*.ts")

_OLD_LETTER = "SR 11-7"
_ANY_CASE = re.IGNORECASE
BARRED = {
    "BCBS 239 compliance claim": re.compile(r"BCBS\s*239[\s-]*compliant|compliant\s+with\s+BCBS\s*239", _ANY_CASE),
    "what BCBS 239 requires": re.compile(r"BCBS\s*239\s+requires", _ANY_CASE),
    "meets regulatory requirements": re.compile(r"\bmeets?\s+(all\s+)?regulatory\s+requirements", _ANY_CASE),
    "industry-standard STTM": re.compile(r"industry[\s-]+standard\s+STTM", _ANY_CASE),
    "the superseded model-risk letter": re.compile(r"\bSR\s*11-7\b", _ANY_CASE),
    # On a line naming PII: a metric word and a number close together within
    # one clause ("precision of 0.92", "0.92 recall"), or a percentage with a
    # metric word ("95% accurate"). A percentage alone is not a claim of
    # accuracy: a rubric weight or a survey share names PII with one.
    "an accuracy figure for finding PII": re.compile(
        r"(?=.*\bPII\b)(?=.*(\b(precision|recall|accuracy|F1)\b[^\d.,;:]{0,12}\d"
        r"|\d(\.\d+)?\s?(precision|recall|accuracy|F1)\b"
        r"|(?=.*\b(precision|recall|accura\w*|F1)\b).*\d+(\.\d+)?\s?%))", _ANY_CASE),
}


def _surfaces() -> dict[str, str]:
    this = Path(__file__).resolve()
    paths = {p for pattern in SURFACES for p in APP.glob(pattern)
             if p.is_file() and "node_modules" not in p.parts and p.resolve() != this}
    return {p.relative_to(APP).as_posix(): p.read_text(encoding="utf-8", errors="replace") for p in sorted(paths)}


def _violations(sources: dict[str, str]) -> list[str]:
    found = []
    for name, text in sources.items():
        for number, line in enumerate(text.splitlines(), start=1):
            found += [f"{name}:{number}: {label}" for label, rule in BARRED.items() if rule.search(line)]
    return found


def test_no_public_surface_uses_barred_wording() -> None:
    sources = _surfaces()
    assert "README.md" in sources and "docs/USER_GUIDE.md" in sources and len(sources) > 100, \
        "fixture sanity: the public surfaces were found"
    assert _violations(sources) == []


@pytest.mark.parametrize("sentence", [
    "ModelBox makes your dictionary BCBS 239 compliant.",
    "Fully compliant with BCBS 239.",
    "BCBS 239 requires column-level lineage.",
    "The export meets regulatory requirements.",
    "An industry-standard STTM in one click.",
    "Validated as a model under " + _OLD_LETTER + ".",
    "PII suggestions are 95% accurate.",
    "The PII rules reach a precision of 0.92.",
    "Recall of 88 on PII columns.",
])
def test_negative_control_each_barred_form_is_found(sentence: str) -> None:
    assert _violations({"docs/synthetic.md": sentence}) != []


def test_the_allowed_wording_passes() -> None:
    assert _violations({"docs/synthetic.md": (
        "Definitions, owners, sources and validation rules of the kind BCBS 239 expects; "
        "attribute-level lineage from source to target; model-risk guidance is SR 26-2."
    )}) == []
    assert _violations({"docs/synthetic.md": (
        "A PII suggestion carries no accuracy figure; it is anchored on NIST SP 800-122 §2.2."
    )}) == []
    # A weight or a share is not an accuracy claim.
    assert _violations({"docs/synthetic.md": "| PII classification | 25% | Every sensitive column classified |"}) == []
