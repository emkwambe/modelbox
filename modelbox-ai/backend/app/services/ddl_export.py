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
from dataclasses import asdict, dataclass, field

import sqlglot
from sqlglot import exp

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SequenceSchema,
    SynthesizedModel,
)

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
_NEXTVAL = re.compile(r"\bNEXTVAL\s*\(", re.IGNORECASE)

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
    # Each statement, in order, without a terminator (CREATE EXTENSION, CREATE
    # SEQUENCE, CREATE TABLE, ALTER TABLE, COMMENT ON): what the file holds,
    # one statement at a time, for a caller that applies it.
    statements: list[str] = field(default_factory=list)


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
    expression: str, source: str, target: str, columns: list[str] | None = None,
    boolean_columns: set[str] | None = None,
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
    # The parentheses were added here to parse it; CHECK (…) adds its own.
    if isinstance(condition, exp.Paren):
        condition = condition.this
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
    if boolean_columns:
        # A SQL Server bit column is BOOLEAN in the target, where 0 and 1 are
        # not its values: (Flag = 1) is written (Flag = TRUE).
        condition = _as_boolean_literals(condition, boolean_columns)
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
#
# Each was found by applying the export to PostgreSQL 16.15 (Step 4a): a type
# sqlglot's own parser accepts can still be one PostgreSQL refuses, or one
# whose operators do not match the CHECKs written against it.
_TYPE_GAPS: dict[str, dict[str, tuple[str | None, str]]] = {  # keyed by sqlglot type name
    "postgres": {
        "UTINYINT": ("SMALLINT", "PostgreSQL has no one-byte integer; emitted as SMALLINT"),
    },
}


@dataclass(frozen=True)
class TypeMapping:
    """A source type written as an exact equivalent in the target (Sprint 9 Step 1a).

    ``source`` None applies to every source dialect. ``extension`` names the
    target extension the replacement needs; such a mapping applies only when
    the export states that the target has it, and the export then starts with
    ``CREATE EXTENSION IF NOT EXISTS``. A mapped column is not a gap.
    """

    source: str | None
    target: str
    type: str  # sqlglot's type name, or a user-defined type's name, upper case
    replacement: str
    extension: str | None = None


TYPE_MAPPINGS: tuple[TypeMapping, ...] = (
    # SQL Server's money is exact to four places over about ±922 trillion,
    # which NUMERIC(19, 4) holds exactly; PostgreSQL's own money is
    # locale-formatted and has no operators against numeric. smallmoney
    # (±214,748.3648) fits NUMERIC(10, 4) exactly (owner, 2026-09-30).
    TypeMapping("tsql", "postgres", "MONEY", "DECIMAL(19, 4)"),
    TypeMapping("tsql", "postgres", "SMALLMONEY", "DECIMAL(10, 4)"),
    # SQL Server's bit is a 0/1 flag; PostgreSQL's BIT is a bit string. Its
    # 0 and 1 in defaults and CHECKs are written FALSE and TRUE.
    TypeMapping("tsql", "postgres", "BIT", "BOOLEAN"),
    # AWS documents ltree as the target for hierarchyid; ltree ships with
    # PostgreSQL as a contrib extension, and PostGIS is not part of it at all.
    TypeMapping(None, "postgres", "HIERARCHYID", "LTREE", extension="ltree"),
    TypeMapping(None, "postgres", "GEOGRAPHY", "GEOGRAPHY", extension="postgis"),
)

# Each extension a mapping can rely on, and the export option that says the
# target has it.
EXTENSION_OPTIONS: dict[str, str] = {"ltree": "target_has_ltree", "postgis": "target_has_postgis"}

# Source types the target would refuse or misread as written. Without a
# mapping that applies (none defined, or its extension not declared), each is
# written as the fallback and named as a gap: never a silent TEXT, and never
# the source's name for a different target type.
_UNMAPPED: dict[tuple[str | None, str], dict[str, tuple[str, str]]] = {
    ("tsql", "postgres"): {
        "MONEY": ("TEXT", "SQL Server money has no mapping to PostgreSQL in this export; emitted as TEXT"),
        "SMALLMONEY": ("TEXT", "SQL Server smallmoney has no mapping to PostgreSQL in this export; emitted as TEXT"),
        "BIT": ("TEXT", "SQL Server bit has no mapping to PostgreSQL in this export; emitted as TEXT"),
    },
    (None, "postgres"): {
        "HIERARCHYID": ("VARCHAR", ("PostgreSQL has no HIERARCHYID; emitted as VARCHAR, which holds its string "
                                    "form ('/1/3/'). Export with target_has_ltree to write it as LTREE")),
        "GEOGRAPHY": ("TEXT", ("GEOGRAPHY needs the PostGIS extension; emitted as TEXT, which holds its WKT "
                               "form. Export with target_has_postgis to write it as PostGIS GEOGRAPHY")),
    },
}
# A schema-qualified user-defined type the model does not define (a domain or
# enum the import listed but did not bring in) cannot be created by this file.
_UNDEFINED_USER_TYPE: dict[str, tuple[str, str]] = {
    "postgres": ("TEXT", "is a user-defined type the model does not define; emitted as TEXT"),
}
_MAX_PRECISION: dict[str, int] = {"postgres": 6}
_TEMPORAL = frozenset({"TIMESTAMP", "TIME", "TIMESTAMPTZ", "DATETIME2", "DATETIME", "TIMETZ"})


