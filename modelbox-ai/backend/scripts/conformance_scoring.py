"""Scoring for the provider conformance harness (D10).

Pure functions, deliberately. Every judgement this harness makes is computed
here, and nothing here can contact a provider — so the whole grading path is
testable offline, and the only thing the environment supplies is the candidate
model itself. The thresholds it is read against were fixed first, in
``conformance_threshold.py``, in a commit that predates any code able to call
out.

Comparisons canonicalise names — lowercase, underscores stripped — because a
provider writing ``DimCustomer`` where the gold graph writes ``dim_customer``
has produced the same entity. Penalising that would measure naming convention
and report it as schema quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.data_model import SynthesizedModel
from app.services.graph_engine import GraphEngine
from scripts.conformance_threshold import (
    CONCENTRATION_SHARE,
    ENTITY_MATCH_FLOOR,
    MAX_LINT_DELTA_PER_GRAPH,
    MIN_COLUMN_F1,
    MIN_ENTITY_F1,
    MIN_RELATIONSHIP_F1,
    NEW_CODE_GRAPH_COUNT,
    REQUIRED_PROVENANCE,
)


def canon(name: str) -> str:
    return name.replace("_", "").replace(" ", "").lower()


def f1(expected: set, actual: set) -> float | None:
    """Harmonic mean of precision and recall, or ``None`` where inapplicable.

    F1 rather than recall: recall alone rewards a provider that emits every
    plausible entity and lets precision collapse, and over-generation is the
    expected failure mode of a model asked for a warehouse schema.

    **Two empty sets return ``None``, not 1.0.** The old value was defended as
    "nothing was required and nothing was invented", which is true of a single
    graph and false of an average. `marketing-attribution` is an OBT model with
    no relationships, so both sides were empty and it scored relationship F1
    1.000 — a free top mark for measuring nothing, averaged in beside graphs
    that were actually judged, on the same run where its entity F1 was 0.000.
    An axis that does not apply to a graph is excluded from that axis's mean;
    `_mean` skips `None` and `verdict` refuses an axis with nothing to judge.
    """
    if not expected and not actual:
        return None
    hits = len(expected & actual)
    if not hits:
        return 0.0
    precision = hits / len(actual)
    recall = hits / len(expected)
    return 2 * precision * recall / (precision + recall)


def _entity_columns(entity) -> set[str]:
    return {canon(c.name) for c in entity.columns}


def entity_similarity(gold_entity, candidate_entity) -> float:
    """How much two entities look like the same table, ignoring their names.

    **Overlap, not Jaccard, and the reason is a measured defect rather than a
    preference.** Jaccard divides by the union, so a candidate that produces the
    right table and adds columns is penalised for the additions. Measured on the
    gold graphs, `dim_customer` against a candidate's own `dim_customer` — the
    same table, the same name, unarguably the same thing — scored **0.200**,
    below the 0.50 floor. A similarity function that scores an identical table
    at 0.2 is miscalibrated on its own terms, whatever any provider run says,
    and that is the ground for changing it.

    Overlap asks the question the matcher actually has — *is this the same
    table* — rather than *are these the same size*. The elaboration a modeller
    adds is not evidence against identity. Measured effect on the 2026-09-02
    candidates: `fact_order_line` against a candidate's `fact_sales`, the same
    fact under another name, moves from 0.231 to 0.500 and is recognised.

    **A foreign-key-structure signal was written and removed.** The idea is
    sound — two facts joining to the same dimensions are the same fact — and on
    all twelve captured candidate graphs it changed **no score at all**, because
    a model that renames a fact renames the dimensions with it, so the targets
    disagree exactly when the vocabulary does. Keeping it would have been
    unexercised complexity that reads as rigour. It belongs here the day a
    fixture demonstrates it deciding something.

    Entity *type* remains deliberately excluded. FACT/DIMENSION is a label the
    paradigm assigns, and a provider that builds the right table and labels it
    wrong should lose points for the label — which it does, through the linter
    codes — rather than have the table itself go unrecognised.

    **The honest limit.** Every signal here is derived from names one level
    down, so a candidate that renames entities *and* columns consistently cannot
    be recognised at all. `saas-subscription` is exactly that case: the
    candidate's `fact_subscription_snapshot` / `dim_organisation` / `dim_tier`
    share zero column names with gold's `fact_subscription_monthly` /
    `dim_customer` / `dim_plan`, and score 0.000 while being a defensible model
    of the same warehouse. Closing that needs embedding similarity with optimal
    assignment, which is a dependency and a decision, not a tweak.
    """
    gold_columns = _entity_columns(gold_entity)
    candidate_columns = _entity_columns(candidate_entity)
    if not gold_columns or not candidate_columns:
        return 0.0
    shared = len(gold_columns & candidate_columns)
    return shared / min(len(gold_columns), len(candidate_columns))


def match_entities(gold: SynthesizedModel, candidate: SynthesizedModel) -> dict[str, str]:
    """Pair gold entities with candidate entities by content, not by name.

    Returns ``{canonical gold name: canonical candidate name}`` for pairs above
    ``ENTITY_MATCH_FLOOR``. Each entity is used at most once.

    **This is the defect the first run exposed.** Scoring by name equality gave
    `ecommerce-orders` 0.857 and `saas-subscription` 0.000 for the same model on
    two near-identical Kimball tasks — the second is not a model that failed to
    comprehend subscription warehousing, it is the same model choosing different
    words, scored as though it had produced nothing. Column F1 stayed at
    0.07-0.16 even where entity F1 was 0.857, which is the same defect one level
    down: `customer_sk` against `customer_id`.

    Greedy, highest similarity first, ties broken by name. Not optimal
    assignment: the Hungarian algorithm would need SciPy, which this harness
    does not depend on, and greedy differs from optimal only when two gold
    entities compete for one candidate at similar scores — which means the
    candidate collapsed two tables into one, and that is a real defect the score
    should reflect rather than an artefact to be optimised away. Deterministic
    tie-breaking matters more than optimality here: the same two graphs must
    always produce the same number.
    """
    pairs = [
        (entity_similarity(g, c), canon(g.entity_name), canon(c.entity_name))
        for g in gold.entities
        for c in candidate.entities
    ]
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    matched: dict[str, str] = {}
    used_candidates: set[str] = set()
    for similarity, gold_name, candidate_name in pairs:
        if similarity < ENTITY_MATCH_FLOOR:
            break
        if gold_name in matched or candidate_name in used_candidates:
            continue
        matched[gold_name] = candidate_name
        used_candidates.add(candidate_name)
    return matched


def entity_set(model: SynthesizedModel) -> set[str]:
    return {canon(e.entity_name) for e in model.entities}


def column_set(model: SynthesizedModel) -> set[tuple[str, str]]:
    return {
        (canon(e.entity_name), canon(c.name))
        for e in model.entities
        for c in e.columns
    }


def _entity_of(ref: str) -> str:
    """The entity half of a `entity.column` reference.

    Relationships are compared entity-to-entity rather than column-to-column:
    the question this harness asks is whether the provider built the same star,
    and whether it joined on `customer_sk` or `customer_id` is a column-naming
    difference already counted once on the column axis. Counting it again here
    would make one disagreement fail two axes.
    """
    return canon(ref.split(".", 1)[0])


def relationship_set(model: SynthesizedModel) -> set[tuple[str, str, str]]:
    return {
        (_entity_of(r.from_ref), _entity_of(r.to_ref), str(r.cardinality))
        for r in model.relationships
    }


def entity_scores(
    gold: SynthesizedModel, candidate: SynthesizedModel
) -> tuple[float | None, float | None, float | None]:
    """Entity, column and relationship F1 computed through a content matching.

    Every axis is scored in the *gold* namespace: candidate entities are
    renamed to their matched gold counterparts first, so a structurally correct
    schema under different names scores as correct. An unmatched candidate
    entity keeps its own name and therefore counts against precision, which is
    the right treatment — it is a table the gold model does not have.
    """
    matching = match_entities(gold, candidate)
    rename = {c: g for g, c in matching.items()}

    def as_gold(name: str) -> str:
        return rename.get(name, name)

    gold_entities = entity_set(gold)
    candidate_entities = {as_gold(canon(e.entity_name)) for e in candidate.entities}

    gold_columns = column_set(gold)
    candidate_columns = {
        (as_gold(canon(e.entity_name)), canon(c.name))
        for e in candidate.entities
        for c in e.columns
    }

    gold_relationships = relationship_set(gold)
    candidate_relationships = {
        (as_gold(a), as_gold(b), cardinality)
        for a, b, cardinality in relationship_set(candidate)
    }

    return (
        f1(gold_entities, candidate_entities),
        f1(gold_columns, candidate_columns),
        f1(gold_relationships, candidate_relationships),
    )


def lint_codes(model: SynthesizedModel) -> list[str]:
    """Linter findings by code — the same instrument the Trainer grades with.

    Verified before it was allowed to carry this: Task 0 showed all thirteen
    codes fire on a graph that must trigger them and stay silent on a
    near-identical graph that must not.
    """
    report = GraphEngine().validate(model.entities, model.relationships)
    return sorted(issue.code for issue in report.issues)


@dataclass(frozen=True)
class GraphScore:
    """One provider's attempt at one gold graph, with its provenance."""

    gold_graph_id: str
    provider: str
    egress_class: str
    model_identifier: str
    model_version: str
    prompt_sha256: str
    run_started_at: str
    entity_f1: float | None
    column_f1: float | None
    relationship_f1: float | None
    gold_codes: list[str] = field(default_factory=list)
    candidate_codes: list[str] = field(default_factory=list)

    @property
    def lint_delta(self) -> int:
        return len(self.candidate_codes) - len(self.gold_codes)

    @property
    def new_codes(self) -> set[str]:
        return set(self.candidate_codes) - set(self.gold_codes)

    def provenance_gaps(self) -> list[str]:
        """Missing provenance makes a score invalid, not partial.

        A quality verdict is a statement about a specific model at a specific
        version. Without that it is unreproducible, and an unreproducible number
        behind a public claim is what the Proof Log exists to prevent.
        """
        return [
            key
            for key in REQUIRED_PROVENANCE
            if not str(getattr(self, key, "") or "").strip()
        ]


