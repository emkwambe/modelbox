"""SQL DDL for a model: tables, keys, constraints and descriptions, or a named gap.

What the model holds is emitted: each entity's columns (type, DEFAULT, NOT
NULL), its primary key in key order, its UNIQUE and CHECK constraints, each
resolved relationship as a FOREIGN KEY over all its column pairs, and table
and column descriptions as ``COMMENT ON``. Anything the target dialect cannot
express, or the model cannot state completely, is an **export gap**: named,
listed at the top of the file and returned with it, and never silently left
out.

Fragments a model supplies are checked before they are placed in a statement:
types and defaults by :mod:`app.services.sql_fragments`, a CHECK expression by
parsing it alone as one boolean expression in the source dialect and again in
the target. A CHECK that fails either is a gap, not verbatim text.

Identifiers are quoted where the target would otherwise change or reject them:
any name that is not lower-case snake case, and any reserved word. Lower-case
names, which is every name a synthesized model uses, are emitted as before.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import sqlglot
from sqlglot import exp

from app.schemas.data_model import EntitySchema, RelationshipSchema, SynthesizedModel

# Which table-level features each target accepts in CREATE TABLE and as
# statements. PRIMARY KEY and FOREIGN KEY are emitted for every target, as
# before; the rest only where the target has them.
_CAPABILITIES: dict[str, frozenset[str]] = {
    "postgres": frozenset({"unique", "check", "comment"}),
    "duckdb": frozenset({"unique", "check", "comment"}),
    "snowflake": frozenset({"unique", "comment"}),
    "redshift": frozenset({"unique", "comment"}),
    "databricks": frozenset(),
    "bigquery": frozenset(),
    "clickhouse": frozenset(),
}

# Reserved in PostgreSQL (and, for these words, in the other targets): a name
# equal to one must be quoted.
_RESERVED = frozenset({
    "ALL", "ANALYSE", "ANALYZE", "AND", "ANY", "ARRAY", "AS", "ASC", "ASYMMETRIC", "AUTHORIZATION",
    "BINARY", "BOTH", "CASE", "CAST", "CHECK", "COLLATE", "COLLATION", "COLUMN", "CONCURRENTLY",
    "CONSTRAINT", "CREATE", "CROSS", "CURRENT_CATALOG", "CURRENT_DATE", "CURRENT_ROLE", "CURRENT_SCHEMA",
    "CURRENT_TIME", "CURRENT_TIMESTAMP", "CURRENT_USER", "DEFAULT", "DEFERRABLE", "DESC", "DISTINCT", "DO",
    "ELSE", "END", "EXCEPT", "FALSE", "FETCH", "FOR", "FOREIGN", "FREEZE", "FROM", "FULL", "GRANT", "GROUP",
    "HAVING", "ILIKE", "IN", "INITIALLY", "INNER", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "LATERAL",
    "LEADING", "LEFT", "LIKE", "LIMIT", "LOCALTIME", "LOCALTIMESTAMP", "NATURAL", "NOT", "NOTNULL", "NULL",
    "OFFSET", "ON", "ONLY", "OR", "ORDER", "OUTER", "OVERLAPS", "PLACING", "PRIMARY", "REFERENCES",
    "RETURNING", "RIGHT", "SELECT", "SESSION_USER", "SIMILAR", "SOME", "SYMMETRIC", "TABLE", "TABLESAMPLE",
    "THEN", "TO", "TRAILING", "TRUE", "UNION", "UNIQUE", "USER", "USING", "VARIADIC", "VERBOSE", "WHEN",
    "WHERE", "WINDOW", "WITH",
})
_PLAIN = re.compile(r"[a-z_][a-z0-9_]*")

# A computed column declares no type the model holds (its expression is kept
# in the import report), so it has no column definition to emit.
COMPUTED = "COMPUTED"


@dataclass(frozen=True)
class ExportGap:
    """Something the model holds that this DDL does not state, and why."""

    kind: str
    entity: str | None
    detail: str

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass
class DdlExport:
    sql: str
    gaps: list[ExportGap]


class DdlExportError(ValueError):
    """A fragment is not valid SQL; the message names it and its lint code."""


def quote(name: str) -> str:
    """``name`` as a double-quoted identifier where it needs one."""
    if _PLAIN.fullmatch(name) and name.upper() not in _RESERVED:
        return name
    return '"' + name.replace('"', '""') + '"'


def _columns(names: list[str]) -> str:
    return ", ".join(quote(n) for n in names)


def _named(constraint_name: str | None) -> str:
    return f"CONSTRAINT {quote(constraint_name)} " if constraint_name else ""


def _missing(columns: list[str], emitted: set[str]) -> list[str]:
    return [c for c in columns if c not in emitted]


def _single_condition(sql: str, dialect: str) -> exp.Expression | None:
    """The condition of ``SELECT 1 WHERE (…)`` if that is all the text is, else None."""
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.SqlglotError:
        return None
    select = statements[0] if len(statements) == 1 else None
    if not isinstance(select, exp.Select) or select.args.get("from") is not None:
        return None
    where = select.args.get("where")
    if where is None or any(node.comments for node in select.walk()):
        return None
    if any(isinstance(node, (exp.Select, exp.Subquery)) for node in where.this.walk()):
        return None
    return where.this


def translate_check(
    expression: str, source: str, target: str, columns: list[str] | None = None
) -> tuple[str | None, str | None]:
    """(the CHECK condition written for ``target``, None) or (None, why it cannot be).

    A column the expression names is written as the entity's own column name,
    quoted as the column definition is. Dialects fold unquoted names
    differently (Oracle up, PostgreSQL down), so ``web_address`` in an Oracle
    CHECK means ``"WEB_ADDRESS"``, and copied unquoted into PostgreSQL it would
    name a column that does not exist.
    """
    condition = _single_condition(f"SELECT 1 WHERE ({expression})", source)
    if condition is None:
        return None, f"is not a single {source} boolean expression"
    if columns:
        exact = set(columns)
        folded = {c.lower(): c for c in columns}
        for node in condition.find_all(exp.Column):
            if node.table:
                continue
            identifier = node.this
            if not isinstance(identifier, exp.Identifier):
                continue
            name = identifier.name if identifier.name in exact else (
                None if identifier.args.get("quoted") else folded.get(identifier.name.lower()))
            if name is not None:
                node.set("this", exp.to_identifier(name, quoted=quote(name) != name))
    try:
        written = condition.sql(dialect=target)
    except sqlglot.errors.SqlglotError:
        return None, f"does not translate from {source} to {target}"
    if _single_condition(f"SELECT 1 WHERE ({written})", target) is None:
        return None, f"does not parse as {target} once translated"
    return written, None


# Types a target has no exact equivalent for, after sqlglot's translation:
# (type -> replacement, or None to keep it) and what the gap says. Each use is
# an export gap; nothing is widened or dropped silently.
_TYPE_GAPS: dict[str, dict[str, tuple[str | None, str]]] = {  # keyed by sqlglot type name
    "postgres": {
        "UTINYINT": ("SMALLINT", "PostgreSQL has no one-byte integer; emitted as SMALLINT"),
        "SMALLMONEY": ("MONEY", "PostgreSQL has no SMALLMONEY; emitted as MONEY"),
        "GEOGRAPHY": (None, "GEOGRAPHY needs the PostGIS extension"),
    },
}
_USER_TYPE_GAPS: dict[str, dict[str, tuple[str, str]]] = {
    "postgres": {"HIERARCHYID": ("VARCHAR", ("PostgreSQL has no HIERARCHYID; emitted as VARCHAR, "
                                             "which holds its string form ('/1/3/')"))},
}
_MAX_PRECISION: dict[str, int] = {"postgres": 6}
_TEMPORAL = frozenset({"TIMESTAMP", "TIME", "TIMESTAMPTZ", "DATETIME2", "DATETIME", "TIMETZ"})


def _fit_type(column: exp.ColumnDef, entity: str, target: str, gaps: list[ExportGap]) -> None:
    """Replace or annotate a translated type the target cannot hold as written."""
    kind = column.args.get("kind")
    if not isinstance(kind, exp.DataType):
        return
    written = kind.sql(dialect=target)
    params = kind.expressions
    if params and all(isinstance(p, exp.DataTypeParam) and p.name.upper() == "MAX" for p in params) \
            and target == "postgres":
        kind.set("expressions", [])  # unbounded is PostgreSQL's default: exact
    if target == "postgres" and params and params[0].name == "*":
        # Oracle's NUMBER(*, s): '*' is Oracle's maximum precision, 38. Exact.
        params[0].set("this", exp.Literal.number(38))
    substitute = _TYPE_GAPS.get(target, {}).get(kind.this.name)
    if substitute is not None:
        replacement, why = substitute
        if replacement is not None:
            column.set("kind", exp.DataType.build(replacement, dialect=target))
        gaps.append(ExportGap("data_type", entity, f"{column.name} {written}: {why}"))
    elif kind.this == exp.DataType.Type.USERDEFINED:
        user = _USER_TYPE_GAPS.get(target, {}).get(kind.sql().upper())
        if user is not None:
            column.set("kind", exp.DataType.build(user[0], dialect=target))
            gaps.append(ExportGap("data_type", entity, f"{column.name} {written}: {user[1]}"))
    limit = _MAX_PRECISION.get(target)
    if limit is not None and kind.this.name in _TEMPORAL and len(params) == 1 and params[0].name.isdigit() \
            and int(params[0].name) > limit:
        kind.set("expressions", [exp.DataTypeParam(this=exp.Literal.number(limit))])
        gaps.append(ExportGap("data_type", entity,
                              f"{column.name} {written}: {target} keeps at most {limit} fractional digits"))


def _constraint_node(text: str, target: str) -> exp.Expression:
    """A table constraint written for ``target``, as a node to append to a table."""
    tree = sqlglot.parse_one(f"CREATE TABLE _t (_c INT, {text})", read=target)
    if not isinstance(tree, exp.Create) or not isinstance(tree.this, exp.Schema) or len(tree.this.expressions) != 2:
        raise DdlExportError(f"constraint {text!r} does not parse as {target}")
    return tree.this.expressions[1]


def _order(model: SynthesizedModel) -> list[EntitySchema]:
    """Referenced tables first (H5); declaration order on a cycle.

    Declaration order emitted a child whose FOREIGN KEY named a table not yet
    created, and psql aborted. A cycle has no order; it is reported as
    CYCLIC_FK, and the tables keep their declared order.
    """
    from app.services.graph_engine import GraphEngine

    by_name = {entity.entity_name: entity for entity in model.entities}
    try:
        ordered = GraphEngine.topological_order(GraphEngine.build_graph(model.entities, model.relationships))
    except Exception:  # noqa: BLE001 - NetworkXUnfeasible on a cyclic graph
        return list(model.entities)
    out = [by_name[name] for name in dict.fromkeys(ordered) if name in by_name]
    return out + [e for e in model.entities if e not in out]


def build_ddl(model: SynthesizedModel, target: str, source: str) -> DdlExport:
    """CREATE TABLE and COMMENT ON statements for ``model`` in ``target``."""
    from app.services.sql_fragments import column_problems

    can = _CAPABILITIES.get(target, frozenset())
    gaps: list[ExportGap] = []
    tables: list[str] = []
    comments: list[str] = []
    entity_columns = {e.entity_name: {c.name for c in e.columns if c.data_type != COMPUTED} for e in model.entities}

    for entity in _order(model):
        name = entity.entity_name
        emitted = entity_columns[name]
        lines: list[str] = []
        for column in entity.columns:
            if column.data_type == COMPUTED:
                gaps.append(ExportGap("computed_column", name,
                                      f"{column.name} is computed; the model holds no type or expression for it"))
                continue
            problems = column_problems(column.data_type, column.default_value, source)
            if problems:
                code, reason = problems[0]
                raise DdlExportError(f"{code}: column '{name}.{column.name}': {reason}.")
            # NOT NULL from the declared constraint (H4): emitting nothing made
            # every column nullable, and Databricks rejected the primary keys.
            # DEFAULT verbatim (M13): the IR stores it already quoted where
            # quoting is needed, a literal the model authored.
            lines.append(f"    {quote(column.name)} {column.data_type}"
                         + (f" DEFAULT {column.default_value}" if column.default_value else "")
                         + ("" if column.is_nullable else " NOT NULL"))

        # Columns are written in the source dialect and translated; every key
        # and constraint clause is written in the target, so translation
        # cannot add to a key (T-SQL's key order became NULLS FIRST).
        try:
            tree = sqlglot.parse_one(f"CREATE TABLE {quote(name)} (\n" + ",\n".join(lines) + "\n)", read=source)
        except sqlglot.errors.SqlglotError as exc:
            raise DdlExportError(f"table '{name}' does not parse as {source}: {exc}") from exc
        if not isinstance(tree, exp.Create) or not isinstance(tree.this, exp.Schema):
            raise DdlExportError(f"table '{name}' did not parse as one CREATE TABLE")
        for column_def in tree.this.expressions:
            _fit_type(column_def, name, target, gaps)

        clauses: list[str] = []
        if entity.primary_key:
            if missing := _missing(entity.primary_key, emitted):
                gaps.append(ExportGap("primary_key", name, f"its columns {missing} are not emitted"))
            else:
                clauses.append(f"PRIMARY KEY ({_columns(entity.primary_key)})")
        for unique in entity.unique_constraints:
            label = f"UNIQUE ({', '.join(unique.columns)})"
            if "unique" not in can:
                gaps.append(ExportGap("unique_constraint", name, f"{label}: {target} has no UNIQUE constraint"))
            elif missing := _missing(unique.columns, emitted):
                gaps.append(ExportGap("unique_constraint", name, f"{label}: columns {missing} are not emitted"))
            else:
                clauses.append(f"{_named(unique.name)}UNIQUE ({_columns(unique.columns)})")
        for check in entity.check_constraints:
            label = f"CHECK ({check.expression})"
            if "check" not in can:
                gaps.append(ExportGap("check_constraint", name, f"{label}: {target} has no CHECK constraint"))
            elif missing := _missing(check.columns, emitted):
                gaps.append(ExportGap("check_constraint", name, f"{label}: columns {missing} are not emitted"))
            else:
                condition, problem = translate_check(check.expression, source, target,
                                                     [c.name for c in entity.columns])
                if problem is not None:
                    gaps.append(ExportGap("check_constraint", name, f"{label} {problem}"))
                else:
                    clauses.append(f"{_named(check.name)}CHECK ({condition})")
        for rel in model.relationships:
            if rel.from_ref == name and (clause := _foreign_key(rel, entity_columns, gaps)) is not None:
                clauses.append(f"{_named(rel.name)}{clause}")
        for clause in clauses:
            tree.this.append("expressions", _constraint_node(clause, target))
        tables.append(tree.sql(dialect=target, pretty=True))

        descriptions = _descriptions(entity, emitted)
        if descriptions and "comment" not in can:
            gaps.append(ExportGap("description", name,
                                  f"{len(descriptions)} descriptions: {target} has no COMMENT ON"))
        elif descriptions:
            comments += [f"COMMENT ON {kind} {target_name} IS '{text.replace(chr(39), chr(39) * 2)}'"
                         for kind, target_name, text in descriptions]

    body = ";\n\n".join(tables + comments) + ";\n"
    if gaps:
        header = [f"-- Export gaps ({len(gaps)}): what the model holds that this file does not state."]
        header += ["-- " + " ".join(f"{g.kind} [{g.entity}]: {g.detail}".split()) for g in gaps]
        body = "\n".join(header) + "\n\n" + body
    return DdlExport(sql=body, gaps=gaps)


def _descriptions(entity: EntitySchema, emitted: set[str]) -> list[tuple[str, str, str]]:
    """(TABLE or COLUMN, the quoted target, the text) for each description to emit."""
    name = entity.entity_name
    table = [("TABLE", quote(name), entity.description)] if entity.description else []
    return table + [("COLUMN", f"{quote(name)}.{quote(c.name)}", c.description)
                    for c in entity.columns if c.description and c.name in emitted]


def _foreign_key(rel: RelationshipSchema, entity_columns: dict[str, set[str]],
                 gaps: list[ExportGap]) -> str | None:
    label = f"{rel.from_ref}({', '.join(rel.from_columns)}) -> {rel.to_ref}({', '.join(rel.to_columns)})"
    if not rel.resolved:
        gaps.append(ExportGap("unresolved_relationship", rel.from_ref,
                              f"{label}: its columns are not all chosen, so there is no foreign key to state"))
        return None
    if rel.to_ref not in entity_columns:
        gaps.append(ExportGap("foreign_key", rel.from_ref, f"{label}: {rel.to_ref} is not a table in this model"))
        return None
    missing = [c for c in rel.from_columns if c not in entity_columns[rel.from_ref]] + [
        f"{rel.to_ref}.{c}" for c in rel.to_columns if c not in entity_columns[rel.to_ref]]
    if missing:
        gaps.append(ExportGap("foreign_key", rel.from_ref, f"{label}: columns {missing} are not emitted"))
        return None
    return f"FOREIGN KEY ({_columns(rel.from_columns)}) REFERENCES {quote(rel.to_ref)} ({_columns(rel.to_columns)})"
