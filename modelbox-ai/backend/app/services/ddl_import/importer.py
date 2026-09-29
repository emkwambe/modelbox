"""Import an exported DDL file into the model IR, and reconcile it.

The pipeline, for one file:

1. **decode** (``encoding``): UTF-8 or UTF-16, with or without a BOM;
2. **split** (``splitter``): statements, with client lines and procedural
   objects classified, never dropped;
3. **classify** every SQL statement by its leading words. Statements that are
   not part of a logical model (session settings, ownership, privileges,
   indexes, sequences, views, domains, extensions, schemas) are **skipped by a
   named rule** and listed in the report. ``ALTER TABLE … ATTACH PARTITION`` is
   read by its own extractor. Everything else is parsed;
4. **parse** (``parse_statement``, the only place sqlglot is called), after the
   Oracle normalizer. A ``Command`` for ``CREATE TABLE``, ``ALTER TABLE``,
   ``COMMENT`` or ``CREATE TYPE`` is a named import failure: sqlglot returns
   ``Command`` for what it does not understand, so accepting it would drop the
   statement while reporting success;
5. **build** the IR: tables become entities; partitions are metadata of their
   parent, not entities; constraints the IR cannot hold (a UNIQUE or CHECK
   over several columns, a composite foreign key) are **held** in the report
   with the reason, not lost;
6. **reconcile** (``counter``): the counts taken independently of all the
   above against what the import produced, table by table. Any difference is
   a gap, listed with the statements that declare that table.

An import is ``reconciled`` only with no failures and no gaps.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.schemas.data_model import (
    Cardinality,
    CheckConstraintSchema,
    ColumnSchema,
    EntitySchema,
    EntityType,
    Paradigm,
    RelationshipSchema,
    SynthesizedModel,
    UniqueConstraintSchema,
    columns_read_by,
)
from app.services.ddl_import import (
    counter,
    oracle_normalizer,
    splitter,
    sqlserver_normalizer,
)
from app.services.ddl_import.dialects import IMPORT_DIALECTS
from app.services.ddl_import.encoding import DecodeError, decode

logger = logging.getLogger(__name__)

DIALECTS = tuple(IMPORT_DIALECTS)
_SQLGLOT_DIALECT = {"oracle": "oracle", "postgres": "postgres", "snowflake": "snowflake", "tsql": "tsql"}

# SQL Server types sqlglot reads as user-defined names. Each is typed here,
# never left untyped: sysname is SQL Server's alias for nvarchar(128).
_BUILTIN_SPECIAL_TYPES = {"sysname": "NVARCHAR(128)", "hierarchyid": "HIERARCHYID"}

# Statement kinds whose Command result must never be accepted.
GUARDED_KINDS = ("create_table", "alter_table", "comment", "create_type")

# Table modifiers any importable dialect writes before TABLE (Snowflake's
# HYBRID and TRANSIENT among them). The counter reads the same words.
_TABLE_MODIFIERS = r"(?:(?:GLOBAL|LOCAL|TEMP|TEMPORARY|UNLOGGED|HYBRID|TRANSIENT|VOLATILE)\s+)*"
_GUARDED = (
    ("create_table", re.compile(rf"^CREATE\s+(?:OR\s+REPLACE\s+)?{_TABLE_MODIFIERS}TABLE\b", re.IGNORECASE)),
    ("alter_table", re.compile(r"^ALTER\s+TABLE\b", re.IGNORECASE)),
    ("comment", re.compile(r"^COMMENT\s+ON\b", re.IGNORECASE)),
    ("create_type", re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?TYPE\b", re.IGNORECASE)),
)

# Named skip rules: statements that are not part of a logical model. Each is
# anchored at the statement's start, so none can match a guarded kind, and the
# ALTER forms only match when the whole statement is that one action.
_PART = r"(?:\"[^\"]+\"|\[[^\]]+\]|[\w$#]+)"
_NAME = rf"{_PART}(?:\s*\.\s*{_PART})*"
SKIP_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("session setting", re.compile(r"^(?:SET\s|RESET\s|SELECT\s+pg_catalog\.set_config\s*\()", re.IGNORECASE)),
    ("ownership", re.compile(
        rf"^ALTER\s+(?:TABLE|SCHEMA|SEQUENCE|VIEW|MATERIALIZED\s+VIEW|FUNCTION|PROCEDURE|AGGREGATE|TYPE|DOMAIN)"
        rf"\s+(?:ONLY\s+)?{_NAME}(?:\s*\([^;]*\))?\s+OWNER\s+TO\s+\S+\s*;?\s*$", re.IGNORECASE)),
    ("privileges", re.compile(r"^(?:GRANT|REVOKE)\s", re.IGNORECASE)),
    ("index", re.compile(
        r"^(?:CREATE\s+(?:UNIQUE\s+)?(?:BITMAP\s+|PRIMARY\s+XML\s+|XML\s+|SPATIAL\s+|(?:NON)?CLUSTERED\s+)?"
        r"(?:COLUMNSTORE\s+)?INDEX|ALTER\s+INDEX)\b", re.IGNORECASE)),
    # T-SQL: enabling or disabling a constraint that already exists. The whole
    # statement must be that one action; adding a constraint is never this.
    ("constraint state", re.compile(
        rf"^ALTER\s+TABLE\s+{_NAME}\s+(?:WITH\s+(?:NO)?CHECK\s+)?(?:NO)?CHECK\s+CONSTRAINT\s+(?:ALL|{_NAME})\s*;?\s*$",
        re.IGNORECASE)),
    ("database selection", re.compile(r"^USE\s", re.IGNORECASE)),
    ("sequence", re.compile(r"^(?:CREATE|ALTER)\s+SEQUENCE\b", re.IGNORECASE)),
    ("view", re.compile(r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:FORCE\s+)?(?:MATERIALIZED\s+)?VIEW|ALTER\s+(?:MATERIALIZED\s+)?VIEW)\b", re.IGNORECASE)),
    ("domain", re.compile(r"^(?:CREATE|ALTER)\s+DOMAIN\b", re.IGNORECASE)),
    ("extension", re.compile(r"^(?:CREATE|ALTER|COMMENT\s+ON)\s+EXTENSION\b", re.IGNORECASE)),
    ("schema", re.compile(r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?|ALTER\s+)SCHEMA\b", re.IGNORECASE)),
    ("synonym", re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:PUBLIC\s+)?SYNONYM\b", re.IGNORECASE)),
    ("drop", re.compile(r"^DROP\s", re.IGNORECASE)),
)
_LATER_TABLE_STATEMENT = re.compile(
    r"\n\s*(?:CREATE|ALTER|COMMENT)\b[^;(\n]{0,120}?\bTABLE\b|\bsp_addextendedproperty\b", re.IGNORECASE)
_LOOKS_LIKE_TABLE = re.compile(r"^(?:CREATE|ALTER|COMMENT|DROP)\b[^;(]{0,120}?\bTABLE\b", re.IGNORECASE | re.DOTALL)
_ATTACH = re.compile(
    rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?(?P<parent>{_NAME})\s+ATTACH\s+PARTITION\s+(?P<child>{_NAME})\s+"
    r"(?P<bound>FOR\s+VALUES\s+.+|DEFAULT)\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
# The three T-SQL forms the parser returns as an opaque Command, each read by
# its own extractor. A statement that starts like one but does not match it
# whole is a named failure.
_TYPE_ALIAS = re.compile(
    rf"^CREATE\s+TYPE\s+(?P<name>{_NAME})\s+FROM\s+(?P<base>.+?)(?:\s+(?P<null>NOT\s+NULL|NULL))?\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_ADD_DEFAULT = re.compile(
    rf"^ALTER\s+TABLE\s+(?P<table>{_NAME})\s+ADD\s+(?:CONSTRAINT\s+{_NAME}\s+)?DEFAULT\s+(?P<expr>.+?)\s+"
    rf"FOR\s+(?P<column>{_NAME})\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_EXTENDED_PROPERTY = re.compile(r"^EXEC(?:UTE)?\s+(?:sys\s*\.\s*)?sp_addextendedproperty\b", re.IGNORECASE)
_PARAM = re.compile(r"@(\w+)\s*=\s*N?'((?:[^']|'')*)'", re.IGNORECASE)
_POSITIONAL = re.compile(r"N?'((?:[^']|'')*)'")
_PROPERTY_KEYS = ("name", "value", "level0type", "level0name", "level1type", "level1name", "level2type", "level2name")

# Where a column's declared type ends: the first constraint or property word
# after it, outside parentheses, quotes and brackets.
_TYPE_END = re.compile(
    r"(?:NOT|NULL|CONSTRAINT|DEFAULT|IDENTITY|PRIMARY|UNIQUE|CHECK|REFERENCES|COLLATE|GENERATED|ENABLE|DISABLE"
    r"|ROWGUIDCOL|SPARSE|FILESTREAM|MASKED|ENCRYPTED|AS)\b",
    re.IGNORECASE,
)
_ITEM_IS_CONSTRAINT = re.compile(
    r"^(?:CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|EXCLUDE|LIKE|PERIOD|SUPPLEMENTAL)\b", re.IGNORECASE)
_COLUMN_NAME = re.compile(r"^(\"[^\"]+\"|\[[^\]]+\]|[\w$#]+)\s*")


class ImportFailure(Exception):
    """A statement could not be imported; the message says why."""


@dataclass
class _Column:
    name: str
    data_type: str
    nullable: bool = True
    default: str | None = None
    checks: list[str] = field(default_factory=list)
    unique: bool = False
    primary_key: bool = False
    description: str | None = None
    source_type: str | None = None  # the declaration exactly as the file wrote it
    user_type: str | None = None  # a user-defined type name, resolved in _to_model
    computed: str | None = None  # a computed column's expression


@dataclass
class _Table:
    name: str
    statement: int
    columns: dict[str, _Column] = field(default_factory=dict)
    primary_key: list[str] = field(default_factory=list)
    primary_key_count: int = 0
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)
    uniques: list[tuple[str | None, list[str]]] = field(default_factory=list)  # (name, columns)
    checks: list[tuple[str | None, str]] = field(default_factory=list)  # table-level (name, SQL)
    description: str | None = None
    partitioning: str | None = None
    statements: list[int] = field(default_factory=list)


@dataclass
class ImportResult:
    dialect: str
    encoding: str
    status: str
    model: SynthesizedModel | None
    report: dict[str, Any]


def _bare(identifier: exp.Expression | None) -> str:
    if identifier is None:
        return ""
    if isinstance(identifier, exp.Table | exp.Column):
        return identifier.name
    return identifier.name if hasattr(identifier, "name") else str(identifier)


def _bare_text(name: str) -> str:
    parts = re.findall(r"\"([^\"]+)\"|\[([^\]]+)\]|([\w$#]+)", name)
    return next(p for p in parts[-1] if p)


def _top_level_items(body: str) -> list[str]:
    """Split a parenthesised list at its top-level commas, respecting quotes and brackets."""
    items: list[str] = []
    depth, start, i, n = 0, 0, 0, len(body)
    while i < n:
        ch = body[i]
        if ch in "'\"[":
            close = {"'": "'", '"': '"', "[": "]"}[ch]
            j = body.find(close, i + 1)
            while ch == "'" and j != -1 and j + 1 < n and body[j + 1] == "'":
                j = body.find("'", j + 2)
            i = n if j == -1 else j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append(body[start:i])
            start = i + 1
        i += 1
    items.append(body[start:])
    return [item.strip() for item in items if item.strip()]


def _type_text(rest: str) -> str | None:
    """A column's type as written: from after its name to the first constraint word."""
    depth, i, n = 0, 0, len(rest)
    while i < n:
        ch = rest[i]
        if ch in "'\"[":
            close = {"'": "'", '"': '"', "[": "]"}[ch]
            j = rest.find(close, i + 1)
            i = n if j == -1 else j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and (i == 0 or rest[i - 1].isspace()) and _TYPE_END.match(rest, i):
            break
        i += 1
    text = rest[:i].rstrip()
    return text or None


