"""The drift classification rules, one by one (Sprint 8 Step 5, item 2).

Each rule D1-D19 has a case it must classify, and every rule that shares a
kind of change with another is paired with the neighbouring case that must
land on the other rule, so no test passes because a kind maps to one class.
The rules' texts are the ones the user guide lists; a test holds the two
together.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.schemas.data_model import ColumnSchema, EntitySchema
from app.services import drift_rules
from app.services.diff_engine import CHANGE_KINDS, Change
from app.services.drift_rules import (
    BREAKING,
    INFORMATIONAL,
    NON_BREAKING,
    classify,
    widens,
)

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "USER_GUIDE.md"


def _col(nullable: bool = True, default: str | None = None) -> ColumnSchema:
    return ColumnSchema(name="c", data_type="INTEGER", is_nullable=nullable, default_value=default)


TABLE = EntitySchema(entity_name="t", columns=[ColumnSchema(name="id", data_type="INTEGER")])

CASES = [
    ("D1", BREAKING, Change("table_removed", "t", before=TABLE)),
    ("D2", NON_BREAKING, Change("table_added", "t", after=TABLE)),
    ("D3", BREAKING, Change("column_removed", "t", "c", before=_col())),
    ("D4", BREAKING, Change("column_added", "t", "c", after=_col(nullable=False))),
    ("D5", NON_BREAKING, Change("column_added", "t", "c", after=_col(nullable=True))),
    ("D5", NON_BREAKING, Change("column_added", "t", "c", after=_col(nullable=False, default="0"))),
    ("D6", NON_BREAKING, Change("type_changed", "t", "c", before="VARCHAR(30)", after="VARCHAR(40)")),
    ("D7", BREAKING, Change("type_changed", "t", "c", before="VARCHAR(35)", after="VARCHAR(32)")),
    ("D7", BREAKING, Change("type_changed", "t", "c", before="INTEGER", after="VARCHAR(10)")),
    ("D8", INFORMATIONAL, Change("declared_type_changed", "t", "c", before="varchar2(10 BYTE)",
                                 after="VARCHAR2(10)")),
    ("D9", BREAKING, Change("nullability_changed", "t", "c", before=True, after=False)),
    ("D10", NON_BREAKING, Change("nullability_changed", "t", "c", before=False, after=True)),
    ("D11", NON_BREAKING, Change("default_changed", "t", "c", before="3", after="5")),
    ("D12", BREAKING, Change("primary_key_changed", "t", columns=("a", "b", "c"), before=["a", "b"],
                             after=["a", "b", "c"])),
    ("D13", BREAKING, Change("unique_added", "t", columns=("a", "b"))),
    ("D14", BREAKING, Change("unique_removed", "t", columns=("a",))),
    ("D15", BREAKING, Change("foreign_key_added", "t", columns=("a",), detail={"to": "u", "to_columns": ["id"]})),
    ("D16", BREAKING, Change("foreign_key_removed", "t", columns=("a",), detail={"to": "u", "to_columns": ["id"]})),
    ("D17", BREAKING, Change("check_added", "t", columns=("a",), after="a > 0")),
    ("D18", NON_BREAKING, Change("check_removed", "t", columns=("a",), before="a > 0")),
    ("D19", INFORMATIONAL, Change("description_changed", "t", "c", before="Old.", after="New.")),
    ("D19", INFORMATIONAL, Change("description_changed", "t", before=None, after="Film genres.")),
]


@pytest.mark.parametrize(("rule", "cls", "change"), CASES, ids=[f"{r}-{c.kind}-{i}" for i, (r, _, c) in
                                                                  enumerate(CASES)])
def test_each_rule_classifies_its_case(rule: str, cls: str, change: Change) -> None:
    got = classify(change)
    assert (got.id, got.cls) == (rule, cls)


def test_every_rule_has_a_case_and_every_kind_a_rule() -> None:
    assert {r.id for r in drift_rules.RULES} == {rule for rule, _, _ in CASES}
    # column_renamed is the migration diff's (identity pairing); the drift
    # report pairs by name and never produces it.
    assert {c.kind for _, _, c in CASES} == set(CHANGE_KINDS) - {"column_renamed"}


def test_a_change_no_rule_covers_is_an_error() -> None:
    with pytest.raises(drift_rules.Unclassified):
        classify(Change("column_renamed", "t", "c", before="a", after="c"))


def test_the_user_guide_lists_every_rule_with_its_text_and_class() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    for rule in drift_rules.RULES:
        row = re.search(rf"^\| {rule.id} \| (.+?) \| (\S+) \|$", guide, re.MULTILINE)
        assert row is not None, f"{rule.id} is not in the user guide's rule table"
        assert (row.group(1), row.group(2)) == (rule.text, rule.cls), rule.id


@pytest.mark.parametrize(("before", "after", "wider"), [
    ("VARCHAR(30)", "VARCHAR(40)", True),
    ("VARCHAR(35)", "VARCHAR(32)", False),
    ("VARCHAR(10)", "TEXT", True),
    ("TEXT", "VARCHAR(16)", False),
    ("CHAR(2)", "VARCHAR(2)", True),
    ("VARCHAR(2)", "CHAR(2)", False),
    ("VARCHAR(10)", "NVARCHAR(10)", True),
    ("NVARCHAR(10)", "NVARCHAR(5)", False),
    ("NVARCHAR(10)", "VARCHAR(10)", False),
    ("DECIMAL(5, 2)", "DECIMAL(7, 2)", True),
    ("DECIMAL(7, 2)", "DECIMAL(5, 2)", False),
    ("DECIMAL(5, 2)", "DECIMAL(5, 3)", False),
    ("SMALLINT", "INT", True),
    ("INT", "SMALLINT", False),
    ("INT", "DECIMAL(10, 0)", True),
    ("INT", "DECIMAL(9, 0)", False),
    ("FLOAT", "DOUBLE", True),
    ("TIMESTAMP(3)", "TIMESTAMP(6)", True),
    ("TIMESTAMP(6)", "TIMESTAMP(3)", False),
    ("DATE", "TIMESTAMP", False),
    ("INT", "VARCHAR(20)", False),
    ("not a type (", "INT", False),
])
def test_widening(before: str, after: str, wider: bool) -> None:
    assert widens(before, after) is wider


def test_negative_control_a_broken_rule_changes_its_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-rule test can fail: with D9 mis-written as non-breaking, its case is misclassified."""
    broken = tuple(r if r.id != "D9" else drift_rules.Rule("D9", r.text, NON_BREAKING, r.applies)
                   for r in drift_rules.RULES)
    monkeypatch.setattr(drift_rules, "RULES", broken)
    rule, cls, change = next(c for c in CASES if c[0] == "D9")
    got = classify(change)
    assert (got.id, got.cls) != (rule, cls)
