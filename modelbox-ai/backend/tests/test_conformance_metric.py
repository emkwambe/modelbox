"""The conformance metric measures structure, not vocabulary (D10).

The first real run scored `ecommerce-orders` at entity F1 0.857 and
`saas-subscription` at 0.000 — the same cloud model, two near-identical Kimball
tasks. A model does not comprehend e-commerce warehousing and then fail
*completely* on subscription warehousing. Those two numbers are one model naming
things differently, scored as though it had produced nothing, and column F1 sat
at 0.07-0.16 even where entity F1 was 0.857 (`customer_sk` against
`customer_id`, one level down).

So the axes are now computed through a content matching: entities are paired by
how much of their column vocabulary coincides, candidates are renamed into the
gold namespace, and the comparison happens there.

**A metric that was loosened needs its failure cases pinned harder than its
success cases**, because the way to make a bad score go away is to stop
measuring. Every test below that shows the metric forgiving a difference is
paired with one showing it still catching a real one:

    rename-invariance          vs  a genuinely different schema scores low
    matched entities score 1.0 vs  renamed *columns* still cost
    an OBT graph is excluded    vs  an unjudged axis fails the verdict

None of these fixtures came from a provider. They are constructed graphs with
known answers, so the metric is pinned by what it *should* say rather than
against a run whose result someone might prefer.

**Mutation results, 2026-08-28.** Both directions were run, because a metric
has two ways to be wrong and each needs its own killer:

- `match_entities` returning `{}` — the old name-equality metric exactly — fails
  `test_renaming_every_table_does_not_change_the_score` with 0.0, reproducing
  the reported defect on a graph that is structurally identical to gold.
- Dropping the match floor to 0.0 so every pair matches fails
  `test_a_different_schema_scores_low`: a SaaS subscription warehouse scores
  0.857 against a healthcare EHR schema. That is the failure mode of a metric
  loosened until it cannot fail, and it is the reason the floor is a threshold
  rather than a convenience.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.schemas.data_model import SynthesizedModel
from scripts.conformance_scoring import (
    GraphScore,
    canon,
    entity_scores,
    entity_similarity,
    f1,
    match_entities,
    verdict,
)

GOLD = Path(__file__).resolve().parent / "fixtures" / "gold"

# Derived, never listed.
#
# This was a four-name literal, and it had already stopped being exhaustive
# before anyone noticed: `marketing-attribution` was never in it, and
# `aml-financial-crime` (e0beb47) did not join it. The identity check — the one
# that proves the metric can recognise a graph as itself — was covering four of
# six graphs and reporting green, which is standard 8's shape in the guard for
# the instrument rather than in the instrument.
#
# `index.json` is the catalogue, not a graph.
GOLD_IDS = sorted(path.stem for path in GOLD.glob("*.json") if path.stem != "index")


def _gold(name: str) -> SynthesizedModel:
    raw = json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))
    return SynthesizedModel(
        paradigm=raw["paradigm"],
        entities=raw["entities"],
        relationships=raw["relationships"],
    )


def _rename_entities(model: SynthesizedModel, mapping: dict[str, str]) -> SynthesizedModel:
    """A structurally identical model with different table names."""
    clone = copy.deepcopy(model)
    for entity in clone.entities:
        entity.entity_name = mapping.get(entity.entity_name, entity.entity_name)
    for relationship in clone.relationships:
        for attribute in ("from_ref", "to_ref"):
            ref = getattr(relationship, attribute)
            table, _, column = ref.partition(".")
            setattr(relationship, attribute, f"{mapping.get(table, table)}.{column}")
    return clone


# ---------------------------------------------------------------------------
# Identity and rename-invariance — what the fix is for
# ---------------------------------------------------------------------------
def test_the_identity_check_covers_every_gold_graph() -> None:
    """Precondition. A glob that returned nothing would parametrise to no cases.

    An empty or shrunken `GOLD_IDS` makes every test below vacuous while the run
    stays green — the exact failure the literal list produced, arriving by a
    different route. Asserting the floor rather than an exact count keeps this
    from becoming the next number that needs editing when a graph lands.
    """
    assert len(GOLD_IDS) >= 6, f"gold fixtures did not resolve: {GOLD_IDS}"


@pytest.mark.parametrize("graph", GOLD_IDS)
def test_a_graph_scores_perfectly_against_itself(graph: str) -> None:
    """Fixture sanity. A metric that cannot recognise identity measures nothing.

    The relationship axis is `None` — not 1.0 — for a graph that declares no
    relationships, which is the empty-set fix this metric was rewritten to make:
    an axis with nothing to judge is excluded from its mean rather than handed a
    free top mark. `marketing-attribution` is that graph, a single-table OBT
    model, and it is the reason this test previously ran on a hand-written list.

    Dropping the whole graph to avoid one inapplicable axis also dropped its
    entity and column identity checks, which apply perfectly well. The axis is
    what is inapplicable, not the graph.
    """
    gold = _gold(graph)
    entity, column, relationship = entity_scores(gold, _gold(graph))
    # A one-table model against itself excludes the entity axis for the same
    # reason it excludes the relationship axis: with one table on each side the
    # axis cannot separate a good answer from a bad one, so 1.0 there would be
    # awarded rather than earned. The column axis still applies and still has to
    # be 1.0 — which is what keeps this an identity check for that graph.
    assert entity == (None if len(gold.entities) == 1 else 1.0)
    assert column == 1.0
    assert relationship == (1.0 if gold.relationships else None)


def test_at_least_one_gold_graph_exercises_each_branch_of_that_rule() -> None:
    """The discriminating half: a rule with only one branch taken proves nothing.

    If every gold graph had relationships, the `None` arm above would never run
    and the assertion would be indistinguishable from `== 1.0`. If none did, the
    reverse. Both arms must be reachable from the fixtures for the test to mean
    what it says.
    """
    with_edges = [gid for gid in GOLD_IDS if _gold(gid).relationships]
    without_edges = [gid for gid in GOLD_IDS if not _gold(gid).relationships]
    assert with_edges, "no gold graph declares relationships"
    assert without_edges, "no gold graph exercises the inapplicable-axis arm"


def test_renaming_every_table_does_not_change_the_score() -> None:
    """The reported defect, in its pure form.

    Identical columns, identical relationships, different table names. Under
    name equality this scored 0.0 on entities and relationships alike; it is the
    same warehouse and must score as one.
    """
    gold = _gold("saas-subscription")
    renamed = _rename_entities(
        gold,
        {
            "dim_customer": "customers",
            "dim_plan": "plans",
            "fact_subscription_monthly": "monthly_subscription_facts",
        },
    )
    entity, column, relationship = entity_scores(gold, renamed)
    assert entity == 1.0, "renaming tables must not change the structure score"
    assert column == 1.0
    assert relationship == 1.0


def test_the_old_metric_would_have_failed_this_case() -> None:
    """Names the difference explicitly, so the fix cannot be quietly reverted.

    Set equality over canonicalised entity names — the previous implementation —
    finds nothing in common here. Any future rewrite that scores 0.0 on the
    graphs above has reintroduced exactly that.
    """
    gold = _gold("saas-subscription")
    renamed = _rename_entities(gold, {"dim_customer": "customers"})
    gold_names = {e.entity_name for e in gold.entities}
    renamed_names = {e.entity_name for e in renamed.entities}
    assert gold_names != renamed_names
    assert "customers" not in gold_names


# ---------------------------------------------------------------------------
# Still able to fail — the half that matters more
# ---------------------------------------------------------------------------
def test_a_different_schema_scores_low() -> None:
    """Rename-invariance must not become everything-matches.

    Two graphs from different domains share almost no column vocabulary, so
    nothing clears the match floor and the score collapses — which is the
    correct answer, and the property that makes a passing score mean anything.
    """
    entity, column, _relationship = entity_scores(
        _gold("saas-subscription"), _gold("healthcare-ehr")
    )
    assert entity is not None and entity < 0.34
    assert column is not None and column < 0.2


def test_renamed_columns_still_cost() -> None:
    """The column axis measures the thing the entity axis deliberately ignores.

    `customer_sk` against `customer_id` is a real difference in a contract, and
    forgiving table names must not forgive it. The entities still match — they
    share most of their vocabulary — but the column score drops.
    """
    gold = _gold("saas-subscription")
    mutated = copy.deepcopy(gold)
    for entity in mutated.entities:
        for column in entity.columns:
            if column.name.endswith("_sk"):
                column.name = column.name.replace("_sk", "_key")

    entity_score, column_score, _unused = entity_scores(gold, mutated)
    assert entity_score == 1.0, "the tables are still recognisably the same"
    assert column_score is not None and column_score < 1.0, (
        "renamed columns must still cost something"
    )


def test_collapsing_two_tables_into_one_is_penalised() -> None:
    """A candidate that merges tables has lost structure, not renamed it.

    Each gold entity may claim at most one candidate, so the merged table
    answers for one of them and the other goes unmatched.
    """
    gold = _gold("saas-subscription")
    merged = copy.deepcopy(gold)
    survivors = [e for e in merged.entities if e.entity_name != "dim_plan"]
    plan = next(e for e in merged.entities if e.entity_name == "dim_plan")
    customer = next(e for e in survivors if e.entity_name == "dim_customer")
    existing = {c.name for c in customer.columns}
    customer.columns.extend(c for c in plan.columns if c.name not in existing)
    merged.entities = survivors
    merged.relationships = [
        r
        for r in merged.relationships
        if "dim_plan" not in r.from_ref and "dim_plan" not in r.to_ref
    ]

    entity_score, _, _ = entity_scores(gold, merged)
    assert entity_score is not None and entity_score < 1.0


def test_similarity_ignores_the_entity_name_entirely() -> None:
    """The matching function must not read the name it is meant to look past."""
    gold = _gold("saas-subscription")
    original = next(e for e in gold.entities if e.entity_name == "dim_customer")
    renamed = copy.deepcopy(original)
    renamed.entity_name = "something_completely_different"
    assert entity_similarity(original, renamed) == 1.0


# ---------------------------------------------------------------------------
# The empty-set defect
# ---------------------------------------------------------------------------
def test_two_empty_sets_are_not_a_perfect_score() -> None:
    """`marketing-attribution` scored relationship F1 1.000 with entity F1 0.000.

    It is an OBT graph with no relationships, so both sides were empty. A free
    top mark for measuring nothing, averaged in beside graphs that were actually
    judged.
    """
    assert f1(set(), set()) is None
    assert f1({"a"}, set()) == 0.0
    assert f1(set(), {"a"}) == 0.0


def test_an_obt_graph_reports_no_relationship_score() -> None:
    gold = _gold("marketing-attribution")
    assert not gold.relationships, "fixture no longer exercises the empty case"
    _, _, relationship = entity_scores(gold, gold)
    assert relationship is None


def _score(**overrides) -> GraphScore:
    base = {
        "gold_graph_id": "g",
        "provider": "p",
        "egress_class": "cloud",
        "model_identifier": "m",
        "model_version": "v",
        "prompt_sha256": "abc",
        "run_started_at": "2026-08-28T00:00:00Z",
        "entity_f1": 0.9,
        "column_f1": 0.8,
        "relationship_f1": 0.7,
    }
    base.update(overrides)
    return GraphScore(**base)


def test_an_inapplicable_axis_is_excluded_from_its_mean() -> None:
    """Not averaged as 1.0, and not as 0.0 either — simply not counted."""
    result = verdict([_score(relationship_f1=None), _score(relationship_f1=0.7)])
    assert result.relationship_f1 == pytest.approx(0.7)


def test_an_axis_with_nothing_to_judge_fails_rather_than_passes() -> None:
    """No evidence must not read as met.

    If every graph in a run left an axis inapplicable, the provider has not
    demonstrated anything about it. Returning a passing verdict there would be
    the same standard-12 shape as the 1.0 this replaced, one level up.
    """
    result = verdict([_score(relationship_f1=None), _score(relationship_f1=None)])
    assert not result.passed
    assert any("no applicable graph" in f for f in result.failures)
    assert "no remedy indicated" in result.remedy


def test_matching_is_deterministic() -> None:
    """The same two graphs must always produce the same number.

    Greedy matching over a sorted pair list, ties broken by name. Iteration
    order of a set or dict leaking into this would make a verdict depend on a
    hash seed — the failure PL-005 exists to rule out for artifacts, applied to
    the score.
    """
    gold, candidate = _gold("ecommerce-orders"), _gold("saas-subscription")
    first = match_entities(gold, candidate)
    for _ in range(5):
        assert match_entities(gold, candidate) == first


# ---------------------------------------------------------------------------
# Open defects — the two graphs that scored 0.000 in the 2026-09-03 run
# ---------------------------------------------------------------------------
# Both halves of D10 scored `saas-subscription` and `marketing-attribution` at
# entity F1 0.000, on both models. Reading the candidates settles what that is:
#
#   gold  dim_customer / dim_plan / fact_subscription_monthly
#   cand  dim_organisation / dim_tier / fact_subscription_snapshot  (+ dim_month)
#
# That candidate is a sound Kimball model of the same warehouse — arguably a
# better one, carrying SCD2 columns on both dimensions and a conformed date
# dimension. It scores zero because gold suffixes surrogate keys `_sk` and it
# chose `_key`, so the column vocabularies are disjoint and every pair falls
# under the match floor. **This is the metric failing, not the model**, and it
# is the same defect the metric was already rewritten twice to fix, surviving in
# the case where the renaming is total rather than partial.
#
# They are recorded as strict xfails rather than fixed here, deliberately.
# `conformance_threshold` names the reason: the runner now persists candidates,
# so the "accidental guarantee" that the floor could not have been fitted to a
# run is gone, and the stated principle is the only thing left holding. A third
# change to this metric, made while looking at a score it would move, has
# nothing to keep it honest. What each test asserts is a principle that can be
# argued without reference to any run's numbers — and the fix has to satisfy the
# principle, not the number.
@pytest.mark.xfail(
    strict=True,
    reason=(
        "D10 open: a total rename leaves no shared vocabulary, so nothing "
        "clears ENTITY_MATCH_FLOOR. Needs similarity that is not lexical."
    ),
)
def test_tables_are_still_paired_when_no_column_name_survives() -> None:
    """Entity pairing must survive a rename the column axis will still punish.

    The two axes answer different questions and this test is careful to claim
    only the first. *Did the model produce the right tables* is the entity axis,
    and the answer here is yes — three tables, right types, right relationships,
    every structure identical to gold. *Did it use the right column names* is
    the column axis, and the answer is no; `test_renamed_columns_still_cost`
    holds that against it deliberately, so nothing here asserts `column_f1`.

    The defect is that a total rename takes the entity axis down with the column
    axis. Pairing is inferred from shared vocabulary, so when none survives
    there is nothing left to infer from, and three correct tables are scored as
    zero tables. The column penalty is then applied a second time, as an entity
    penalty, for the same difference.

    Prefixing every column is a blunter rename than the real candidate's, which
    reworded columns individually. It is the right test case anyway: it is the
    worst case, it is unambiguous, and gold relabelled is a graph whose correct
    entity score is known without appeal to a run.
    """
    gold = _gold("saas-subscription")
    candidate = _rename_entities(
        gold,
        {
            "dim_customer": "dim_organisation",
            "dim_plan": "dim_tier",
            "fact_subscription_monthly": "fact_subscription_snapshot",
        },
    )
    for entity in candidate.entities:
        for column in entity.columns:
            column.name = f"sub_{column.name}"

    entity_f1, _, _ = entity_scores(gold, candidate)
    assert entity_f1 == 1.0


def test_the_only_entity_on_each_side_is_paired() -> None:
    """A degenerate assignment, failed for a similarity reason.

    `marketing-attribution` is a One Big Table: gold has one entity, the
    candidate has one entity, and they are the same table under different words
    (`obt_touchpoints` / `obt_marketing_interactions`). There is exactly one
    possible pairing, so no similarity judgement arises — yet the floor rejects
    it and the entity axis reports 0.000.

    Pairing them is not charity. It moves the question to the column axis, which
    is where the difference between a good OBT and a bad one actually lives; the
    real candidate carries 35 columns against gold's 9 and will be scored on
    that. Refusing the pair scores the model as having produced no table at all,
    when it produced exactly one, of the right type, for the right domain.
    """
    gold = _gold("marketing-attribution")
    candidate = _rename_entities(gold, {"obt_touchpoints": "obt_marketing_interactions"})
    for column in candidate.entities[0].columns:
        column.name = f"mkt_{column.name}"

    assert match_entities(gold, candidate) == {
        canon("obt_touchpoints"): canon("obt_marketing_interactions")
    }