def declared_types(statement: str) -> dict[str, str | None]:
    """Each column's type exactly as a CREATE TABLE statement declares it, by column name.

    Read from the statement's own text, before any normalizing, so what is
    stored is what the file said: ``VARCHAR2(10 BYTE)``, ``[nvarchar](60)``,
    ``integer``. A computed column declares no type, and maps to None.
    """
    open_at = statement.find("(")
    if open_at == -1:
        return {}
    depth, end = 0, len(statement)
    for i in range(open_at, len(statement)):
        if statement[i] == "(":
            depth += 1
        elif statement[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    found: dict[str, str | None] = {}
    for item in _top_level_items(statement[open_at + 1:end]):
        if _ITEM_IS_CONSTRAINT.match(item) or (name := _COLUMN_NAME.match(item)) is None:
            continue
        found[_bare_text(name.group(1))] = _type_text(item[name.end():])
    return found


def _extended_property(text: str) -> dict[str, str]:
    """sp_addextendedproperty's arguments, named or positional."""
    named = {key.lower(): value.replace("''", "'") for key, value in _PARAM.findall(text)}
    if named:
        return named
    values = [value.replace("''", "'") for value in _POSITIONAL.findall(text)]
    return dict(zip(_PROPERTY_KEYS, values, strict=False))


def classify(statement: splitter.Statement) -> tuple[str, str | None]:
    """(kind, skip reason) for one statement."""
    if statement.kind != "sql":
        return statement.kind, None
    text = statement.text.lstrip()
    for name, pattern in SKIP_RULES:
        if pattern.match(text):
            if _LATER_TABLE_STATEMENT.search(text):
                # A T-SQL batch can hold several statements: one a rule skips
                # must not carry a table statement past the importer with it.
                return "unrecognized_table", None
            return "skipped", name
    if _ATTACH.match(text) or re.match(r"^ALTER\s+TABLE\b[^;]*\bATTACH\s+PARTITION\b", text, re.IGNORECASE | re.DOTALL):
        return "attach_partition", None
    if _EXTENDED_PROPERTY.match(text):
        return "extended_property", None
    if _TYPE_ALIAS.match(text):
        return "type_alias", None
    if _ADD_DEFAULT.match(text):
        return "add_default", None
    for kind, pattern in _GUARDED:
        if pattern.match(text):
            return kind, None
    if _LOOKS_LIKE_TABLE.match(text):
        # Never skip what might define or change a table: a form no rule
        # recognises is a failure the report names, not a quiet skip.
        return "unrecognized_table", None
    return "skipped", "not a table-level statement"


def parse_statement(text: str, dialect: str, kind: str) -> exp.Expr:
    """Parse one statement; the only call into sqlglot in the importer.

    A guarded kind that parses to ``Command`` (or to nothing) is a failure,
    never a skip.
    """
    try:
        parsed = [tree for tree in sqlglot.parse(text, read=_SQLGLOT_DIALECT[dialect]) if tree is not None]
    except SqlglotError as exc:
        raise ImportFailure(f"does not parse as {dialect}: {str(exc).splitlines()[0]}") from exc
    if len(parsed) != 1:
        raise ImportFailure(f"parsed as {len(parsed)} statements, not one")
    tree = parsed[0]
    if isinstance(tree, exp.Command) and kind in GUARDED_KINDS:
        raise ImportFailure(
            "the parser did not understand this statement (it returned an opaque Command); "
            "importing it would drop it silently"
        )
    return tree


def _column_names(nodes: list[exp.Expression]) -> list[str]:
    return [node.name for node in nodes]


class _Builder:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.tables: dict[str, _Table] = {}
        self.partitions: dict[str, dict[str, Any]] = {}  # child -> {parent, bound, statement}
        self.types: list[dict[str, Any]] = []
        # T-SQL CREATE TYPE … FROM: alias (lower-cased bare name) -> base type.
        self.aliases: dict[str, dict[str, Any]] = {}
        self.nocheck: list[dict[str, Any]] = []  # constraints added WITH NOCHECK

    def _table(self, name: str, statement: splitter.Statement) -> _Table:
        table = self.tables.get(name)
        if table is None:
            raise ImportFailure(f"refers to table {name!r}, which no CREATE TABLE in this file defines")
        table.statements.append(statement.index)
        return table

    def _sql(self, node: exp.Expression) -> str:
        return node.sql(dialect=_SQLGLOT_DIALECT[self.dialect])

    def _constraint(self, table: _Table, node: exp.Expression, statement: splitter.Statement,
                    name: str | None = None) -> None:
        if isinstance(node, exp.Constraint):
            for inner in node.expressions:
                self._constraint(table, inner, statement, node.name or None)
            return
        if isinstance(node, exp.PrimaryKey):
            table.primary_key = _column_names(node.expressions)
            table.primary_key_count += 1
        elif isinstance(node, exp.ForeignKey):
            reference = node.args.get("reference")
            target = reference.this if reference is not None else None
            table.foreign_keys.append({
                "name": name,
                "columns": _column_names(node.expressions),
                "references": _bare(target.this) if isinstance(target, exp.Schema) else _bare(target),
                "ref_columns": _column_names(target.expressions) if isinstance(target, exp.Schema) else [],
                "statement": statement.index,
            })
        elif isinstance(node, exp.UniqueColumnConstraint):
            schema = node.this
            table.uniques.append((name, _column_names(schema.expressions) if isinstance(schema, exp.Schema) else []))
        elif isinstance(node, exp.CheckColumnConstraint):
            table.checks.append((name, self._sql(node.this)))
        else:
            raise ImportFailure(f"table constraint of an unsupported kind: {type(node).__name__}")

    def create_table(self, tree: exp.Expr, statement: splitter.Statement, partitioning: str | None) -> None:
        if not isinstance(tree, exp.Create) or str(tree.args.get("kind", "")).upper() != "TABLE":
            raise ImportFailure(f"expected CREATE TABLE, parsed as {type(tree).__name__}")
        schema = tree.this
        if not isinstance(schema, exp.Schema):
            raise ImportFailure("CREATE TABLE without a column list (CREATE TABLE … AS SELECT is not imported)")
        name = _bare(schema.this)
        if name in self.tables:
            raise ImportFailure(f"table {name!r} is defined twice (two schemas with the same table name?)")
        table = _Table(name=name, statement=statement.index, statements=[statement.index])
        properties = tree.args.get("properties")
        if partitioning is None and properties is not None:
            partitioned = properties.find(exp.PartitionedByProperty)
            if partitioned is not None:
                partitioning = "PARTITION BY " + self._sql(partitioned.this)
        table.partitioning = partitioning
        declared = declared_types(statement.text)
        for item in schema.expressions:
            if isinstance(item, exp.ColumnDef):
                self._column(table, item, statement)
                table.columns[item.name].source_type = declared.get(item.name)
            else:
                self._constraint(table, item, statement)
        if not table.columns:
            raise ImportFailure(f"table {name!r} declares no columns")
        self.tables[name] = table

    def _column(self, table: _Table, item: exp.ColumnDef, statement: splitter.Statement) -> None:
        kind = item.args.get("kind")
        constraints = item.args.get("constraints") or []
        computed = next((c.args["kind"] for c in constraints
                         if isinstance(c.args.get("kind"), exp.ComputedColumnConstraint)), None)
        if kind is None and computed is not None:
            # A computed column declares no type; its expression is kept in the report.
            column = _Column(name=item.name, data_type="COMPUTED", computed=self._sql(computed.this))
        else:
            column = _Column(name=item.name, data_type=self._sql(kind) if kind is not None else "")
        if not column.data_type:
            raise ImportFailure(f"column {table.name}.{item.name} has no data type")
        if isinstance(kind, exp.DataType) and kind.this == exp.DataType.Type.USERDEFINED:
            column.user_type = _bare_text(self._sql(kind))
        for constraint in constraints:
            ckind = constraint.args.get("kind")
            if isinstance(ckind, exp.NotNullColumnConstraint):
                column.nullable = bool(ckind.args.get("allow_null"))
            elif isinstance(ckind, exp.PrimaryKeyColumnConstraint):
                table.primary_key = [column.name]
                table.primary_key_count += 1
                column.nullable = False
            elif isinstance(ckind, exp.UniqueColumnConstraint):
                column.unique = True
            elif isinstance(ckind, exp.DefaultColumnConstraint):
                column.default = self._sql(ckind.this)
            elif isinstance(ckind, exp.CheckColumnConstraint):
                column.checks.append(self._sql(ckind.this))
            elif isinstance(ckind, exp.Reference):
                target = ckind.this
                table.foreign_keys.append({
                    "name": constraint.name or None,
                    "columns": [column.name],
                    "references": _bare(target.this) if isinstance(target, exp.Schema) else _bare(target),
                    "ref_columns": _column_names(target.expressions) if isinstance(target, exp.Schema) else [],
                    "statement": statement.index,
                })
            # Identity, generated, collation and similar column properties do
            # not change the logical model and carry no constraint count.
        table.columns[column.name] = column

    def type_alias(self, statement: splitter.Statement) -> None:
        """T-SQL ``CREATE TYPE name FROM base [NULL | NOT NULL]``: an alias for a base type."""
        match = _TYPE_ALIAS.match(statement.text.strip())
        if match is None:
            raise ImportFailure("CREATE TYPE … FROM in a form the importer does not read")
        base = match.group("base").strip()
        # The base type normalized by the parser, through the one parse entry point.
        probe = parse_statement(f"CREATE TABLE _alias (_c {base})", self.dialect, "create_table")
        column = probe.this.expressions[0] if isinstance(probe, exp.Create) and isinstance(probe.this, exp.Schema) else None
        if not isinstance(column, exp.ColumnDef) or column.args.get("kind") is None:
            raise ImportFailure(f"the base type {base!r} of a user-defined type does not parse")
        name = _bare_text(match.group("name"))
        self.aliases[name.lower()] = {
            "name": name, "base": base, "normalized": self._sql(column.args["kind"]),
            "nullable": (match.group("null") or "NULL").upper() == "NULL", "statement": statement.index,
        }
        self.types.append({"index": statement.index, "statement": statement.head,
                           "alias": name, "base": base})

    def add_default(self, statement: splitter.Statement) -> None:
        """T-SQL ``ALTER TABLE t ADD [CONSTRAINT n] DEFAULT expr FOR column``."""
        match = _ADD_DEFAULT.match(statement.text.strip())
        if match is None:
            raise ImportFailure("ADD … DEFAULT … FOR in a form the importer does not read")
        table = self._table(_bare_text(match.group("table")), statement)
        column = table.columns.get(_bare_text(match.group("column")))
        if column is None:
            raise ImportFailure(f"sets a default on {table.name}.{_bare_text(match.group('column'))}, "
                                "which the table does not have")
        column.default = match.group("expr").strip()

    def extended_property(self, statement: splitter.Statement) -> str | None:
        """Apply an MS_Description to its table or column; otherwise say why it is not imported."""
        args = _extended_property(statement.text)
        name, value = args.get("name"), args.get("value")
        level1, level2 = args.get("level1type", "").upper(), args.get("level2type", "").upper()
        if name != "MS_Description" or level1 != "TABLE" or level2 not in ("", "COLUMN"):
            where = "/".join(p for p in (args.get("level0type"), args.get("level1type"), args.get("level2type")) if p)
            return f"extended property {name or '?'} on {where or 'the database'}"
        table = self._table(args.get("level1name", ""), statement)
        if level2 == "":
            table.description = value or None
            return None
        column = table.columns.get(args.get("level2name", ""))
        if column is None:
            raise ImportFailure(f"describes {table.name}.{args.get('level2name')}, which the table does not have")
        column.description = value or None
        return None

    def alter_table(self, tree: exp.Expr, statement: splitter.Statement) -> None:
        if not isinstance(tree, exp.Alter) or str(tree.args.get("kind", "")).upper() != "TABLE":
            raise ImportFailure(f"expected ALTER TABLE, parsed as {type(tree).__name__}")
        target = _bare(tree.this)
        owner = self.tables.get(target)
        for action in tree.args.get("actions") or []:
            if isinstance(action, exp.AddConstraint):
                table = self._table(target, statement)
                for node in action.expressions:
                    self._constraint(table, node, statement)
            elif isinstance(action, exp.AlterColumn) and owner is not None and action.args.get("default") is not None:
                column = owner.columns.get(action.name)
                if column is None:
                    raise ImportFailure(f"sets a default on {target}.{action.name}, which the table does not have")
                column.default = self._sql(action.args["default"])
                owner.statements.append(statement.index)
            else:
                raise ImportFailure(f"ALTER TABLE action not imported: {type(action).__name__}")

    def comment(self, tree: exp.Expr, statement: splitter.Statement) -> None:
        if not isinstance(tree, exp.Comment):
            raise ImportFailure(f"expected COMMENT, parsed as {type(tree).__name__}")
        text = tree.expression.this if isinstance(tree.expression, exp.Literal) else None
        kind = str(tree.args.get("kind", "")).upper()
        if kind == "TABLE":
            table = self._table(_bare(tree.this), statement)
            table.description = text or None
        elif kind == "COLUMN":
            column_node = tree.this
            table_name = column_node.table if isinstance(column_node, exp.Column) else ""
            table = self._table(table_name, statement)
            column = table.columns.get(column_node.name)
            if column is None:
                raise ImportFailure(f"comments on {table_name}.{column_node.name}, which the table does not have")
            column.description = text or None
        else:
            raise ImportFailure(f"COMMENT ON {kind} is not imported")

    def attach(self, statement: splitter.Statement) -> None:
        match = _ATTACH.match(statement.text.strip())
        if match is None:
            raise ImportFailure("ATTACH PARTITION in a form the importer does not read")
        parent, child = _bare_text(match.group("parent")), _bare_text(match.group("child"))
        self.partitions[child] = {
            "parent": parent,
            "bound": " ".join(match.group("bound").rstrip(";").split()),
            "statement": statement.index,
        }


def _imported_counts(table: _Table) -> dict[str, int]:
    return {
        "columns": len(table.columns),
        "primary_keys": table.primary_key_count,
        "foreign_keys": len(table.foreign_keys),
        "unique_constraints": len(table.uniques) + sum(1 for c in table.columns.values() if c.unique),
        "check_constraints": len(table.checks) + sum(len(c.checks) for c in table.columns.values()),
        "table_descriptions": 1 if table.description else 0,
        "column_descriptions": sum(1 for c in table.columns.values() if c.description),
    }


def _to_model(builder: _Builder) -> tuple[SynthesizedModel | None, dict[str, Any], list[dict[str, Any]]]:
    """The IR for the non-partition tables, what is held in the report, and build failures."""
    entities: list[EntitySchema] = []
    relationships: list[RelationshipSchema] = []
    held: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    entity_names = {name for name in builder.tables if name not in builder.partitions}

    for name, table in builder.tables.items():
        if name in builder.partitions:
            continue
        table_held: dict[str, Any] = {}
        names = list(table.columns)
        columns: list[ColumnSchema] = []
        for position, column in enumerate(table.columns.values()):
            data_type = column.data_type
            if column.user_type is not None:
                alias = builder.aliases.get(column.user_type.lower())
                if alias is not None:
                    data_type = alias["normalized"]
                elif column.user_type.lower() in _BUILTIN_SPECIAL_TYPES:
                    data_type = _BUILTIN_SPECIAL_TYPES[column.user_type.lower()]
                else:
                    table_held.setdefault("unresolved_types", []).append({
                        "column": column.name, "type": column.source_type or data_type,
                        "reason": "a user-defined type no CREATE TYPE in this file defines"})
            if column.computed is not None:
                table_held.setdefault("computed_columns", []).append({
                    "column": column.name, "expression": column.computed,
                    "reason": "computed column: the model holds no expression"})
            try:
                columns.append(ColumnSchema(
                    name=column.name,
                    data_type=data_type,
                    source_data_type=column.source_type,
                    ordinal_position=position,
                    is_nullable=column.nullable,
                    default_value=column.default,
                    description=column.description,
                ))
            except ValueError as exc:
                failures.append({"statement": table.statement, "table": name,
                                 "reason": f"column {column.name} does not fit the model: {exc}"})
        # Keys and constraints go into the model whole (Sprint 8 Step 3): a
        # composite key, and a UNIQUE or CHECK over several columns, included.
        uniques = [UniqueConstraintSchema(columns=[c.name]) for c in table.columns.values() if c.unique]
        uniques += [UniqueConstraintSchema(name=n, columns=cols) for n, cols in table.uniques if cols]
        checks = [CheckConstraintSchema(expression=e, columns=[c.name])
                  for c in table.columns.values() for e in c.checks]
        checks += [CheckConstraintSchema(name=n, expression=e, columns=columns_read_by(e, names))
                   for n, e in table.checks]
        for fk in table.foreign_keys:
            target = fk["references"]
            if target not in entity_names:
                table_held.setdefault("foreign_keys", []).append(
                    {**fk, "reason": f"references {target!r}, which is not a table in this file"})
                continue
            referenced = fk["ref_columns"] or builder.tables[target].primary_key
            if len(referenced) != len(fk["columns"]):
                table_held.setdefault("foreign_keys", []).append(
                    {**fk, "reason": f"names {len(fk['columns'])} columns, but {target}'s primary key, which it "
                                     f"references implicitly, has {len(referenced)}"})
                continue
            relationships.append(RelationshipSchema(
                from_ref=name, from_columns=fk["columns"], to_ref=target, to_columns=referenced,
                name=fk.get("name"), cardinality=Cardinality.MANY_TO_ONE))
        if table.partitioning:
            table_held["partitioning"] = table.partitioning
        partitions = [
            {"name": child, "bound": info["bound"],
             "counts": _imported_counts(builder.tables[child]) if child in builder.tables else None,
             "primary_key": builder.tables[child].primary_key if child in builder.tables else [],
             "foreign_keys": builder.tables[child].foreign_keys if child in builder.tables else []}
            for child, info in builder.partitions.items() if info["parent"] == name]
        if partitions:
            table_held["partitions"] = partitions
        if table_held:
            held[name] = table_held
        if columns:
            try:
                entities.append(EntitySchema(
                    entity_name=name, entity_type=EntityType.TABLE, description=table.description,
                    columns=columns, primary_key=table.primary_key, unique_constraints=uniques,
                    check_constraints=checks))
            except ValueError as exc:
                failures.append({"statement": table.statement, "table": name,
                                 "reason": f"its keys or constraints do not fit the model: {exc}"})
    for child, info in builder.partitions.items():
        if info["parent"] not in entity_names:
            failures.append({"statement": info["statement"], "table": child,
                             "reason": f"is a partition of {info['parent']!r}, which is not a table in this file"})
        if child not in builder.tables:
            failures.append({"statement": info["statement"], "table": child,
                             "reason": "is attached as a partition but no CREATE TABLE defines it"})
    model = (SynthesizedModel(paradigm=Paradigm.THREE_NF, entities=entities, relationships=relationships)
             if entities else None)
    return model, held, failures


def _reconcile(text: str, dialect: str, builder: _Builder, statements: list[splitter.Statement]) -> dict[str, Any]:
    expected = counter.count(text, dialect)
    by_name = {s.index: s for s in statements}
    imported: dict[str, dict[str, int]] = {
        name: _imported_counts(table) for name, table in builder.tables.items()}
    gaps: list[dict[str, Any]] = []
    for name in sorted(set(expected) | set(imported)):
        source = expected.get(name)
        got = imported.get(name, dict.fromkeys(counter.KINDS, 0))
        is_partition = (source.partition_of if source else None) or builder.partitions.get(name, {}).get("parent")
        if source is None:
            gaps.append({"table": name, "kind": "table", "source": 0, "imported": 1, "statements": []})
            continue
        if name not in imported:
            gaps.append({"table": name, "kind": "partition" if is_partition else "table",
                         "source": 1, "imported": 0,
                         "statements": _mentions(name, statements)})
            continue
        for kind in counter.KINDS:
            if source.counts[kind] != got[kind]:
                table = builder.tables[name]
                gaps.append({"table": name, "kind": kind, "source": source.counts[kind], "imported": got[kind],
                             "statements": [{"index": i, "line": by_name[i].line, "statement": by_name[i].head}
                                            for i in sorted(set(table.statements)) if i in by_name]})
    return {
        "source": counter.totals(expected),
        "imported": _totals(builder, imported),
        "gaps": gaps,
    }


def _mentions(name: str, statements: list[splitter.Statement]) -> list[dict[str, Any]]:
    pattern = re.compile(rf"(?<![\w$#]){re.escape(name)}(?![\w$#])", re.IGNORECASE)
    return [{"index": s.index, "line": s.line, "statement": s.head}
            for s in statements if pattern.search(s.text)][:20]


def _totals(builder: _Builder, imported: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    out = {"tables": {"count": 0, **dict.fromkeys(counter.KINDS, 0)},
           "partitions": {"count": 0, **dict.fromkeys(counter.KINDS, 0)}}
    for name, counts in imported.items():
        bucket = out["partitions" if name in builder.partitions else "tables"]
        bucket["count"] += 1
        for kind in counter.KINDS:
            bucket[kind] += counts[kind]
    return out


def import_ddl(raw: bytes, dialect: str, file_name: str = "upload.sql") -> ImportResult:
    """Import one exported DDL file. Never raises for bad content: failures are in the report."""
    if dialect not in DIALECTS:
        raise ValueError(f"dialect {dialect!r} is not importable; importable: {', '.join(DIALECTS)}")
    report: dict[str, Any] = {"file": file_name, "dialect": dialect,
                              "evidence": IMPORT_DIALECTS[dialect]["evidence"],
                              "failures": [], "not_imported": [], "normalizer": {}}
    try:
        text, encoding_label = decode(raw)
    except DecodeError as exc:
        report.update(status="unreconciled", encoding=None,
                      failures=[{"statement": None, "line": None, "reason": str(exc)}])
        return ImportResult(dialect, "undecodable", "unreconciled", None, report)
    report["encoding"] = encoding_label

    statements = splitter.split(text, dialect)
    builder = _Builder(dialect)
    applied: dict[str, int] = {}
    for statement in statements:
        kind, reason = classify(statement)
        if kind in ("client", "procedural", "skipped"):
            report["not_imported"].append({"index": statement.index, "line": statement.line,
                                           "reason": reason or ("client command" if kind == "client"
                                                                else "procedural object"),
                                           "statement": statement.head})
            continue
        try:
            if kind == "unrecognized_table":
                raise ImportFailure("names a TABLE in a form the importer does not recognise; nothing was skipped silently")
            if kind == "attach_partition":
                builder.attach(statement)
                continue
            if kind == "type_alias":
                builder.type_alias(statement)
                continue
            if kind == "add_default":
                builder.add_default(statement)
                continue
            if kind == "extended_property":
                not_imported = builder.extended_property(statement)
                if not_imported is not None:
                    report["not_imported"].append({"index": statement.index, "line": statement.line,
                                                   "reason": not_imported, "statement": statement.head})
                continue
            partitioning = None
            text_to_parse = statement.text
            if dialect == "oracle":
                normalized = oracle_normalizer.normalize(text_to_parse)
                text_to_parse, partitioning = normalized.text, normalized.partitioning
                for rule, n in normalized.applied.items():
                    applied[rule] = applied.get(rule, 0) + n
            elif dialect == "tsql":
                tsql = sqlserver_normalizer.normalize(text_to_parse)
                text_to_parse, partitioning = tsql.text, tsql.partitioning
                for rule, n in tsql.applied.items():
                    applied[rule] = applied.get(rule, 0) + n
                if tsql.nocheck:
                    builder.nocheck.append({"index": statement.index, "statement": statement.head})
            tree = parse_statement(text_to_parse, dialect, kind)
            if kind == "create_table":
                builder.create_table(tree, statement, partitioning)
            elif kind == "alter_table":
                builder.alter_table(tree, statement)
            elif kind == "comment":
                builder.comment(tree, statement)
            elif kind == "create_type":
                builder.types.append({"index": statement.index, "statement": statement.head})
        except ImportFailure as exc:
            report["failures"].append({"statement": statement.index, "line": statement.line,
                                       "head": statement.head, "reason": str(exc)})
    report["normalizer"] = applied
    report["types"] = builder.types
    if builder.nocheck:
        # Added WITH NOCHECK: the constraint is in the model, but the database
        # did not validate the rows that existed when it was added.
        report["not_validated"] = builder.nocheck

    model, held, build_failures = _to_model(builder)
    report["failures"].extend(build_failures)
    report["held"] = held
    report["reconciliation"] = _reconcile(text, dialect, builder, statements)
    reconciled = not report["failures"] and not report["reconciliation"]["gaps"] and model is not None
    status = "reconciled" if reconciled else "unreconciled"
    report["status"] = status
    return ImportResult(dialect, encoding_label, status, model, report)