def score_graph(
    *,
    gold_graph_id: str,
    gold: SynthesizedModel,
    candidate: SynthesizedModel,
    provider: str,
    egress_class: str,
    model_identifier: str,
    model_version: str,
    prompt_sha256: str,
    run_started_at: str,
) -> GraphScore:
    entity, column, relationship = entity_scores(gold, candidate)
    return GraphScore(
        gold_graph_id=gold_graph_id,
        provider=provider,
        egress_class=egress_class,
        model_identifier=model_identifier,
        model_version=model_version,
        prompt_sha256=prompt_sha256,
        run_started_at=run_started_at,
        entity_f1=entity,
        column_f1=column,
        relationship_f1=relationship,
        gold_codes=lint_codes(gold),
        candidate_codes=lint_codes(candidate),
    )


@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    egress_class: str
    model_identifier: str
    model_version: str
    entity_f1: float | None
    column_f1: float | None
    relationship_f1: float | None
    lint_delta: float
    systematic_new_codes: list[str]
    failures: list[str]
    remedy: str

    @property
    def passed(self) -> bool:
        return not self.failures


def _mean(values: list[float | None]) -> float | None:
    """Mean of the applicable scores, or ``None`` if none apply.

    Skipping `None` rather than treating it as zero: a graph with no
    relationships has not scored badly on relationships, it has not been asked
    about them. Counting that as 0.0 would be the mirror of the 1.0 defect —
    both invent a judgement where none was made.
    """
    applicable = [value for value in values if value is not None]
    if not applicable:
        return None
    return sum(applicable) / len(applicable)


