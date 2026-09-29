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
    ColumnSchema,
    EntitySchema,
    EntityType,
    Paradigm,
    RelationshipSchema,
    SynthesizedModel,
)
from app.services.ddl_import import counter, oracle_normalizer, splitter
from app.services.ddl_import.dialects import IMPORT_DIALECTS
from app.services.ddl_import.encoding import DecodeError, decode

logger = logging.getLogger(__name__)

DIALECTS = tuple(IMPORT_DIALECTS)
_SQLGLOT_DIALECT = {"oracle": "oracle", "postgres": "postgres", "snowflake": "snowflake"}

# Statement kinds whose Command result must never be accepted.
GUARDED_KINDS = ("create_table", "alter_table", "comment", "create_type")

# Table modifiers any importable dialect writes before TABLE (Snowflake's
# HYBRID and TRANSIENT among them). The counter reads the same words.
_TABLE_MODIFIERS = r"(?:(?:GLOBAL|LOCAL|TEMP|TEMPORARY|UNLOGGED|HYBRID|TRANSIENT|VOLATILE)\s+)*"
_GUARDED = (
    ("create_table", re.compile(rf"^CREATE\s+(?:OR\s+REPLACE\s+)?{_TABLE_MODIFIERS}TABLE\b", re.I)),
    ("alter_table", re.compile(r"^ALTER\s+TABLE\b", re.I)),
    ("comment", re.compile(r"^COMMENT\s+ON\b", re.I)),
    ("create_type", re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?TYPE\b", re.I)),
)

# Named skip rules: statements that are not part of a logical model. Each is
# anchored at the statement's start, so none can match a guarded kind, and the
# ALTER forms only match when the whole statement is that one action.
_NAME = r"(?:\"[^\"]+\"|[\w$#]+)(?:\s*\.\s*(?:\"[^\"]+\"|[\w$#]+))*"
SKIP_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("session setting", re.compile(r"^(?:SET\s|RESET\s|SELECT\s+pg_catalog\.set_config\s*\()", re.I)),
    ("ownership", re.compile(
        rf"^ALTER\s+(?:TABLE|SCHEMA|SEQUENCE|VIEW|MATERIALIZED\s+VIEW|FUNCTION|PROCEDURE|AGGREGATE|TYPE|DOMAIN)"
        rf"\s+(?:ONLY\s+)?{_NAME}(?:\s*\([^;]*\))?\s+OWNER\s+TO\s+\S+\s*;?\s*$", re.I)),
    ("privileges", re.compile(r"^(?:GRANT|REVOKE)\s", re.I)),
    ("index", re.compile(r"^(?:CREATE\s+(?:UNIQUE\s+|BITMAP\s+)?INDEX|ALTER\s+INDEX)\b", re.I)),
    ("sequence", re.compile(r"^(?:CREATE|ALTER)\s+SEQUENCE\b", re.I)),
    ("view", re.compile(r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:FORCE\s+)?(?:MATERIALIZED\s+)?VIEW|ALTER\s+(?:MATERIALIZED\s+)?VIEW)\b", re.I)),
    ("domain", re.compile(r"^(?:CREATE|ALTER)\s+DOMAIN\b", re.I)),
    ("extension", re.compile(r"^(?:CREATE|ALTER|COMMENT\s+ON)\s+EXTENSION\b", re.I)),
    ("schema", re.compile(r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?|ALTER\s+)SCHEMA\b", re.I)),
    ("synonym", re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:PUBLIC\s+)?SYNONYM\b", re.I)),
    ("drop", re.compile(r"^DROP\s", re.I)),
)
_LOOKS_LIKE_TABLE = re.compile(r"^(?:CREATE|ALTER|COMMENT|DROP)\b[^;(]{0,120}?\bTABLE\b", re.I | re.S)
_ATTACH = re.compile(
    rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?(?P<parent>{_NAME})\s+ATTACH\s+PARTITION\s+(?P<child>{_NAME})\s+"
    r"(?P<bound>FOR\s+VALUES\s+.+|DEFAULT)\s*;?\s*$",
    re.I | re.S,
)


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


@dataclass
class _Table:
    name: str
    statement: int
    columns: dict[str, _Column] = field(default_factory=dict)
    primary_key: list[str] = field(default_factory=list)
    primary_key_count: int = 0
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)
    uniques: list[list[str]] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)  # table-level CHECKs, as SQL
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
    parts = re.findall(r"\"([^\"]+)\"|([\w$#]+)", name)
    quoted, plain = parts[-1]
    return quoted or plain


