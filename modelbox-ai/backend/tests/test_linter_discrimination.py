"""Task 0 — a discrimination test for the scorer itself.

The graph linter grades in three places: Trainer labs (H2, H3), provider
conformance (D10), and beside the cross-artifact gate. Three claims rest on one
instrument, and the instrument had never been given the test it is used to
apply. Standard 13 covers the measuring device as much as the code it measures.

`test_trainer_labs.py` asserts set-equality between a lab's expectations and the
linter's output. That proves the labs match the linter. It does not prove the
linter is right — two different claims, and only one had ever been tested.

**The negative case is the load-bearing half.** A code that fires on everything
grades every lab identically and rates every provider identically, and nothing
downstream can tell: the Trainer would report uniform scores that look like a
consistent cohort, and the conformance harness would report that every model is
equally good. Both failures corroborate each other.

Each case below is a pair — a graph that must trigger the code and a
near-identical graph that must not, differing only in the property under test.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from app.schemas.data_model import EntitySchema, RelationshipSchema
from app.services.graph_engine import GraphEngine
from tests.test_graph_engine import col, entity, rel

Graph = tuple[list[EntitySchema], list[RelationshipSchema]]


@dataclass(frozen=True)
class Case:
    """One linter code, with the two graphs that must separate it."""

    code: str
    triggers: Callable[[], Graph]
    silent: Callable[[], Graph]
    difference: str


def _pk(name: str = "id"):
    return col(name, pk=True)


CASES: list[Case] = [
    Case(
        code="MISSING_PK",
        triggers=lambda: ([entity("a", [col("name")])], []),
        silent=lambda: ([entity("a", [_pk(), col("name")])], []),
        difference="the table has a primary key",
    ),
    Case(
        code="CYCLIC_FK",
        triggers=lambda: (
            [
                entity("a", [_pk(), col("b_id", fk=True)]),
                entity("b", [_pk(), col("a_id", fk=True)]),
            ],
            [rel("a.b_id", "b.id"), rel("b.a_id", "a.id")],
        ),
        silent=lambda: (
            [
                entity("a", [_pk(), col("b_id", fk=True)]),
                entity("b", [_pk(), col("note")]),
            ],
            [rel("a.b_id", "b.id")],
        ),
        difference="the second relationship closes the loop",
    ),
    Case(
        code="DANGLING_REF",
        triggers=lambda: (
            [entity("a", [_pk(), col("ghost_id", fk=True)])],
            [rel("a.ghost_id", "nowhere.id")],
        ),
        silent=lambda: (
            [
                entity("a", [_pk(), col("b_id", fk=True)]),
                entity("b", [_pk()]),
            ],
            [rel("a.b_id", "b.id")],
        ),
        difference="the referenced entity exists",
    ),
    Case(
        code="ORPHAN_ENTITY",
        triggers=lambda: (
            [
                entity("a", [_pk(), col("b_id", fk=True)]),
                entity("b", [_pk()]),
                entity("island", [_pk()]),
            ],
            [rel("a.b_id", "b.id")],
        ),
        silent=lambda: (
            [
                entity("a", [_pk(), col("b_id", fk=True)]),
                entity("b", [_pk()]),
            ],
            [rel("a.b_id", "b.id")],
        ),
        difference="no entity sits outside the graph",
    ),
    Case(
        code="FAN_OUT_RISK",
        triggers=lambda: (
            [entity("a", [_pk()]), entity("b", [_pk()])],
            [rel("a.id", "b.id", "N:M")],
        ),
        silent=lambda: (
            [entity("a", [_pk()]), entity("b", [_pk()])],
            [rel("a.id", "b.id", "1:N")],
        ),
        difference="the relationship is not many-to-many",
    ),
    Case(
        code="MISSING_DESCRIPTION",
        triggers=lambda: ([entity("a", [_pk()], desc=None)], []),
        silent=lambda: ([entity("a", [_pk()], desc="documented")], []),
        difference="the entity carries a description",
    ),
    Case(
        code="MISSING_GRAIN",
        triggers=lambda: ([entity("fact_x", [_pk()], "FACT", grain=None)], []),
        silent=lambda: (
            [entity("fact_x", [_pk()], "FACT", grain="one row per x")],
            [],
        ),
        difference="the fact declares its grain",
    ),
    Case(
        code="MISSING_SLA",
        triggers=lambda: (
            [entity("a", [_pk()], tier="TIER_1_CRITICAL", sla=None)],
            [],
        ),
        silent=lambda: (
            [entity("a", [_pk()], tier="TIER_1_CRITICAL", sla="< 1h")],
            [],
        ),
        difference="the critical asset declares a freshness SLA",
    ),
    Case(
        code="NAMING_CONVENTION",
        triggers=lambda: ([entity("FactOrders", [_pk()], "FACT")], []),
        silent=lambda: ([entity("fact_orders", [_pk()], "FACT")], []),
        difference="the name is snake_case with the right prefix",
    ),
    Case(
        code="PII_EXPOSURE",
        triggers=lambda: ([entity("a", [_pk(), col("email")])], []),
        silent=lambda: ([entity("a", [_pk(), col("email", pii=True)])], []),
        difference="the personal column is classified as PII",
    ),
    Case(
        code="INVALID_RANGE",
        triggers=lambda: (
            [entity("a", [_pk(), col("n", data_type="INT", min_value=10, max_value=1)])],
            [],
        ),
        silent=lambda: (
            [entity("a", [_pk(), col("n", data_type="INT", min_value=1, max_value=10)])],
            [],
        ),
        difference="the range is satisfiable",
    ),
    Case(
        code="INVALID_REGEX",
        triggers=lambda: ([entity("a", [_pk(), col("s", regex_pattern="([a-z")])], []),
        silent=lambda: ([entity("a", [_pk(), col("s", regex_pattern="^[a-z]+$")])], []),
        difference="the pattern compiles",
    ),
    Case(
        code="PATTERN_EXCEEDS_LENGTH",
        triggers=lambda: (
            [
                entity(
                    "a",
                    [_pk(), col("c", data_type="VARCHAR(6)", regex_pattern=r"^[A-Z]{3}-\d{4}$")],
                )
            ],
            [],
        ),
        silent=lambda: (
            [
                entity(
                    "a",
                    [_pk(), col("c", data_type="VARCHAR(8)", regex_pattern=r"^[A-Z]{3}-\d{4}$")],
                )
            ],
            [],
        ),
        difference="the column is wide enough for the pattern",
    ),
]

CASE_IDS = [c.code for c in CASES]


def _codes(entities, relationships) -> set[str]:
    return {i.code for i in GraphEngine().validate(entities, relationships).issues}


def test_every_emitted_code_has_a_discrimination_case() -> None:
    """The pairs must cover every code the linter can emit.

    Standard 11 applied to this file: a code added later without a case here
    would be graded by the Trainer and scored by the conformance harness while
    never having been shown to discriminate. Read the emit sites from the
    source rather than restating a number, so the check cannot drift.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent
        / "app" / "services" / "graph_engine.py"
    ).read_text(encoding="utf-8")
    emitted = set(re.findall(r'code="([A-Z_]+)"', source))
    covered = {c.code for c in CASES}

    assert emitted - covered == set(), (
        f"linter codes with no discrimination case: {sorted(emitted - covered)}"
    )
    assert covered - emitted == set(), (
        f"cases for codes the linter cannot emit: {sorted(covered - emitted)}"
    )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_code_fires_when_it_should(case: Case) -> None:
    entities, relationships = case.triggers()
    assert case.code in _codes(entities, relationships), (
        f"{case.code} did not fire on a graph built to trigger it"
    )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_code_is_silent_when_it_should_be(case: Case) -> None:
    """The half that catches a code firing on everything.

    A linter that reports every code on every graph passes every positive test
    in this file and is worthless. This is the assertion that separates a
    working instrument from one that only looks busy.
    """
    entities, relationships = case.silent()
    assert case.code not in _codes(entities, relationships), (
        f"{case.code} fired on a graph that differs only in that "
        f"{case.difference} — the code does not discriminate"
    )
