"""Guard: every Trainer 'Spot the Flaw' lab is gradable by the shipped linter.

Each lab's `expected_flaws` codes must match exactly what GraphEngine.validate
produces on its flawed graph — so labs never drift from the appliance.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.schemas.data_model import ColumnSchema, EntitySchema, RelationshipSchema
from app.services.graph_engine import GraphEngine

_LAB_DIR = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "content" / "trainer"
)
_LABS = sorted(_LAB_DIR.glob("*.json")) if _LAB_DIR.is_dir() else []


def _load(lab: dict) -> tuple[list[EntitySchema], list[RelationshipSchema]]:
    entities = [
        EntitySchema(
            entity_name=e["entity_name"],
            entity_type=e["entity_type"],
            grain=e.get("grain"),
            description=e.get("description"),
            tier=e.get("tier"),
            freshness_sla=e.get("freshness_sla"),
            columns=[ColumnSchema(**c) for c in e["columns"]],
        )
        for e in lab["graph"]["entities"]
    ]
    relationships = [
        RelationshipSchema.model_validate(r) for r in lab["graph"]["relationships"]
    ]
    return entities, relationships


def _linter_codes() -> set[str]:
    """Every code the linter can emit, read off its source.

    Derived rather than listed, so a new rule added to `GraphEngine` fails the
    coverage test below until a lab teaches it. A hand-written list would go on
    passing while the curriculum silently fell behind the appliance — the same
    breadth failure as a gate parameterised over fixtures that do not exercise
    the feature (standard 11).
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "graph_engine.py"
    ).read_text(encoding="utf-8")
    return set(re.findall(r'code="([A-Z_]+)"', source))


def test_every_linter_code_is_taught_by_some_lab() -> None:
    """H2 — all linter codes are taught and gradeable.

    A code no lab exercises is a fault the appliance reports and the curriculum
    never prepares anyone to read. Four were in that position until the
    integration-review lab: CYCLIC_FK, DANGLING_REF, ORPHAN_ENTITY and
    PATTERN_EXCEEDS_LENGTH — the structural ones that only appear when separate
    pieces of work are put together, which is precisely when a learner meets
    them in practice.

    Mutation, 2026-08-29: removing `m4_lab2_integration_review.json` fails this
    with those four named, and nothing else in the suite notices — which is the
    gap it was written to close.
    """
    taught: set[str] = set()
    for path in _LABS:
        lab = json.loads(path.read_text(encoding="utf-8"))
        taught.update(flaw["code"] for flaw in lab["expected_flaws"])

    codes = _linter_codes()
    assert codes, "fixture sanity: no linter codes were found in graph_engine.py"
    untaught = sorted(codes - taught)
    assert not untaught, (
        f"these linter codes are reported by the appliance but taught by no "
        f"lab: {untaught}"
    )


@pytest.mark.skipif(not _LABS, reason="no Trainer labs present")
@pytest.mark.parametrize("lab_path", _LABS, ids=lambda p: p.stem)
def test_lab_flaws_match_linter(lab_path: Path) -> None:
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    entities, relationships = _load(lab)
    report = GraphEngine().validate(entities, relationships)

    produced = {issue.code for issue in report.issues}
    expected = {flaw["code"] for flaw in lab["expected_flaws"]}
    assert produced == expected, (
        f"{lab_path.name}: linter produced {sorted(produced)} "
        f"but expected_flaws declare {sorted(expected)}"
    )