def _as_boolean_default(column: exp.ColumnDef) -> None:
    """A 0/1 default on a column now BOOLEAN, as FALSE/TRUE (the same value)."""
    for constraint in column.args.get("constraints") or []:
        default = constraint.args.get("kind")
        if not isinstance(default, exp.DefaultColumnConstraint):
            continue
        value = default.this
        while isinstance(value, exp.Paren):
            value = value.this
        if isinstance(value, exp.Literal) and value.name in ("0", "1"):
            default.set("this", exp.true() if value.name == "1" else exp.false())


def _uncast_default(column: exp.ColumnDef, written: exp.DataType) -> bool:
    """Remove casts to ``written`` from the column's default; True if any was removed.

    Pagila's ``rating mpaa_rating DEFAULT 'G'::mpaa_rating``: once the column
    is TEXT, the cast still names the type the file does not create.
    """
    removed = False
    for constraint in column.args.get("constraints") or []:
        default = constraint.args.get("kind")
        if not isinstance(default, exp.DefaultColumnConstraint):
            continue
        for cast in list(default.find_all(exp.Cast)):
            if cast.to == written:
                cast.replace(cast.this)
                removed = True
    return removed


def _type_name(kind: exp.DataType) -> str:
    """The name mappings are keyed by: sqlglot's type, or a user-defined type's own name."""
    return kind.sql().upper() if kind.this == exp.DataType.Type.USERDEFINED else kind.this.name


def mapping_for(type_name: str, source: str, target: str, extensions: frozenset[str]) -> TypeMapping | None:
    """The mapping that applies to ``type_name`` from ``source`` to ``target``, if any."""
    for mapping in TYPE_MAPPINGS:
        if (mapping.type == type_name and mapping.target == target and mapping.source in (None, source)
                and (mapping.extension is None or mapping.extension in extensions)):
            return mapping
    return None


def _fit_type(column: exp.ColumnDef, entity: str, target: str, gaps: list[ExportGap],
              source: str = "", extensions: frozenset[str] = frozenset()) -> str | None:
    """Replace or annotate a translated type the target cannot hold as written.

    Returns the replacement type where a mapping applied (an exact equivalent,
    so not a gap), else None.
    """
    kind = column.args.get("kind")
    if not isinstance(kind, exp.DataType):
        return None
    name = _type_name(kind)
    mapping = mapping_for(name, source, target, extensions)
    if mapping is not None:
        column.set("kind", exp.DataType.build(mapping.replacement, dialect=target, udt=True))
        if mapping.replacement == "BOOLEAN":
            _as_boolean_default(column)
        return mapping.replacement
    unmapped = _UNMAPPED.get((source, target), {}).get(name) or _UNMAPPED.get((None, target), {}).get(name)
    if unmapped is not None:
        written = kind.sql(dialect=target)
        column.set("kind", exp.DataType.build(unmapped[0], dialect=target))
        gaps.append(ExportGap("data_type", entity, f"{column.name} {written}: {unmapped[1]}"))
        return None
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
        if "." in kind.sql() and (undefined := _UNDEFINED_USER_TYPE.get(target)) is not None:
            # Schema-qualified, as pg_dump writes a type it created. An
            # unqualified name (Pagila's tsvector) is a type sqlglot does not
            # know but the target may: written as is, and applying the export
            # to PostgreSQL (test_ddl_on_postgres) is what checks it.
            column.set("kind", exp.DataType.build(undefined[0], dialect=target))
            uncast = _uncast_default(column, kind)
            gaps.append(ExportGap("data_type", entity, f"{column.name} {written} {undefined[1]}"
                                  + ("; the cast to it in the default is removed" if uncast else "")))
    limit = _MAX_PRECISION.get(target)
    if limit is not None and kind.this.name in _TEMPORAL and len(params) == 1 and params[0].name.isdigit() \
            and int(params[0].name) > limit:
        kind.set("expressions", [exp.DataTypeParam(this=exp.Literal.number(limit))])
        gaps.append(ExportGap("data_type", entity,
                              f"{column.name} {written}: {target} keeps at most {limit} fractional digits"))
    return None