def verdict(scores: list[GraphScore]) -> ProviderVerdict:
    """Apply the fixed thresholds. No number in this function is chosen here."""
    if not scores:
        raise ValueError("no scores to judge")
    invalid = {s.gold_graph_id: s.provenance_gaps() for s in scores}
    invalid = {k: v for k, v in invalid.items() if v}
    if invalid:
        raise ValueError(f"scores missing required provenance: {invalid}")

    entity = _mean([s.entity_f1 for s in scores])
    column = _mean([s.column_f1 for s in scores])
    relationship = _mean([s.relationship_f1 for s in scores])
    delta = _mean([float(s.lint_delta) for s in scores])

    counts: dict[str, int] = {}
    for score in scores:
        for code in score.new_codes:
            counts[code] = counts.get(code, 0) + 1
    systematic = sorted(c for c, n in counts.items() if n >= NEW_CODE_GRAPH_COUNT)

    failures: list[str] = []
    # An axis with nothing to judge fails rather than passing quietly. A run
    # where no graph exercised relationships has not demonstrated that the
    # provider can build them, and "no evidence" must not read as "met" — the
    # same standard-12 shape as the empty-set F1 this replaced.
    for name, value in (
        ("entity", entity),
        ("column", column),
        ("relationship", relationship),
    ):
        if value is None:
            failures.append(f"{name} F1 has no applicable graph in this run")
    if entity is not None and entity < MIN_ENTITY_F1:
        failures.append(f"entity F1 {entity:.3f} < {MIN_ENTITY_F1}")
    if column is not None and column < MIN_COLUMN_F1:
        failures.append(f"column F1 {column:.3f} < {MIN_COLUMN_F1}")
    if relationship is not None and relationship < MIN_RELATIONSHIP_F1:
        failures.append(f"relationship F1 {relationship:.3f} < {MIN_RELATIONSHIP_F1}")
    if delta > MAX_LINT_DELTA_PER_GRAPH:
        failures.append(f"lint delta +{delta:.2f} > +{MAX_LINT_DELTA_PER_GRAPH}")
    if systematic:
        failures.append(f"new lint codes on >= {NEW_CODE_GRAPH_COUNT} graphs: {systematic}")

    return ProviderVerdict(
        provider=scores[0].provider,
        egress_class=scores[0].egress_class,
        model_identifier=scores[0].model_identifier,
        model_version=scores[0].model_version,
        entity_f1=entity,
        column_f1=column,
        relationship_f1=relationship,
        lint_delta=delta,
        systematic_new_codes=systematic,
        failures=failures,
        remedy=remedy_for(entity, column, relationship),
    )


