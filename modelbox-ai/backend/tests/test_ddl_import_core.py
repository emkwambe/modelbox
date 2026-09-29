"""The DDL importer's machinery: encodings, splitting, the Oracle normalizer, and
the rule that an import can never silently drop a statement.

Each check has a negative control (Amendment 2) that turns off exactly the
piece under test and shows the check then fails:

* every normalizer rule, disabled alone, makes a real fixture statement fail;
* without the Command guard, an unparsed table statement would pass;
* without UTF-16 detection, a UTF-16 file with no BOM would not import;
* with one statement kind dropped inside the importer, reconciliation reports
  the gap by statement.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest
from sqlglot import exp

from app.services.ddl_import import encoding, importer, oracle_normalizer, splitter
from app.services.ddl_import.importer import ImportFailure, import_ddl, parse_statement

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
PACKAGE = Path(__file__).resolve().parents[1] / "app" / "services" / "ddl_import"


def _text(dialect: str, stem: str) -> str:
    return (DDL / dialect / f"{stem}.sql").read_text(encoding="utf-8")


# --- Encodings ----------------------------------------------------------------

ENCODINGS = [
    pytest.param(lambda t: t.encode("utf-8"), "UTF-8 without BOM", id="utf-8"),
    pytest.param(lambda t: t.encode("utf-8-sig"), "UTF-8 with BOM", id="utf-8-bom"),
    pytest.param(lambda t: t.encode("utf-16"), "UTF-16 LE with BOM", id="utf-16-bom"),
    pytest.param(lambda t: t.encode("utf-16-le"), "UTF-16-LE without BOM", id="utf-16-le"),
    pytest.param(lambda t: t.encode("utf-16-be"), "UTF-16-BE without BOM", id="utf-16-be"),
]


@pytest.mark.parametrize(("encode", "label"), ENCODINGS)
def test_every_encoding_imports_the_same_real_file(encode, label: str) -> None:
    text = _text("oracle", "hr")
    result = import_ddl(encode(text), "oracle", "hr.sql")
    baseline = import_ddl(text.encode("utf-8"), "oracle", "hr.sql")
    assert result.encoding == label
    assert result.status == "reconciled"
    assert result.report["reconciliation"] == baseline.report["reconciliation"]


def test_an_undecodable_file_is_refused_by_name() -> None:
    result = import_ddl("CREATE TABLE t (a int); -- café".encode("latin-1"), "postgres")
    assert result.model is None
    assert result.status == "unreconciled"
    assert "neither UTF-8 nor UTF-16" in result.report["failures"][0]["reason"]


def test_negative_control_without_utf16_detection_a_bomless_file_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(encoding, "_utf16_without_bom", lambda raw: None)
    result = import_ddl(_text("oracle", "hr").encode("utf-16-le"), "oracle")
    assert result.status != "reconciled"


# --- Splitting ----------------------------------------------------------------

def test_oracle_sqlplus_lines_are_client_commands_and_plsql_splits_at_slash() -> None:
    text = (
        "SET ECHO OFF\nPROMPT creating\n@other_script.sql\n"
        "CREATE TABLE t (a NUMBER);\n"
        "CREATE OR REPLACE PROCEDURE p AS BEGIN INSERT INTO t VALUES (1); COMMIT; END;\n/\n"
        "COMMENT ON TABLE t IS 'has; a semicolon';\n"
    )
    statements = splitter.split(text, "oracle")
    assert [s.kind for s in statements] == ["client", "client", "client", "sql", "procedural", "sql"]
    assert statements[4].text.endswith("END;")
    assert statements[5].text == "COMMENT ON TABLE t IS 'has; a semicolon';"


def test_postgres_dollar_bodies_and_psql_meta_commands() -> None:
    text = (
        "\\restrict key\n"
        "CREATE FUNCTION f() RETURNS int AS $body$ SELECT 1; SELECT 2; $body$ LANGUAGE sql;\n"
        "CREATE TABLE t (a text DEFAULT 'x;y');\n"
    )
    statements = splitter.split(text, "postgres")
    assert [s.kind for s in statements] == ["client", "procedural", "sql"]
    assert statements[2].text == "CREATE TABLE t (a text DEFAULT 'x;y');"


def test_pagila_splits_into_every_statement_pg_dump_wrote() -> None:
    statements = splitter.split(_text("postgres", "pagila"), "postgres")
    kinds = {kind: sum(1 for s in statements if s.kind == kind) for kind in ("sql", "client", "procedural")}
    assert kinds == {"sql": 463, "client": 2, "procedural": 25}


def test_procedural_objects_are_listed_in_the_report_not_dropped() -> None:
    report = import_ddl(_text("postgres", "pagila").encode(), "postgres").report
    listed = [item for item in report["not_imported"] if item["reason"] == "procedural object"]
    assert len(listed) == 25
    assert all(item["statement"] and item["line"] for item in listed)


# --- The Oracle normalizer: every rule has a case and a negative control ------

# Research R1's probe for a partitioned table: sqlglot returns an opaque
# Command for it, so without the rule the table disappears.
PARTITIONED = (
    'CREATE TABLE "S"."T" ("D" DATE, "V" NUMBER) PARTITION BY RANGE ("D") '
    "INTERVAL (NUMTOYMINTERVAL(1,'MONTH')) "
    "(PARTITION \"P1\" VALUES LESS THAN (TO_DATE('2020-02-01','YYYY-MM-DD')))"
)


def _case_for(rule: str) -> tuple[str, str]:
    """A real statement from the Oracle fixtures on which ``rule`` fires."""
    if rule == "partition_by":
        return PARTITIONED, "create_table"
    for stem in ("hr", "co"):
        for statement in splitter.split(_text("oracle", stem), "oracle"):
            kind, _ = importer.classify(statement)
            if kind not in ("create_table", "alter_table"):
                continue
            if rule not in oracle_normalizer.normalize(statement.text).applied:
                continue
            try:
                parse_statement(oracle_normalizer.normalize(statement.text, frozenset({rule})).text, "oracle", kind)
            except ImportFailure:
                return statement.text, kind
    raise AssertionError(f"no fixture statement shows rule {rule!r} is needed")


@pytest.mark.parametrize("rule", oracle_normalizer.RULE_NAMES)
def test_each_normalizer_rule_is_what_makes_its_case_import(rule: str) -> None:
    statement, kind = _case_for(rule)
    normalized = oracle_normalizer.normalize(statement)
    assert rule in normalized.applied
    tree = parse_statement(normalized.text, "oracle", kind)
    assert not isinstance(tree, exp.Command)


@pytest.mark.parametrize("rule", oracle_normalizer.RULE_NAMES)
def test_negative_control_each_rule_disabled_makes_its_case_fail(rule: str) -> None:
    statement, kind = _case_for(rule)
    with pytest.raises(ImportFailure):
        parse_statement(oracle_normalizer.normalize(statement, frozenset({rule})).text, "oracle", kind)


def test_partitioning_is_recorded_as_metadata_not_discarded() -> None:
    normalized = oracle_normalizer.normalize(PARTITIONED)
    assert normalized.partitioning is not None
    assert normalized.partitioning.startswith('PARTITION BY RANGE ("D") INTERVAL')


def test_rules_never_touch_string_literals_or_quoted_names() -> None:
    statement = (
        'CREATE TABLE "S"."T" ("TABLESPACE" VARCHAR2(20) DEFAULT \'STORAGE(1) LOGGING\', '
        '"B" NUMBER, CONSTRAINT "C" CHECK ("TABLESPACE" IN (\'ENABLE\', \'USING INDEX\')) ENABLE) '
        'TABLESPACE "USERS"'
    )
    normalized = oracle_normalizer.normalize(statement).text
    assert '"TABLESPACE" VARCHAR2(20)' in normalized
    assert "'STORAGE(1) LOGGING'" in normalized
    assert "'ENABLE', 'USING INDEX'" in normalized
    assert 'TABLESPACE "USERS"' not in normalized


# --- Silent fallback is failure --------------------------------------------------

def _sqlglot_calls(source: str) -> list[tuple[str, int]]:
    """(function containing the call, line) for every call into sqlglot's parser."""
    tree = ast.parse(source)
    found: list[tuple[str, int]] = []
    for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)] + [tree]:
        body = function.body if not isinstance(function, ast.Module) else [
            n for n in function.body if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)]
        for node in [m for stmt in body for m in ast.walk(stmt)]:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    node.func.attr in ("parse", "parse_one", "transpile") and \
                    isinstance(node.func.value, ast.Name) and node.func.value.id == "sqlglot":
                name = function.name if not isinstance(function, ast.Module) else "<module>"
                found.append((name, node.lineno))
    return found


