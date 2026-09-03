"""The size x domain cells obey the same rules as the D10 descriptions.

Two new descriptions were written for cells that had no gold graph, and a
description authored freely is a description that can hand the model its answer.
The calibration rule is inherited unchanged from `conformance_prompts`, and so
is its enforcement — a prompt that names its own schema measures transcription.

The design checks matter as much as the leak check here. This experiment
manipulates *size* and *domain* as independent factors, so a run where the two
"large" cells are not actually larger, or where the "small specialised" cell is
specialised only in name, has not tested anything. Those are preconditions on
the fixture in the sense stop condition 4 means: assertions that would fail if
the experiment could not answer its question.
"""

from __future__ import annotations

import re

import pytest

from scripts.experiment_prompts import CELLS


@pytest.mark.parametrize("cell_id", sorted(CELLS))
def test_no_description_leaks_a_schema_identifier(cell_id: str) -> None:
    """No snake_case token, exactly as the D10 rule requires.

    Business prose contains none, so any identifier lifted from a schema shows
    up here — including from a schema nobody has written yet, which is the case
    for the two new cells and the reason this is the check that transfers.
    """
    _, description, _, _, _ = CELLS[cell_id]
    snake = sorted(set(re.findall(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b", description)))
    assert not snake, f"{cell_id} leaks schema identifiers: {snake}"


@pytest.mark.parametrize("cell_id", sorted(CELLS))
def test_no_description_names_a_kimball_construct(cell_id: str) -> None:
    """Nor the paradigm's vocabulary.

    `target_paradigm` is supplied to the model separately, so a description that
    also says "fact table" or "dimension" is handing over the modelling decision
    in prose rather than measuring whether the model makes it. The D10
    descriptions avoid this; the check is stated here because the new ones were
    written by hand and the temptation is real.
    """
    _, description, _, _, _ = CELLS[cell_id]
    banned = ["fact table", "dimension table", "star schema", "surrogate key"]
    found = [term for term in banned if term in description.lower()]
    assert not found, f"{cell_id} names its own modelling constructs: {found}"


def test_the_design_is_a_complete_two_by_two() -> None:
    """All four combinations exist, exactly once each.

    A missing or duplicated cell makes the factors inseparable, which is the one
    thing this experiment is for.
    """
    combinations = [(size, domain) for _, _, size, domain, _ in CELLS.values()]
    assert sorted(combinations) == [
        ("large", "commodity"),
        ("large", "specialised"),
        ("small", "commodity"),
        ("small", "specialised"),
    ]


def test_the_size_factor_is_actually_manipulated() -> None:
    """Every large cell targets at least twice the entities of every small one.

    The precondition without which "size" is not a variable. Targets are design
    intent rather than a scoring reference — nothing grades a candidate against
    them — but if they do not separate, neither will the cells.
    """
    small = [t for _, _, size, _, t in CELLS.values() if size == "small"]
    large = [t for _, _, size, _, t in CELLS.values() if size == "large"]
    assert min(large) >= 2 * max(small), (
        f"large targets {sorted(large)} do not clearly exceed small {sorted(small)}"
    )


def test_the_domain_factor_is_actually_manipulated() -> None:
    """The specialised cells carry regulatory vocabulary; the commodity ones do not.

    Guards the failure that would quietly ruin the design: writing the small
    specialised cell as a simplified caricature, which confounds "small" with
    "easy" and leaves the contrast measuring difficulty rather than domain.
    Both specialised cells have to read as real financial-crime work.
    """
    jargon = ("launder", "sanction", "politically exposed", "financial crime")
    for cell_id, (_, description, _, domain, _) in CELLS.items():
        hits = [term for term in jargon if term in description.lower()]
        if domain == "specialised":
            assert hits, f"{cell_id} is labelled specialised but reads as generic"
        else:
            assert not hits, f"{cell_id} is labelled commodity but carries {hits}"


def test_the_reused_cells_are_reused_and_not_rewritten() -> None:
    """The two existing cells must be the descriptions already measured.

    Copying them and editing "slightly" would mean the D10 numbers and these are
    not comparable, while looking as though they were.
    """
    from scripts.conformance_prompts import DESCRIPTIONS

    for cell_id in ("ecommerce-orders", "aml-financial-crime"):
        assert CELLS[cell_id][1] is DESCRIPTIONS[cell_id], (
            f"{cell_id} is a copy rather than the D10 description itself"
        )
