"""The conformance prompts obey their calibration rule — enforced, not stated.

The rule was fixed before any description was written:

    State the business domain, each entity's purpose, and the grain of the
    central fact. Do not name entities, columns, or relationships. Pass
    target_paradigm explicitly.

A rule that exists only in a docstring is an intention. These tests are what
make it a constraint, and they matter because the failure is invisible from the
output: a prompt that names its answer produces a *high* score, and a high score
is the last thing anyone re-examines.

Both directions are checked. Too rich measures transcription — caught by the
leak tests. Too thin measures prompt poverty — caught by the substance tests.
The first version of this harness failed the second check on all five graphs and
nothing noticed, because there was nothing to notice with.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.conformance_prompts import DESCRIPTIONS, build_prompt

GOLD = Path(__file__).resolve().parent / "fixtures" / "gold"

# Column names that are also ordinary nouns of their domain, and are therefore
# permitted in a description. **The principle, stated so it is not re-derived
# to suit whatever failed last:** a prompt may use the domain's vocabulary; it
# may not disclose the schema's structure. Entity names are structure.
# Multi-token identifiers are structure. A single common noun that any
# requirements document in that domain would contain is vocabulary.
#
# Found by these tests failing on their own author's first draft. The
# alternative — banning the nouns — produces evasive prose ("the hardware the
# prospect used" for a device) and tests whether a model can decode
# circumlocution, which is prompt poverty wearing a rule's clothing.
#
# The honest consequence, recorded rather than hidden: column F1 is partly
# credited for domain vocabulary and is a weaker signal than entity F1. The
# threshold already reflects that independently — 0.70 against 0.80 — which is
# the one reassurance that this is not a rationalisation, since those numbers
# were fixed before any of this was written.
DOMAIN_VOCABULARY: dict[str, frozenset[str]] = {
    "banking-datavault": frozenset({"balance", "status"}),
    "marketing-attribution": frozenset({"campaign", "channel", "device"}),
    "saas-subscription": frozenset({"month"}),
}


def _gold() -> dict[str, dict]:
    out = {}
    for path in sorted(GOLD.glob("*.json")):
        if path.name != "index.json":
            out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return out


GOLD_GRAPHS = _gold()


def test_every_gold_graph_has_a_description() -> None:
    """No silent fallback. A missing description is a hard error at run time.

    The filename fallback this replaces is what made every prompt two words and
    every score uninterpretable. Absence must be loud (standard 4) — degrading
    to a default is the same defect wearing a more respectable name.
    """
    missing = sorted(set(GOLD_GRAPHS) - set(DESCRIPTIONS))
    assert not missing, f"gold graphs with no conformance description: {missing}"
    extra = sorted(set(DESCRIPTIONS) - set(GOLD_GRAPHS))
    assert not extra, f"descriptions for graphs that no longer exist: {extra}"


@pytest.mark.parametrize("graph_id", sorted(DESCRIPTIONS))
def test_no_description_leaks_a_schema_identifier(graph_id: str) -> None:
    """The load-bearing check: a prompt must not contain its own answer.

    Two rules. **No snake_case token at all** — business prose has none, and any
    identifier from the schema would carry one, so this catches leaks of names
    nobody thought to enumerate. And **no entity name verbatim**, which catches
    a single-word entity that snake_case would miss.

    Note what is deliberately allowed: the business noun. "customer" is the
    domain vocabulary any real requirements document would use; `dim_customer`
    is the answer. Banning the noun would make the task unstatable, which is the
    over-correction that turns a prompt-quality fix into prompt poverty.
    """
    description = DESCRIPTIONS[graph_id]

    snake = sorted(set(re.findall(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b", description)))
    assert not snake, f"{graph_id} leaks schema identifiers: {snake}"

    raw = GOLD_GRAPHS[graph_id]
    names = {e["entity_name"] for e in raw["entities"]}
    names |= {c["name"] for e in raw["entities"] for c in e["columns"]}
    allowed = DOMAIN_VOCABULARY.get(graph_id, frozenset())
    leaked = sorted(
        n
        for n in names
        if n not in allowed
        and re.search(rf"\b{re.escape(n)}\b", description, re.IGNORECASE)
    )
    assert not leaked, f"{graph_id} names its own schema objects: {leaked}"


def test_the_vocabulary_allowance_is_narrow_and_justified() -> None:
    """The allowance must not become a loophole.

    Every allowed word must be a **single common noun** that is genuinely the
    domain's own vocabulary — never an entity name, never multi-token. Written
    as a test because "we allowed a few words" is how a rule stops being one:
    the next person adds `order_line` to the list and the prompt starts
    disclosing structure again.
    """
    for graph_id, allowed in DOMAIN_VOCABULARY.items():
        entities = {e["entity_name"] for e in GOLD_GRAPHS[graph_id]["entities"]}
        for word in allowed:
            assert "_" not in word, f"{graph_id}: '{word}' is an identifier, not a noun"
            assert word not in entities, (
                f"{graph_id}: '{word}' is an entity name; structure is never vocabulary"
            )
            assert len(word.split()) == 1, f"{graph_id}: '{word}' is a phrase"


@pytest.mark.parametrize("graph_id", sorted(DESCRIPTIONS))
def test_each_description_states_a_grain(graph_id: str) -> None:
    """Grain is the field a model cannot infer and source documents omit.

    It is also the single highest-leverage input the product has — `MISSING_GRAIN`
    is one of the thirteen codes the candidate will be scored against. A prompt
    that omits it is asking the model to guess, then penalising the guess.
    """
    description = DESCRIPTIONS[graph_id].lower()
    assert "grain" in description or "one row" in description, (
        f"{graph_id} states no grain, so the candidate is scored on a guess"
    )


@pytest.mark.parametrize("graph_id", sorted(DESCRIPTIONS))
def test_each_description_is_substantive(graph_id: str) -> None:
    """The thin end of the calibration, guarded with a number.

    Not a proxy for quality — length does not make a description good. It is a
    floor against the failure that actually happened: prompts of two or three
    words, produced by a fallback nobody looked at. A regression to that would
    otherwise show up only as a mysteriously bad provider score.
    """
    words = DESCRIPTIONS[graph_id].split()
    assert len(words) >= 40, (
        f"{graph_id} description is {len(words)} words; the filename fallback "
        f"that made scores uninterpretable was three"
    )


@pytest.mark.parametrize("graph_id", sorted(DESCRIPTIONS))
def test_the_prompt_states_the_paradigm(graph_id: str) -> None:
    """Withholding it scores the model's guess at a naming convention.

    `hub_`/`lnk_`/`sat_` is Data Vault convention, not a fact about banking, and
    `SynthesizeRequest` carries `target_paradigm` because it is not inferable
    from content. A prompt that omits it tests something the product never asks
    a model to do.
    """
    paradigm = GOLD_GRAPHS[graph_id]["paradigm"]
    prompt = build_prompt(paradigm, DESCRIPTIONS[graph_id])
    assert paradigm in prompt, f"{graph_id}'s prompt omits the paradigm"
    assert DESCRIPTIONS[graph_id] in prompt


def test_the_five_paradigms_are_not_all_the_same() -> None:
    """Fixture breadth: the paradigm must actually vary, or supplying it proves nothing.

    Standard 8. If every gold graph were Kimball, `test_the_prompt_states_the_paradigm`
    would pass on a harness that hardcoded "KIMBALL" and the whole paradigm fix
    would be untested.
    """
    paradigms = {raw["paradigm"] for raw in GOLD_GRAPHS.values()}
    assert len(paradigms) > 1, f"only one paradigm across the gold graphs: {paradigms}"