def test_sqlglot_is_called_only_by_parse_statement() -> None:
    """No import path can parse around the guard, and so ignore a Command."""
    calls = {path.name: _sqlglot_calls(path.read_text(encoding="utf-8")) for path in PACKAGE.glob("*.py")}
    assert sum(len(c) for c in calls.values()) >= 1, "found no sqlglot call at all: the scan is broken"
    outside = [(name, fn, line) for name, found in calls.items() for fn, line in found
               if (name, fn) != ("importer.py", "parse_statement")]
    assert outside == []


def test_negative_control_a_second_parse_path_is_found() -> None:
    rogue = "import sqlglot\n\ndef shortcut(text):\n    return sqlglot.parse_one(text)\n"
    assert _sqlglot_calls(rogue) == [("shortcut", 4)]


@pytest.mark.parametrize("kind", importer.GUARDED_KINDS)
def test_a_command_for_a_guarded_statement_is_a_named_failure(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importer.sqlglot, "parse", lambda text, read: [exp.Command(this="CREATE")])
    with pytest.raises(ImportFailure, match="opaque Command"):
        parse_statement("CREATE TABLE t (a int)", "postgres", kind)


def test_negative_control_without_the_guard_a_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer.sqlglot, "parse", lambda text, read: [exp.Command(this="CREATE")])
    monkeypatch.setattr(importer, "GUARDED_KINDS", ())
    assert isinstance(parse_statement("CREATE TABLE t (a int)", "postgres", "create_table"), exp.Command)


