"""Guard: every Trainer 'Spot the Flaw' lab is gradable by the shipped linter.

Each lab's `expected_flaws` codes must match exactly what GraphEngine.validate
produces on its flawed graph — so labs never drift from the appliance.
"""

from __future__ import annotations

import json
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