def classify(statement: splitter.Statement) -> tuple[str, str | None]:
    """(kind, skip reason) for one statement."""
    if statement.kind != "sql":
        return statement.kind, None
    text = statement.text.lstrip()
    for name, pattern in SKIP_RULES:
        if pattern.match(text):
            return "skipped", name
    if _ATTACH.match(text) or re.match(r"^ALTER\s+TABLE\b[^;]*\bATTACH\s+PARTITION\b", text, re.I | re.S):
        return "attach_partition", None
    for kind, pattern in _GUARDED:
        if pattern.match(text):
            return kind, None
    if _LOOKS_LIKE_TABLE.match(text):
        # Never skip what might define or change a table: a form no rule
        # recognises is a failure the report names, not a quiet skip.
        return "unrecognized_table", None
    return "skipped", "not a table-level statement"


def parse_statement(text: str, dialect: str, kind: str) -> exp.Expression:
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

    def _table(self, name: str, statement: splitter.Statement) -> _Table:
        table = self.tables.get(name)
        if table is None:
            raise ImportFailure(f"refers to table {name!r}, which no CREATE TABLE in this file defines")
        table.statements.append(statement.index)
        return table

    def _sql(self, node: exp.Expression) -> str:
        return node.sql(dialect=_SQLGLOT_DIALECT[self.dialect])

    def _constraint(self, table: _Table, node: exp.Expression, statement: splitter.Statement) -> None:
        if isinstance(node, exp.Constraint):
            for inner in node.expressions:
                self._constraint(table, inner, statement)
            return
        if isinstance(node, exp.PrimaryKey):
            table.primary_key = _column_names(node.expressions)
            table.primary_key_count += 1
        elif isinstance(node, exp.ForeignKey):
            reference = node.args.get("reference")
            target = reference.this if reference is not None else None
            table.foreign_keys.append({
                "columns": _column_names(node.expressions),
                "references": _bare(target.this) if isinstance(target, exp.Schema) else _bare(target),
                "ref_columns": _column_names(target.expressions) if isinstance(target, exp.Schema) else [],
                "statement": statement.index,
            })
        elif isinstance(node, exp.UniqueColumnConstraint):
            schema = node.this
            table.uniques.append(_column_names(schema.expressions) if isinstance(schema, exp.Schema) else [])
        elif isinstance(node, exp.CheckColumnConstraint):
            table.checks.append(self._sql(node.this))
        else:
            raise ImportFailure(f"table constraint of an unsupported kind: {type(node).__name__}")

    def create_table(self, tree: exp.Expression, statement: splitter.Statement, partitioning: str | None) -> None:
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
        for item in schema.expressions:
            if isinstance(item, exp.ColumnDef):
                self._column(table, item, statement)
            else:
                self._constraint(table, item, statement)
        if not table.columns:
            raise ImportFailure(f"table {name!r} declares no columns")
        self.tables[name] = table

    def _column(self, table: _Table, item: exp.ColumnDef, statement: splitter.Statement) -> None:
        kind = item.args.get("kind")
        column = _Column(name=item.name, data_type=self._sql(kind) if kind is not None else "")
        if not column.data_type:
            raise ImportFailure(f"column {table.name}.{item.name} has no data type")
        for constraint in item.args.get("constraints") or []:
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
                    "columns": [column.name],
                    "references": _bare(target.this) if isinstance(target, exp.Schema) else _bare(target),
                    "ref_columns": _column_names(target.expressions) if isinstance(target, exp.Schema) else [],
                    "statement": statement.index,
                })
            # Identity, generated, collation and similar column properties do
            # not change the logical model and carry no constraint count.
        table.columns[column.name] = column

    def alter_table(self, tree: exp.Expression, statement: splitter.Statement) -> None:
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

    def comment(self, tree: exp.Expression, statement: splitter.Statement) -> None:
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
        unique_single = {cols[0] for cols in table.uniques if len(cols) == 1}
        held_uniques = [cols for cols in table.uniques if len(cols) != 1]
        column_checks: dict[str, list[str]] = {}
        held_checks: list[str] = []
        for check in table.checks:
            referenced = {c for c in re.findall(r"[\"]?([A-Za-z_][\w$#]*)[\"]?", check)
                          if c in table.columns or c.upper() in table.columns or c.lower() in table.columns}
            if len(referenced) == 1:
                col = next(iter(referenced))
                key = col if col in table.columns else (col.upper() if col.upper() in table.columns else col.lower())
                column_checks.setdefault(key, []).append(check)
            else:
                held_checks.append(check)
        columns: list[ColumnSchema] = []
        for position, column in enumerate(table.columns.values()):
            checks = column.checks + column_checks.get(column.name, [])
            try:
                columns.append(ColumnSchema(
                    name=column.name,
                    data_type=column.data_type,
                    ordinal_position=position,
                    is_primary_key=column.name in table.primary_key,
                    is_nullable=column.nullable,
                    is_unique=column.unique or column.name in unique_single,
                    default_value=column.default,
                    check_expression=" AND ".join(f"({c})" for c in checks) if checks else None,
                    description=column.description,
                ))
            except ValueError as exc:
                failures.append({"statement": table.statement, "table": name,
                                 "reason": f"column {column.name} does not fit the model: {exc}"})
        for fk in table.foreign_keys:
            simple = len(fk["columns"]) == 1 and len(fk["ref_columns"]) <= 1
            target = fk["references"]
            if simple and target in entity_names:
                ref_col = fk["ref_columns"][0] if fk["ref_columns"] else None
                if ref_col is None:
                    target_table = builder.tables[target]
                    ref_col = target_table.primary_key[0] if len(target_table.primary_key) == 1 else None
                if ref_col is not None:
                    relationships.append(RelationshipSchema.model_validate({
                        "from": f"{name}.{fk['columns'][0]}", "to": f"{target}.{ref_col}", "cardinality": "N:1"}))
                    for column in columns:
                        if column.name == fk["columns"][0]:
                            column.is_foreign_key = True
                            column.references = f"{target}.{ref_col}"
                    continue
            reason = ("composite foreign key: the model holds single-column relationships"
                      if not simple else f"references {target!r}, which is not a table in this file")
            table_held.setdefault("foreign_keys", []).append({**fk, "reason": reason})
        if held_uniques:
            table_held["unique_constraints"] = [
                {"columns": cols, "reason": "UNIQUE over several columns: the model holds single-column UNIQUE"}
                for cols in held_uniques]
        if held_checks:
            table_held["check_constraints"] = [
                {"expression": check, "reason": "CHECK over several columns: the model holds column CHECKs"}
                for check in held_checks]
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
            entities.append(EntitySchema(entity_name=name, entity_type=EntityType.TABLE,
                                         description=table.description, columns=columns))
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
    pattern = re.compile(rf"(?<![\w$#]){re.escape(name)}(?![\w$#])", re.I)
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
            partitioning = None
            text_to_parse = statement.text
            if dialect == "oracle":
                normalized = oracle_normalizer.normalize(text_to_parse)
                text_to_parse, partitioning = normalized.text, normalized.partitioning
                for rule, n in normalized.applied.items():
                    applied[rule] = applied.get(rule, 0) + n
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

    model, held, build_failures = _to_model(builder)
    report["failures"].extend(build_failures)
    report["held"] = held
    report["reconciliation"] = _reconcile(text, dialect, builder, statements)
    reconciled = not report["failures"] and not report["reconciliation"]["gaps"] and model is not None
    status = "reconciled" if reconciled else "unreconciled"
    report["status"] = status
    return ImportResult(dialect, encoding_label, status, model, report)