@pytest.mark.parametrize(
    "statement",
    ["CREATE HYPOTHETICAL TABLE t (a int);", "ALTER FOREIGN TABLE t ADD COLUMN b int;",
     "COMMENT  ON FOREIGN TABLE t IS 'x';"],
)
def test_a_table_statement_no_rule_recognises_is_a_failure_not_a_skip(statement: str) -> None:
    report = import_ddl(f"CREATE TABLE ok (a int);\n{statement}\n".encode(), "postgres").report
    assert report["status"] == "unreconciled"
    assert any(f["statement"] == 2 for f in report["failures"]), report["failures"]


def test_skip_rules_are_anchored_and_never_match_a_table_definition() -> None:
    for name, pattern in importer.SKIP_RULES:
        for statement in ("CREATE TABLE t (a int)", "COMMENT ON TABLE t IS 'x'", "CREATE TYPE s AS ENUM ('a')",
                          "ALTER TABLE t ADD CONSTRAINT p PRIMARY KEY (a)"):
            assert not pattern.match(statement), f"skip rule {name!r} matches {statement!r}"


# --- The counter is independent, and reconciliation catches a loss ------------------

def test_the_counter_shares_no_code_with_the_importer() -> None:
    tree = ast.parse((PACKAGE / "counter.py").read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names} | {
        f"{node.module}" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    forbidden = {m for m in imported if m.startswith(("sqlglot", "app."))}
    assert forbidden == set(), forbidden


def test_negative_control_a_statement_the_importer_drops_is_a_gap_by_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(importer._Builder, "comment", lambda self, tree, statement: None)
    report = import_ddl(_text("oracle", "hr").encode(), "oracle").report
    assert report["status"] == "unreconciled"
    gaps = {(g["table"], g["kind"]) for g in report["reconciliation"]["gaps"]}
    assert ("EMPLOYEES", "column_descriptions") in gaps
    employees = next(g for g in report["reconciliation"]["gaps"]
                     if g["table"] == "EMPLOYEES" and g["kind"] == "table_descriptions")
    assert employees["source"] == 1 and employees["imported"] == 0
    assert any("EMPLOYEES" in s["statement"] for s in employees["statements"])


# --- Nothing connects anywhere -------------------------------------------------------

NETWORK_MODULES = ("socket", "ssl", "http", "urllib", "httpx", "requests", "aiohttp", "asyncpg",
                   "psycopg2", "oracledb", "pyodbc", "snowflake", "google", "litellm", "smtplib")


def test_the_importer_imports_no_network_or_database_client() -> None:
    offenders = []
    for path in [*PACKAGE.glob("*.py"), PACKAGE.parents[1] / "api" / "v1" / "endpoints" / "ddl_import.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            offenders += [(path.name, n) for n in names if n.split(".")[0] in NETWORK_MODULES]
    assert offenders == []