# PostgreSQL accepts an identity column only on these types.
_IDENTITY_TYPES = frozenset({exp.DataType.Type.SMALLINT, exp.DataType.Type.INT, exp.DataType.Type.BIGINT})
_NEXTVAL_ARGUMENT = re.compile(r"\bNEXTVAL\s*\(\s*(?:CAST\s*\(\s*)?'([^']+)'", re.IGNORECASE)


def _name_parts(name: str) -> tuple[str, ...]:
    """A dotted name as PostgreSQL reads it: quoted parts exact, unquoted folded to lower case."""
    parts = re.findall(r'"((?:[^"]|"")*)"|([^.\s]+)', name)
    return tuple(quoted.replace('""', '"') if quoted else plain.lower() for quoted, plain in parts)


def sequence_named_by(default: str) -> tuple[str, ...] | None:
    """The sequence a ``nextval('…')`` default names, as name parts; None if it names none."""
    match = _NEXTVAL_ARGUMENT.search(default)
    return _name_parts(match.group(1)) if match else None


def _sequence_statement(sequence: SequenceSchema) -> str:
    """CREATE SEQUENCE for PostgreSQL, with what the source declared; an unset option keeps its default."""
    clauses = [f"CREATE SEQUENCE {'.'.join(quote(part) for part in sequence.name.split('.'))}"]
    if sequence.start is not None:
        clauses.append(f"START WITH {sequence.start}")
    if sequence.increment is not None:
        clauses.append(f"INCREMENT BY {sequence.increment}")
    if sequence.min_value is not None:
        clauses.append(f"MINVALUE {sequence.min_value}")
    if sequence.max_value is not None:
        clauses.append(f"MAXVALUE {sequence.max_value}")
    if sequence.cache is not None:
        clauses.append(f"CACHE {sequence.cache}")
    if sequence.cycle:
        clauses.append("CYCLE")
    return " ".join(clauses)


def _plain_name(*parts: str) -> str:
    """A lower-case snake-case identifier built from ``parts``, as a generated sequence's name."""
    return re.sub(r"[^a-z0-9_]+", "_", "_".join(parts).lower()).strip("_")[:63]


def _state_identity(column_def: exp.ColumnDef, column: ColumnSchema, entity: str, target: str,
                    gaps: list[ExportGap], generated: list[SequenceSchema], taken: set[str]) -> None:
    """Write a column's identity for ``target``, or name why it cannot be.

    PostgreSQL: ``GENERATED BY DEFAULT AS IDENTITY`` with the source's seed
    and increment, BY DEFAULT so a data migration can load existing values. A
    column whose type is not an integer (Oracle's ``NUMBER(*,0)``) cannot be
    an identity column there, so it takes a sequence default with the same
    start and increment instead, named as a gap (owner, 2026-09-30). An Oracle
    column a trigger fills from a sequence is a gap: the trigger is not in the
    model.
    """
    identity = column.identity
    if identity is None:
        return
    if identity.kind == "trigger":
        gaps.append(ExportGap("identity", entity, (
            f"{column.name} is filled on insert by trigger {identity.trigger} from sequence "
            f"{identity.sequence}; the trigger is not in the model, so no value is generated")))
        return
    seed = f"START WITH {identity.start}" if identity.start is not None else ""
    step = f"INCREMENT BY {identity.increment}" if identity.increment is not None else ""
    declared = " ".join(p for p in (f"GENERATED {identity.generation} AS IDENTITY", seed, step) if p)
    if target != "postgres":
        gaps.append(ExportGap("identity", entity, f"{column.name} {declared}: not emitted for {target}"))
        return
    notes: list[str] = []
    if identity.generation == "ALWAYS":
        notes.append("GENERATED ALWAYS in the source, emitted BY DEFAULT so a data migration can load "
                     "existing values")
    if identity.on_null:
        notes.append("ON NULL has no PostgreSQL equivalent, so an explicit NULL is refused rather than numbered")
    kind = column_def.args.get("kind")
    if isinstance(kind, exp.DataType) and kind.this in _IDENTITY_TYPES:
        column_def.append("constraints", exp.ColumnConstraint(kind=exp.GeneratedAsIdentityColumnConstraint(
            this=False,
            start=exp.Literal.number(identity.start) if identity.start is not None else None,
            increment=exp.Literal.number(identity.increment) if identity.increment is not None else None)))
        if notes:
            gaps.append(ExportGap("identity", entity, f"{column.name}: " + "; ".join(notes)))
        return
    if column_def.find(exp.DefaultColumnConstraint) is not None:
        gaps.append(ExportGap("identity", entity, f"{column.name} {declared}: the column also has a DEFAULT, "
                                                  "so neither an identity nor a sequence default is emitted"))
        return
    name = base = _plain_name(entity, column.name, "seq")
    suffix = 1
    while name in taken:
        suffix += 1
        name = f"{base[:60]}_{suffix}"
    taken.add(name)
    generated.append(SequenceSchema(name=name, start=identity.start, increment=identity.increment))
    default = sqlglot.parse_one(f"SELECT nextval('{name}')", read="postgres").expressions[0]
    column_def.append("constraints", exp.ColumnConstraint(kind=exp.DefaultColumnConstraint(this=default)))
    written = kind.sql(dialect=target) if isinstance(kind, exp.DataType) else "its type"
    gaps.append(ExportGap("identity", entity, "; ".join([
        (f"{column.name} {declared} on {written}: PostgreSQL allows an identity column only on smallint, integer "
         f"or bigint, so it is emitted as DEFAULT nextval('{name}') with the same start and increment"),
        *notes])))


