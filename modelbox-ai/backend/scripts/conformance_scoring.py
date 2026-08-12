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
    MAX_LINT_DELTA_PER_GRAPH,
    MIN_COLUMN_F1,
    MIN_ENTITY_F1,
    MIN_RELATIONSHIP_F1,
    NEW_CODE_GRAPH_COUNT,
    REQUIRED_PROVENANCE,
)


def canon(name: str) -> str:
    return name.replace("_", "").replace(" ", "").lower()


def f1(expected: set, actual: set) -> float:
    """Harmonic mean of precision and recall.

    F1 rather than recall: recall alone rewards a provider that emits every
    plausible entity and lets precision collapse, and over-generation is the
    expected failure mode of a model asked for a warehouse schema. Two empty
    sets score 1.0 — nothing was required and nothing was invented.
    """
    if not expected and not actual:
        return 1.0
    hits = len(expected & actual)
    if not hits:
        return 0.0
    precision = hits / len(actual)
    recall = hits / len(expected)
    return 2 * precision * recall / (precision + recall)


def entity_set(model: SynthesizedModel) -> set[str]:
    return {canon(e.entity_name) for e in model.entities}


def column_set(model: SynthesizedModel) -> set[tuple[str, str]]:
    return {
        (canon(e.entity_name), canon(c.name))
        for e in model.entities
        for c in e.columns
    }


def relationship_set(model: SynthesizedModel) -> set[tuple[str, str, str]]:
    return {
        (canon(r.from_ref), canon(r.to_ref), str(r.cardinality))
        for r in model.relationships
    }


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
    entity_f1: float
    column_f1: float
    relationship_f1: float
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
    return GraphScore(
        gold_graph_id=gold_graph_id,
        provider=provider,
        egress_class=egress_class,
        model_identifier=model_identifier,
        model_version=model_version,
        prompt_sha256=prompt_sha256,
        run_started_at=run_started_at,
        entity_f1=f1(entity_set(gold), entity_set(candidate)),
        column_f1=f1(column_set(gold), column_set(candidate)),
        relationship_f1=f1(relationship_set(gold), relationship_set(candidate)),
        gold_codes=lint_codes(gold),
        candidate_codes=lint_codes(candidate),
    )


@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    egress_class: str
    model_identifier: str
    model_version: str
    entity_f1: float
    column_f1: float
    relationship_f1: float
    lint_delta: float
    systematic_new_codes: list[str]
    failures: list[str]
    remedy: str

    @property
    def passed(self) -> bool:
        return not self.failures


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


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
    if entity < MIN_ENTITY_F1:
        failures.append(f"entity F1 {entity:.3f} < {MIN_ENTITY_F1}")
    if column < MIN_COLUMN_F1:
        failures.append(f"column F1 {column:.3f} < {MIN_COLUMN_F1}")
    if relationship < MIN_RELATIONSHIP_F1:
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


def remedy_for(entity: float, column: float, relationship: float) -> str:
    """Which remedy the *shape* of the failure indicates.

    Decided before any provider ran, because a remedy chosen after seeing a
    number is chosen to suit it. "Concentrated" is numeric for the same reason:
    otherwise the question is settled by whoever wants which conclusion.
    """
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
