"""How each drift is classified: breaking, non-breaking or informational.

Sprint 8 Step 5. A drift is **breaking** when something that works against the
documented design can fail against the deployed schema: a read that names a
column or table that is gone, a write the deployed schema now refuses (a new
constraint, a narrower type, NOT NULL), or a guarantee a consumer relies on
that no longer holds (a key or foreign key removed). **Non-breaking** when
nothing that works today can fail: an addition nothing depends on, a looser
rule, a wider type. **Informational** when only text a person reads changed.

Every rule is written here once, in :data:`RULES`, in the order it is tried;
the user guide lists the same rules with the same ids, and each has its own
test. A change that no rule matches is an error, never a silent default.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.services.diff_engine import Change

BREAKING = "breaking"
NON_BREAKING = "non-breaking"
INFORMATIONAL = "informational"
CLASSES = (BREAKING, NON_BREAKING, INFORMATIONAL)


@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    cls: str
    applies: Callable[[Change, str], bool]


# -- type widening ------------------------------------------------------------
_INTEGER_RANK = {"TINYINT": 1, "UTINYINT": 1, "SMALLINT": 2, "USMALLINT": 2, "INT": 3, "UINT": 3, "BIGINT": 4,
                 "UBIGINT": 4}
_FLOAT_RANK = {"FLOAT": 1, "DOUBLE": 2}
_FIXED_TEXT = {"CHAR", "NCHAR"}
_VARYING_TEXT = {"VARCHAR", "NVARCHAR", "TEXT"}
_UNICODE_TEXT = {"NCHAR", "NVARCHAR"}
_DECIMALS = {"DECIMAL", "NUMERIC", "BIGDECIMAL"}
_TEMPORAL = {"TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMPLTZ", "DATETIME", "DATETIME2", "TIME", "TIMETZ"}


def _parse(data_type: str, dialect: str) -> exp.DataType | None:
    for read in (dialect or None, None):
        try:
            return exp.DataType.build(data_type, dialect=read)
        except (sqlglot.errors.ParseError, ValueError):
            continue
    return None


def _params(kind: exp.DataType) -> list[int | None]:
    """The numeric parameters of a type; None for one that is not a number (MAX)."""
    out: list[int | None] = []
    for param in kind.expressions:
        text = param.name if isinstance(param, exp.DataTypeParam) else param.sql()
        out.append(int(text) if text.isdigit() else None)
    return out


def widens(before: str, after: str, dialect: str = "") -> bool:
    """Whether every value of ``before`` fits ``after`` unchanged.

    True only for a change this can prove: a larger integer, a decimal with
    at least as many digits on each side of the point, a longer or unbounded
    string of the same kind (fixed to varying and ASCII to Unicode also
    widen), a larger float, more fractional seconds. Anything else, including
    any type this cannot read, is not a widening.
    """
    a, b = _parse(before, dialect), _parse(after, dialect)
    if a is None or b is None:
        return False
    ta, tb = a.this.name, b.this.name
    pa, pb = _params(a), _params(b)
    if ta in _INTEGER_RANK and tb in _INTEGER_RANK:
        return _INTEGER_RANK[tb] >= _INTEGER_RANK[ta]
    if ta in _INTEGER_RANK and tb in _DECIMALS:
        # The integer's largest value has this many digits; the decimal must
        # hold that many before its point.
        digits = {1: 3, 2: 5, 3: 10, 4: 19}[_INTEGER_RANK[ta]]
        if not pb:
            return True
        precision, scale = pb[0], (pb[1] if len(pb) > 1 else 0)
        return precision is not None and scale is not None and precision - scale >= digits
    if ta in _DECIMALS and tb in _DECIMALS:
        if not pb:
            return True
        if not pa:
            return False
        p1, s1 = pa[0], pa[1] if len(pa) > 1 else 0
        p2, s2 = pb[0], pb[1] if len(pb) > 1 else 0
        if None in (p1, s1, p2, s2):
            return False
        return p2 >= p1 and s2 >= s1 and (p2 - s2) >= (p1 - s1)  # type: ignore[operator]
    if ta in _FLOAT_RANK and tb in _FLOAT_RANK:
        return _FLOAT_RANK[tb] >= _FLOAT_RANK[ta]
    texts = _FIXED_TEXT | _VARYING_TEXT
    if ta in texts and tb in texts:
        if ta in _VARYING_TEXT and tb in _FIXED_TEXT:
            return False  # a fixed width pads, and truncates what is longer
        if ta in _UNICODE_TEXT and tb not in _UNICODE_TEXT and tb != "TEXT":
            return False
        unbounded_b = tb == "TEXT" or not pb or pb[0] is None
        unbounded_a = ta == "TEXT" or not pa or pa[0] is None
        if unbounded_b:
            return True
        if unbounded_a:
            return False
        return pb[0] >= pa[0]  # type: ignore[operator]
    if ta == tb and ta in _TEMPORAL:
        return (pb[0] if pb else 6) >= (pa[0] if pa else 6)  # type: ignore[operator]
    return False


def _added_column(change: Change) -> tuple[bool, bool]:
    """(nullable, has a default) for an added column."""
    column = change.after
    return bool(column.is_nullable), bool(column.default_value or column.source_default_value)


# -- the rules, in the order they are tried ---------------------------------
RULES: tuple[Rule, ...] = (
    Rule("D1", "A table is removed.", BREAKING, lambda c, _: c.kind == "table_removed"),
    Rule("D2", "A table is added.", NON_BREAKING, lambda c, _: c.kind == "table_added"),
    Rule("D3", "A column is removed (a renamed column is a removal and an addition).", BREAKING,
         lambda c, _: c.kind == "column_removed"),
    Rule("D4", "A NOT NULL column with no default is added: existing inserts that omit it fail.", BREAKING,
         lambda c, _: c.kind == "column_added" and _added_column(c) == (False, False)),
    Rule("D5", "A nullable column, or a NOT NULL column with a default, is added.", NON_BREAKING,
         lambda c, _: c.kind == "column_added"),
    Rule("D6", "A type is widened: every value of the old type fits the new one.", NON_BREAKING,
         lambda c, dialect: c.kind == "type_changed" and widens(c.before, c.after, dialect)),
    Rule("D7", "A type is narrowed, or changed to another kind of type.", BREAKING,
         lambda c, _: c.kind == "type_changed"),
    Rule("D8", "The declared type's text changed and its normalized type did not.", INFORMATIONAL,
         lambda c, _: c.kind == "declared_type_changed"),
    Rule("D9", "A nullable column becomes NOT NULL.", BREAKING,
         lambda c, _: c.kind == "nullability_changed" and c.after is False),
    Rule("D10", "A NOT NULL column becomes nullable.", NON_BREAKING,
         lambda c, _: c.kind == "nullability_changed" and c.after is True),
    Rule("D11", "A default is added, changed or removed: only rows inserted later are affected.", NON_BREAKING,
         lambda c, _: c.kind == "default_changed"),
    Rule("D12", "The primary key is added, removed, or its columns or their order change.", BREAKING,
         lambda c, _: c.kind == "primary_key_changed"),
    Rule("D13", "A UNIQUE constraint is added: writes the design allows can be refused.", BREAKING,
         lambda c, _: c.kind == "unique_added"),
    Rule("D14", "A UNIQUE constraint is removed: consumers relying on uniqueness lose it.", BREAKING,
         lambda c, _: c.kind == "unique_removed"),
    Rule("D15", "A foreign key is added: writes the design allows can be refused.", BREAKING,
         lambda c, _: c.kind == "foreign_key_added"),
    Rule("D16", "A foreign key is removed: consumers relying on the reference lose it.", BREAKING,
         lambda c, _: c.kind == "foreign_key_removed"),
    Rule("D17", "A CHECK constraint is added: writes the design allows can be refused.", BREAKING,
         lambda c, _: c.kind == "check_added"),
    Rule("D18", "A CHECK constraint is removed: the deployed schema accepts more.", NON_BREAKING,
         lambda c, _: c.kind == "check_removed"),
    Rule("D19", "A table or column description is added, changed or removed.", INFORMATIONAL,
         lambda c, _: c.kind == "description_changed"),
)


class Unclassified(ValueError):
    """A change no rule covers: a gap in the rules, never a silent default."""


def classify(change: Change, dialect: str = "") -> Rule:
    """The first rule that applies to ``change``."""
    for rule in RULES:
        if rule.applies(change, dialect):
            return rule
    raise Unclassified(f"no drift rule covers {change.kind}")
