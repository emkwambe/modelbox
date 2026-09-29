"""Model-supplied SQL fragments are checked against the dialect's grammar.

A column's ``data_type`` and ``default_value`` come from model output, from
introspection, or from the canvas, and the DDL and dbt emitters interpolate
them into SQL. So each must parse as exactly what it claims to be before it
reaches an emitter; anything else is refused with a lint code and never
emitted verbatim (Sprint 7, Step 2.4).

**Why not `DataType.build`.** It returns ``INT`` for ``"INT); DROP TABLE x; --"``
and silently discards the rest. The checks here parse the fragment inside a
whole statement and require that statement to be exactly the expected shape:

* ``data_type`` — ``SELECT CAST(NULL AS <data_type>)`` is one statement whose
  only projection is a ``Cast`` carrying nothing but its value and type.
  Trailing clauses (``DEFAULT``, ``FROM``, a second statement) fail.
* ``default_value`` — ``SELECT <default_value>`` is one statement with one
  projection, no alias, no subquery and no ``FROM``.

Both refuse any comment in the parsed tree: a ``--`` in a type would comment
out the rest of its DDL line. A ``--`` inside a string literal is not a
comment and passes.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

INVALID_DATA_TYPE = "INVALID_DATA_TYPE"
INVALID_DEFAULT = "INVALID_DEFAULT"

# The dialect model output is authored in (see ExporterService._source_dialect).
DEFAULT_DIALECT = "snowflake"


def _has_comments(tree: exp.Expression) -> bool:
    return any(node.comments for node in tree.walk())


def _parse_single(sql: str, dialect: str) -> exp.Select | None:
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.SqlglotError:
        return None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return None
    select = statements[0]
    if select.args.get("from") or len(select.expressions) != 1 or _has_comments(select):
        return None
    return select


def data_type_problem(data_type: str, dialect: str = DEFAULT_DIALECT) -> str | None:
    """Why ``data_type`` is not exactly one type in ``dialect``, or None."""
    select = _parse_single(f"SELECT CAST(NULL AS {data_type})", dialect)
    if select is None:
        return f"data type {data_type!r} is not a single {dialect} type"
    cast = select.expressions[0]
    extra = [
        key for key, value in cast.args.items()
        if key not in ("this", "to") and value not in (None, False, [])
    ]
    if not isinstance(cast, exp.Cast) or extra:
        return f"data type {data_type!r} is not a single {dialect} type"
    return None


def default_problem(default_value: str, dialect: str = DEFAULT_DIALECT) -> str | None:
    """Why ``default_value`` is not one scalar expression in ``dialect``, or None."""
    select = _parse_single(f"SELECT {default_value}", dialect)
    if select is None:
        return f"default {default_value!r} is not a single {dialect} expression"
    value = select.expressions[0]
    if isinstance(value, exp.Alias) or any(
        isinstance(node, (exp.Select, exp.Subquery)) for node in value.walk()
    ):
        return f"default {default_value!r} is not a single {dialect} expression"
    return None


def column_problems(
    data_type: str, default_value: str | None, dialect: str = DEFAULT_DIALECT
) -> list[tuple[str, str]]:
    """``(code, message)`` for each fragment of one column that fails its check."""
    problems: list[tuple[str, str]] = []
    if (reason := data_type_problem(data_type, dialect)) is not None:
        problems.append((INVALID_DATA_TYPE, reason))
    if default_value and (reason := default_problem(default_value, dialect)) is not None:
        problems.append((INVALID_DEFAULT, reason))
    return problems