def _as_boolean_literals(condition: exp.Expression, flags: set[str]) -> exp.Expression:
    """In a CHECK over columns now BOOLEAN, a comparison with 0 or 1 compares with FALSE or TRUE."""
    def literal(node: exp.Expression) -> exp.Expression | None:
        while isinstance(node, exp.Paren):
            node = node.this
        if isinstance(node, exp.Literal) and not node.is_string and node.name in ("0", "1"):
            return exp.true() if node.name == "1" else exp.false()
        return None

    def is_flag(node: exp.Expression) -> bool:
        while isinstance(node, exp.Paren):
            node = node.this
        return isinstance(node, exp.Column) and node.name in flags

    for node in list(condition.walk()):
        if isinstance(node, (exp.EQ, exp.NEQ)):
            for side, other in (("this", "expression"), ("expression", "this")):
                if is_flag(node.args[other]) and (value := literal(node.args[side])) is not None:
                    node.set(side, value)
        elif isinstance(node, exp.In) and is_flag(node.this):
            node.set("expressions", [literal(e) or e for e in node.expressions])
    return condition


# Targets that add a foreign key to an existing table with ALTER TABLE.
_ALTER_ADDS_FOREIGN_KEYS = frozenset({"postgres", "snowflake", "redshift", "databricks"})


def _alter_foreign_key(table: str, clause: str, target: str) -> str:
    """ALTER TABLE … ADD <clause>, checked to parse as exactly that in ``target``."""
    statement = f"ALTER TABLE {quote(table)} ADD {clause}"
    tree = sqlglot.parse_one(statement, read=target)
    if not isinstance(tree, exp.Alter):
        raise DdlExportError(f"foreign key {statement!r} does not parse as {target}")
    return tree.sql(dialect=target)


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


