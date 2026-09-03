"""The conformance metric must still be able to say no (D10).

**Why this file exists, stated plainly, because it is a correction.** The entity
metric has been changed three times — name equality to vocabulary overlap
(`8c54a71`), Jaccard to overlap coefficient (`55afaaf`), then a forced
assignment and an excluded axis (`6752c1e`). Every one was defensible. Every one
was diagnosed from the same direction: a *good* model scoring *low*. Not one was
checked against a known-bad model that must still score low.

A change set examined only where the score was too low raises the score by
construction, whether or not it improves validity. That is regressional
Goodhart, and it means the three monotonic rises are not evidence of three good
fixes — they are what that selection process produces either way. The protection
`conformance_threshold` used to rely on (no preserved candidates, so nothing to
fit against) is gone now that the runner persists them.

So: deliberately damaged models, and the metric must keep scoring them low. The
established form is a contrast set (Gardner et al., Findings of EMNLP 2020) —
author-written minimal perturbations, not model-in-the-loop filtering, which
Bowman & Dahl (NAACL 2021) argue creates the wrong incentive.

**Every assertion here is relational, not a magic number.** A mutant must score
below identity; more damage must score no higher than less damage; a rename must
not move the entity axis. A relation cannot be satisfied by editing the gold
graph or by loosening a floor, which is precisely the failure mode this guards.

Run these against any future metric change *before* looking at what it does to
`docs/marketing/`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.schemas.data_model import SynthesizedModel
from scripts.conformance_scoring import entity_scores
from scripts.conformance_threshold import MIN_ENTITY_F1

GOLD = Path(__file__).resolve().parent / "fixtures" / "gold"

# Graphs with enough entities to damage in more than one way. A one-table OBT
# has no entity axis to test (both sides carry one entity, so it is excluded)
# and nothing to drop.
MULTI_ENTITY = ["saas-subscription", "ecommerce-orders", "banking-datavault", "aml-financial-crime"]


def _gold(name: str) -> SynthesizedModel:
    raw = json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))
    return SynthesizedModel(
        paradigm=raw["paradigm"],
        entities=raw["entities"],
        relationships=raw["relationships"],
    )


def _without(model: SynthesizedModel, names: set[str]) -> SynthesizedModel:
    """Drop entities and every relationship that referenced them."""
    clone = copy.deepcopy(model)
    clone.entities = [e for e in clone.entities if e.entity_name not in names]
    clone.relationships = [
        r
        for r in clone.relationships
        if r.from_ref.split(".")[0] not in names and r.to_ref.split(".")[0] not in names
    ]
    return clone


def drop_entities(model: SynthesizedModel, count: int) -> SynthesizedModel:
    return _without(model, {e.entity_name for e in model.entities[-count:]})


def merge_two_entities(model: SynthesizedModel) -> SynthesizedModel:
    """Fold the second table's columns into the first and delete it.

    The realistic version of "the model collapsed two concepts", which is a
    modelling error the entity axis exists to catch.
    """
    clone = copy.deepcopy(model)
    victim = clone.entities[1]
    present = {c.name for c in clone.entities[0].columns}
    clone.entities[0].columns.extend(c for c in victim.columns if c.name not in present)
    return _without(clone, {victim.entity_name})


def drop_half_the_columns(model: SynthesizedModel) -> SynthesizedModel:
    clone = copy.deepcopy(model)
    for entity in clone.entities:
        entity.columns = entity.columns[: max(1, len(entity.columns) // 2)]
    return clone


def flip_every_cardinality(model: SynthesizedModel) -> SynthesizedModel:
    clone = copy.deepcopy(model)
    flip = {"N:1": "1:N", "1:N": "N:1", "1:1": "N:1", "N:M": "1:1"}
    for relationship in clone.relationships:
        relationship.cardinality = flip.get(  # type: ignore[assignment]
            relationship.cardinality, relationship.cardinality
        )
    return clone


def rename_every_table(model: SynthesizedModel) -> SynthesizedModel:
    """The **other** positive control, and the one that catches a regression.

    Added after this suite failed to notice a mutation that reverted the matcher
    to name equality — `rename_surrogate_keys` changes only column names, so a
    name-equality matcher still pairs the tables and the suite stayed green
    while the metric had lost its central property. A negative-control suite
    that cannot detect the defect the metric was built to fix is exactly the
    test that goes green for the wrong reason.
    """
    clone = copy.deepcopy(model)
    mapping = {e.entity_name: f"tbl_{e.entity_name}" for e in clone.entities}
    for entity in clone.entities:
        entity.entity_name = mapping[entity.entity_name]
    for relationship in clone.relationships:
        for attribute in ("from_ref", "to_ref"):
            table, _, column = getattr(relationship, attribute).partition(".")
            setattr(relationship, attribute, f"{mapping.get(table, table)}.{column}")
    return clone


def rename_surrogate_keys(model: SynthesizedModel) -> SynthesizedModel:
    """The **positive** control: a naming convention, not a modelling error.

    `_sk` and `_key` are the same idea spelled two ways. A candidate that
    chooses the other spelling has not got anything wrong about the tables, and
    this is the exact substitution that sinks `saas-subscription` in the real
    run.
    """
    clone = copy.deepcopy(model)
    for entity in clone.entities:
        for column in entity.columns:
            column.name = column.name.replace("_sk", "_key")
    return clone


# ---------------------------------------------------------------------------
# The positive control
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("graph", MULTI_ENTITY)
def test_a_naming_convention_does_not_cost_a_table(graph: str) -> None:
    """Renaming surrogate keys must leave the entity axis untouched.

    An invariance test in CheckList's sense: it asserts that a change which
    should not matter does not matter. It says nothing about the column axis,
    which `test_renamed_columns_still_cost` deliberately holds the other way —
    renamed columns should cost, once, on the axis that measures columns.
    """
    gold = _gold(graph)
    entity, _, relationship = entity_scores(gold, rename_surrogate_keys(gold))
    assert entity == 1.0, "a spelling choice cost the model its tables"
    assert relationship == 1.0


@pytest.mark.parametrize("graph", MULTI_ENTITY)
def test_renaming_every_table_does_not_change_the_entity_score(graph: str) -> None:
    """The metric's central property, restated where a change will be run.

    This is the defect the whole rewrite existed to fix — a structurally
    identical model under different table names must score as correct. It is
    here rather than only in `test_conformance_metric` because a mutation
    reverting the matcher to name equality left this suite entirely green until
    this test was added.
    """
    gold = _gold(graph)
    entity, column, relationship = entity_scores(gold, rename_every_table(gold))
    assert entity == 1.0, "renaming tables cost the model its tables"
    assert column == 1.0, "renaming tables leaked into the column axis"
    assert relationship == 1.0


# ---------------------------------------------------------------------------
# The negative controls
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("graph", MULTI_ENTITY)
def test_deleting_tables_costs_entity_score(graph: str) -> None:
    """Directional: fewer tables must score lower, and more loss lower still."""
    gold = _gold(graph)
    one, _, _ = entity_scores(gold, drop_entities(gold, 1))
    two, _, _ = entity_scores(gold, drop_entities(gold, 2))
    assert one is not None and two is not None
    assert one < 1.0, "dropping a table did not cost anything"
    assert two < one, "dropping two tables scored no worse than dropping one"


@pytest.mark.parametrize("graph", MULTI_ENTITY)
def test_collapsing_two_concepts_costs_entity_score(graph: str) -> None:
    gold = _gold(graph)
    entity, _, _ = entity_scores(gold, merge_two_entities(gold))
    assert entity is not None and entity < 1.0


@pytest.mark.parametrize("graph", MULTI_ENTITY)
def test_deleting_columns_costs_column_score(graph: str) -> None:
    gold = _gold(graph)
    _, column, _ = entity_scores(gold, drop_half_the_columns(gold))
    assert column is not None and column < 1.0


@pytest.mark.parametrize("graph", MULTI_ENTITY)
def test_reversing_every_cardinality_costs_relationship_score(graph: str) -> None:
    """And costs *only* that.

    Two claims in one, and the second is the more useful. Reversing a Fact ->
    Dimension edge is a real modelling error and must show up. It must also not
    leak into the entity or column axes, because an axis that moves when
    something unrelated changes cannot be attributed.
    """
    gold = _gold(graph)
    entity, column, relationship = entity_scores(gold, flip_every_cardinality(gold))
    assert relationship is not None and relationship < 1.0
    assert entity == 1.0, "reversing an edge changed the entity axis"
    assert column == 1.0, "reversing an edge changed the column axis"


def test_a_different_domain_still_scores_low() -> None:
    """The property that makes a passing score mean anything.

    Duplicated from `test_conformance_metric` on purpose: that file is where the
    metric's *features* are tested, and this is the file a future change is
    supposed to be run against. A guard that lives only beside the thing it
    guards is easy to move.
    """
    entity, column, _ = entity_scores(_gold("saas-subscription"), _gold("healthcare-ehr"))
    assert entity is not None and entity < 0.34
    assert column is not None and column < 0.2


# ---------------------------------------------------------------------------
# What the suite found on its first run
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Open: F1 is insensitive to deletion on large graphs. Dropping 2 of 12 "
        "entities scores 0.909, clearing MIN_ENTITY_F1. Needs a floor that "
        "scales, or a separate recall gate."
    ),
)
def test_losing_a_sixth_of_a_large_model_should_not_clear_the_gate() -> None:
    """The first thing this suite caught, and it is a real gap.

    Deleting two tables from the twelve-entity AML model scores entity F1 0.909
    against a 0.80 threshold — a model missing a sixth of itself passes the
    entity gate comfortably. On a three-entity graph the same proportional loss
    scores 0.500 and fails, so the gate's real strictness depends on graph size,
    which nothing about the threshold says.

    This is the F1 counterpart of the lint instrument's raw-count problem
    (`GraphScore.lint_delta_per_entity`): both get more forgiving as the model
    gets bigger, and both were read as though they did not.

    Left failing rather than fixed. Changing `MIN_ENTITY_F1` or making it scale
    is a threshold change, and this suite exists precisely so that the next such
    change is argued rather than fitted.
    """
    gold = _gold("aml-financial-crime")
    entity, _, _ = entity_scores(gold, drop_entities(gold, 2))
    assert entity is not None
    assert entity < MIN_ENTITY_F1, (
        f"a model missing 2 of {len(gold.entities)} tables scored {entity:.3f}, "
        f"clearing the {MIN_ENTITY_F1} gate"
    )
