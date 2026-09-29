"""The Security FAQ may not claim more than the Proof Log proves (G2, E2).

E2 says no public surface states a capability without a `PL-` identifier behind
it. The Security FAQ is the most public surface in the repository — it is written
to be handed to someone whose job is to disbelieve it — and it is also the
easiest place for a claim to drift, because the sentences are persuasive by
design and the evidence is in another file.

So the citation is checked rather than trusted: every `PL-` the FAQ names must
resolve to an entry that exists, and the entries it leans on must still be there.
A document citing `PL-011` because someone drafted an entry that never landed
would read exactly as authoritative as this one does.

**What this cannot check**, stated so nobody reads it as more than it is: that
the prose beside a citation is a fair summary of the entry. That is a judgement,
and the answer is the Proof Log's own structure — each entry carries its honest
limits and a "not usable as" line, so a reviewer can follow the citation and see
what the claim may not be stretched to say.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs"
FAQ = DOCS / "SECURITY_FAQ.md"
PROOF_LOG = DOCS / "marketing" / "PROOF_LOG.md"

PL_REFERENCE = re.compile(r"\bPL-(\d{3})\b")
PL_ENTRY = re.compile(r"^## PL-(\d{3}) — ", re.MULTILINE)


def _faq() -> str:
    return FAQ.read_text(encoding="utf-8")


def _entries() -> set[str]:
    return set(PL_ENTRY.findall(PROOF_LOG.read_text(encoding="utf-8")))


def test_the_faq_exists_and_answers_the_three_questions() -> None:
    """G2 names them: what leaves, where it goes, how to stop it.

    Asserted because the criterion is about a reviewer finding answers, not
    about a file existing. A document that discusses security in general while
    leaving one of the three unanswered has not met it.
    """
    text = _faq().lower()
    for question in ("what leaves", "where does it go", "how do we stop it"):
        assert question in text, f"the FAQ does not answer '{question}'"


def test_the_proof_log_still_defines_every_entry_the_faq_cites() -> None:
    """A citation to an entry that does not exist reads as authoritative anyway."""
    cited = set(PL_REFERENCE.findall(_faq()))
    assert cited, "fixture sanity: the FAQ cites no Proof Log entry at all"

    missing = sorted(cited - _entries())
    assert not missing, (
        f"the Security FAQ cites Proof Log entries that do not exist: "
        f"{['PL-' + m for m in missing]}"
    )


@pytest.mark.parametrize("entry", ["008", "009", "010"])
def test_the_claims_the_faq_leans_on_are_still_proven(entry: str) -> None:
    """These three carry the answers to G2's three questions.

    Named individually rather than derived from the FAQ, so deleting a claim
    from the document does not quietly delete the requirement that it be
    provable. If one of these is ever marked EXPIRED, the FAQ needs rewriting
    before it is handed to anyone.
    """
    assert entry in _entries(), f"PL-{entry} is no longer in the Proof Log"


def test_no_capability_section_is_silent_about_its_evidence() -> None:
    """Each of the three answer sections must cite something.

    The failure this rules out is a section that reads as a guarantee while
    citing nothing — which is how a document that started disciplined becomes a
    brochure one paragraph at a time.
    """
    sections = re.split(r"^## ", _faq(), flags=re.MULTILINE)
    answers = [
        s
        for s in sections
        if s.startswith(("1. What leaves", "3. How do we stop", "4. What is recorded"))
    ]
    assert len(answers) == 3, "the FAQ's answer sections have been renamed"
    for section in answers:
        assert PL_REFERENCE.search(section), (
            f"section '{section.splitlines()[0]}' states capabilities without "
            f"citing a Proof Log entry"
        )


def test_the_faq_states_what_is_not_claimed() -> None:
    """A security document that only lists strengths is not a security document.

    The 'what we do not claim' section is the part a reviewer checks first for
    honesty, and it is the part most likely to be trimmed by someone polishing
    for an audience.
    """
    text = _faq()
    assert "## 6. What we do not claim" in text
    for limit in ("masking", "certification", "retention"):
        assert limit in text.lower(), (
            f"the FAQ no longer discloses its limit regarding '{limit}'"
        )