def build_ddl(model: SynthesizedModel, target: str, source: str,
              extensions: frozenset[str] = frozenset()) -> DdlExport:
    """CREATE TABLE and COMMENT ON statements for ``model`` in ``target``.

    ``extensions`` are the target extensions the export may rely on
    (``ltree``, ``postgis``): the caller's explicit statement that the target
    has them, never assumed. Each is created first with ``CREATE EXTENSION IF
    NOT EXISTS``, and the mappings that need it apply.
    """
    from app.services.sql_fragments import column_problems

    unknown = sorted(extensions - set(EXTENSION_OPTIONS))
    if unknown:
        raise DdlExportError(f"unknown target extension(s): {', '.join(unknown)}")
    if extensions and target != "postgres":
        raise DdlExportError(f"{', '.join(EXTENSION_OPTIONS[e] for e in sorted(extensions))} applies "
                             f"to a PostgreSQL export only, not {target}")
    can = _CAPABILITIES.get(target, frozenset())
    gaps: list[ExportGap] = []
    tables: list[str] = []
    deferred: list[str] = []  # foreign keys closing a cycle, added after every table
    created: set[str] = set()
    comments: list[str] = []
    entity_columns = {e.entity_name: {c.name for c in e.columns if c.data_type != COMPUTED} for e in model.entities}
    # A PostgreSQL model's sequences are created by the export, so its
    # nextval defaults keep working: PostgreSQL refuses a default that names a
    # sequence the file does not create. From any other source a sequence is
    # not emitted (its options need not hold in PostgreSQL: Oracle's MAXVALUE
    # exceeds bigint), and a default that names one is a gap.
    keeps_sequences = source == target == "postgres"
    held = {_name_parts(s.name): s for s in model.sequences}
    generated: list[SequenceSchema] = []  # sequence defaults standing in for identity columns
    taken = {parts[-1] for parts in held}

    for entity in _order(model):
        name = entity.entity_name
        emitted = entity_columns[name]
        by_column = {c.name: c for c in entity.columns}
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
            default = column.default_value
            if default and _NEXTVAL.search(default) and not (keeps_sequences and sequence_named_by(default) in held):
                # A sequence this file does not create: PostgreSQL refuses a
                # default that names it.
                why = ("the model does not hold" if keeps_sequences
                       else f"this export does not create from a {source} model")
                gaps.append(ExportGap("default", name, f"{column.name} DEFAULT {default} names a sequence "
                                                       f"{why}; the default is not emitted"))
                default = None
            lines.append(f"    {quote(column.name)} {column.data_type}"
                         + (f" DEFAULT {default}" if default else "")
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
        flags: set[str] = set()  # columns now BOOLEAN, whose 0 and 1 are FALSE and TRUE
        for column_def in tree.this.expressions:
            if _fit_type(column_def, name, target, gaps, source, extensions) == "BOOLEAN":
                flags.add(column_def.name)
            if column_def.name in by_column:
                _state_identity(column_def, by_column[column_def.name], name, target, gaps, generated, taken)

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
                                                     [c.name for c in entity.columns], flags)
                if problem is not None:
                    gaps.append(ExportGap("check_constraint", name, f"{label} {problem}"))
                else:
                    clauses.append(f"{_named(check.name)}CHECK ({condition})")
        for rel in model.relationships:
            if rel.from_ref != name or (clause := _foreign_key(rel, entity_columns, gaps)) is None:
                continue
            if rel.to_ref in created or rel.to_ref == name:
                clauses.append(f"{_named(rel.name)}{clause}")
            elif target in _ALTER_ADDS_FOREIGN_KEYS:
                # The referenced table is created later: the model has a
                # foreign-key cycle (HR's DEPARTMENTS and EMPLOYEES), so no
                # order creates every referenced table first. Added once every
                # table exists.
                deferred.append(_alter_foreign_key(name, f"{_named(rel.name)}{clause}", target))
            else:
                gaps.append(ExportGap("foreign_key", name, f"{rel.from_ref} -> {rel.to_ref}: the model has a "
                                                           "foreign-key cycle, the referenced table is created "
                                                           f"later, and {target} cannot add a foreign key once a "
                                                           "table exists"))
        for clause in clauses:
            tree.this.append("expressions", _constraint_node(clause, target))
        tables.append(tree.sql(dialect=target, pretty=True))
        created.add(name)

        descriptions = _descriptions(entity, emitted)
        if descriptions and "comment" not in can:
            gaps.append(ExportGap("description", name,
                                  f"{len(descriptions)} descriptions: {target} has no COMMENT ON"))
        elif descriptions:
            comments += [f"COMMENT ON {kind} {target_name} IS '{text.replace(chr(39), chr(39) * 2)}'"
                         for kind, target_name, text in descriptions]

    if not keeps_sequences:
        gaps += [ExportGap("sequence", None, f"{s.name}: not emitted; sequences are created only for a "
                                             f"PostgreSQL model exported to PostgreSQL ({source} to {target})")
                 for s in model.sequences]
    # Extensions first, then sequences, which the tables' defaults name.
    prelude = [f"CREATE EXTENSION IF NOT EXISTS {extension}" for extension in sorted(extensions)]
    prelude += [_sequence_statement(s) for s in (model.sequences if keeps_sequences else [])]
    prelude += [_sequence_statement(s) for s in generated]
    statements = prelude + tables + deferred + comments
    body = ";\n\n".join(statements) + ";\n"
    if gaps:
        header = [f"-- Export gaps ({len(gaps)}): what the model holds that this file does not state."]
        header += ["-- " + " ".join(f"{g.kind} [{g.entity}]: {g.detail}".split()) for g in gaps]
        body = "\n".join(header) + "\n\n" + body
    return DdlExport(sql=body, gaps=gaps, statements=statements)


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