def remedy_for(
    entity: float | None, column: float | None, relationship: float | None
) -> str:
    """Which remedy the *shape* of the failure indicates.

    Decided before any provider ran, because a remedy chosen after seeing a
    number is chosen to suit it. "Concentrated" is numeric for the same reason:
    otherwise the question is settled by whoever wants which conclusion.

    An axis with no applicable graph indicates no remedy, because it made no
    measurement. Treating it as a zero shortfall would let an unmeasured axis
    argue for a fix, and treating it as a full one would let it dominate.
    """
    if entity is None or column is None or relationship is None:
        return (
            "no remedy indicated — at least one axis had no applicable graph, "
            "so the shape of the failure is not established"
        )
    shortfalls = {
        "entity": max(0.0, MIN_ENTITY_F1 - entity),
        "column": max(0.0, MIN_COLUMN_F1 - column),
        "relationship": max(0.0, MIN_RELATIONSHIP_F1 - relationship),
    }
    total = sum(shortfalls.values())
    if total == 0:
        return "none — all axes within threshold"
    if shortfalls["relationship"] / total >= CONCENTRATION_SHARE:
        return (
            "staged synthesis indicated — degradation is concentrated in "
            f"relationships ({shortfalls['relationship'] / total:.0%} of total "
            "shortfall): synthesise entities first, then relationships with the "
            "entity set fixed"
        )
    return (
        "narrow the air-gap claim — degradation is spread across axes "
        f"({ {k: round(v, 3) for k, v in shortfalls.items()} }), so no fix at "
        "the synthesis layer is indicated"
    )


__all__ = [
    "GraphScore",
    "ProviderVerdict",
    "canon",
    "column_set",
    "entity_set",
    "f1",
    "lint_codes",
    "relationship_set",
    "remedy_for",
    "score_graph",
    "verdict",
]
