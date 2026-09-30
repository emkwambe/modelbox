"""The exported dbt project builds on PostgreSQL, on the product's own seed data.

Sprint 9 Step 2b. Each imported certified fixture (Oracle HR, Oracle CO,
Pagila, AdventureWorks) is taken through the path a user takes:

1. Its PostgreSQL DDL export is applied to an empty database on the appliance's
   own PostgreSQL 16.15, with every key, foreign key and CHECK constraint.
2. ``ExporterService.generate_synthetic_seed`` generates rows, exactly as the
   export endpoint calls it, and **every INSERT is accepted** under those
   constraints, with every table holding the rows asked for, read back by SQL.
3. The tables are copied, without their constraints, into the schema the
   exported ``_sources.yml`` names, and the exported dbt project for
   PostgreSQL is built there with ``dbt build``: every model and every test.
4. The copy is then broken deliberately, once with a duplicate grain key and
   once with an orphan foreign key, and the test that guards each must fail,
   with every other failure confined to the rows that were changed.

The copy is keyless because the database's own constraints would refuse the
broken rows, which is what step 2 shows and what the controls below confirm.

**Controls.** Each positive result is paired with one that must fail, so a
test that could not fail cannot pass: the database refuses a duplicate key
(the constraints of step 2 are live); the seed with its identifiers unquoted is
refused (quoting is load-bearing); and the project exported with the source
types, not PostgreSQL's, does not build (the type translation is load-bearing).

Runs in the CI job "Artifact Fidelity Harness", which has dbt and starts the
appliance's PostgreSQL (``MODELBOX_DBT_POSTGRES_URL``). There
``MODELBOX_DBT_POSTGRES_EXPECT=1`` turns a missing server or toolchain into a
failure. Elsewhere it skips, saying why.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from app.schemas.data_model import SynthesizedModel
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService

URL_ENV = "MODELBOX_DBT_POSTGRES_URL"
EXPECTED = os.environ.get("MODELBOX_DBT_POSTGRES_EXPECT") == "1"
URL = os.environ.get(URL_ENV, "")
HAVE_DBT = find_spec("dbt") is not None
HAVE_PSYCOPG2 = find_spec("psycopg2") is not None

_BACKEND = Path(__file__).resolve().parent.parent
DDL = _BACKEND / "tests" / "fixtures" / "ddl"
PACKAGE_CACHE = _BACKEND / ".dbt-packages"
CERTIFIED = [("oracle", "hr"), ("oracle", "co"), ("postgres", "pagila"), ("tsql", "adventureworks")]
IDS = [stem for _, stem in CERTIFIED]
ROWS = 20

_missing = [name for name, present in (
    (URL_ENV, URL.startswith("postgresql")), ("dbt", HAVE_DBT), ("psycopg2", HAVE_PSYCOPG2),
    ("the dbt package cache (scripts/refresh_dbt_packages.py)", PACKAGE_CACHE.is_dir())) if not present]

pytestmark = pytest.mark.skipif(
    bool(_missing) and not EXPECTED,
    reason=f"needs {', '.join(_missing)} (the Artifact Fidelity Harness job has them)",
)


def test_the_job_has_its_server_and_toolchain() -> None:
    """A skipped gate must be loud: where this module is expected to run, it can."""
    if not EXPECTED:
        pytest.skip("MODELBOX_DBT_POSTGRES_EXPECT is not set")
    assert not _missing, f"missing: {', '.join(_missing)}"


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
def _connect(database: str | None = None) -> Any:
    import psycopg2

    parts = urlsplit(URL)
    connection = psycopg2.connect(host=parts.hostname, port=parts.port or 5432, user=parts.username,
                                  password=parts.password, dbname=database or parts.path.lstrip("/"))
    connection.autocommit = True
    return connection


def _fresh_database(name: str) -> None:
    # Not `with connection:`, which opens a transaction block even under
    # autocommit, and DROP DATABASE refuses to run in one.
    admin = _connect()
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            cursor.execute(f'CREATE DATABASE "{name}"')
    finally:
        admin.close()


def _apply(database: str, statements: list[str]) -> list[dict[str, str]]:
    """Apply each statement on its own (autocommit); every refusal, with its SQLSTATE."""
    import psycopg2

    refused = []
    connection = _connect(database)
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                try:
                    cursor.execute(statement)
                except psycopg2.Error as exc:
                    refused.append({"sqlstate": exc.pgcode or "", "error": str(exc).splitlines()[0][:300],
                                    "statement": " ".join(statement.split())[:160]})
    finally:
        connection.close()
    return refused


def _query(database: str, sql: str, params: tuple[object, ...] = ()) -> list[tuple[Any, ...]]:
    connection = _connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall()) if cursor.description else []
    finally:
        connection.close()


def _inserts(sql: str) -> list[str]:
    # The first statement follows the file's header comments, so a statement
    # is any chunk that contains an INSERT, comments and all.
    return [s for s in re.split(r";\s*\n", sql) if re.search(r"^INSERT INTO ", s, re.MULTILINE)]


# ---------------------------------------------------------------------------
# dbt
# ---------------------------------------------------------------------------
_DBT = """
import sys
from dbt.cli.main import dbtRunner
project, command = sys.argv[1], sys.argv[2:]
result = dbtRunner().invoke(command + ["--project-dir", project, "--profiles-dir", project,
                                       "--no-partial-parse"])
sys.exit(0 if result.success else 1)
"""


@dataclass
class DbtRun:
    success: bool
    output: str
    status: dict[str, str]  # unique_id -> status, from target/run_results.json


def _dbt(project: Path, *command: str) -> DbtRun:
    env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "False", "DO_NOT_TRACK": "1"}
    done = subprocess.run([sys.executable, "-c", _DBT, str(project), *command], capture_output=True,
                          text=True, env=env, cwd=str(project), check=False, timeout=1800)
    results = project / "target" / "run_results.json"
    status = {}
    if results.exists():
        status = {r["unique_id"]: r["status"] for r in json.loads(results.read_text(encoding="utf-8"))["results"]}
        results.unlink()  # so a later run cannot be read as this one's
    return DbtRun(done.returncode == 0, (done.stdout + done.stderr)[-4000:], status)


def _write_project(root: Path, files: dict[str, str], database: str, schema: str = "analytics") -> Path:
    for path, content in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content, encoding="utf-8")
    if "packages.yml" in files:
        shutil.copytree(PACKAGE_CACHE, root / "dbt_packages")
    (root / "dbt_project.yml").write_text(
        "name: 'step2b'\nversion: '1.0'\nprofile: 'step2b'\nmodel-paths: ['models']\n", encoding="utf-8")
    parts = urlsplit(URL)
    (root / "profiles.yml").write_text(yaml.safe_dump({"step2b": {"target": "ci", "outputs": {"ci": {
        "type": "postgres", "host": parts.hostname, "port": parts.port or 5432, "user": parts.username,
        "password": parts.password, "dbname": database, "schema": schema, "threads": 4}}}}),
        encoding="utf-8")
    return root


def _source_schema(files: dict[str, str]) -> str:
    return str(yaml.safe_load(files["models/staging/_sources.yml"])["sources"][0]["schema"])


# ---------------------------------------------------------------------------
# One fixture, taken through the whole path once per session
# ---------------------------------------------------------------------------
@dataclass
class Case:
    stem: str
    dialect: str
    model: SynthesizedModel
    database: str
    seed_sql: str
    rows_skipped: dict[str, int]
    ddl_refused: list[dict[str, str]]
    seed_refused: list[dict[str, str]]
    project: Path
    raw_schema: str
    build: DbtRun


_CASES: dict[str, Case] = {}


def _case(stem: str, tmp_path_factory: pytest.TempPathFactory) -> Case:
    if stem in _CASES:
        return _CASES[stem]
    dialect = {s: d for d, s in CERTIFIED}[stem]
    logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
    imported = import_ddl((DDL / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert imported.model is not None, "fixture sanity: the certified fixture imports"
    model = imported.model
    exporter = ExporterService(source_dialect=dialect)
    database = f"dbt_{stem}"
    _fresh_database(database)
    ddl_refused = _apply(database, exporter.generate_ddl_export(model, "postgres").statements)

    # As the export endpoint calls it: row count, format, target dialect.
    seed = exporter.generate_synthetic_seed(model, ROWS, "sql_insert", "postgres")
    seed_sql = next(iter(seed.files.values()))
    seed_refused = _apply(database, _inserts(seed_sql))

    files = exporter.generate_dbt_project(model, dialect="postgres")
    raw = _source_schema(files)
    tables = [name for (name,) in _query(
        database, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")]
    copy = [f'CREATE SCHEMA "{raw}"'] + [
        f'CREATE TABLE "{raw}"."{t}" (LIKE public."{t}" INCLUDING DEFAULTS); '
        f'INSERT INTO "{raw}"."{t}" SELECT * FROM public."{t}"' for t in tables]
    assert not _apply(database, copy), "fixture sanity: the keyless copy is made"

    # Packages come from the offline cache, copied in, never fetched: as in the
    # fidelity harness, a registry cannot fail this gate.
    project = _write_project(tmp_path_factory.mktemp(f"dbt-{stem}"), files, database)
    build = _dbt(project, "build")
    _CASES[stem] = Case(stem, dialect, model, database, seed_sql, seed.rows_skipped, ddl_refused,
                        seed_refused, project, raw, build)
    return _CASES[stem]


@pytest.fixture(params=IDS)
def case(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Case:
    return _case(request.param, tmp_path_factory)


# ---------------------------------------------------------------------------
# The seed loads under every constraint
# ---------------------------------------------------------------------------
def test_the_schema_is_applied_with_its_constraints(case: Case) -> None:
    assert not case.ddl_refused, case.ddl_refused[:5]
    kinds = dict(_query(case.database, "SELECT contype::text, count(*) FROM pg_constraint k "
                        "JOIN pg_namespace n ON n.oid = k.connamespace WHERE n.nspname = 'public' GROUP BY 1"))
    relationships = sum(1 for r in case.model.relationships if r.resolved)
    checks = sum(len(e.check_constraints) for e in case.model.entities)
    # Keys and foreign keys are what the seed must satisfy; the fixture has them.
    assert kinds.get("p", 0) > 0 and kinds.get("f", 0) == relationships
    assert (kinds.get("c", 0) > 0) == (checks > 0)


def test_every_seed_row_is_accepted(case: Case) -> None:
    assert not case.seed_refused, "\n".join(
        f"{r['sqlstate']}: {r['error']}\n    {r['statement']}" for r in case.seed_refused[:10])
    assert case.rows_skipped == {}, f"the generator left rows out: {case.rows_skipped}"
    tables = [t for (t,) in _query(case.database,
                                   "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")]
    assert set(tables) == {e.entity_name for e in case.model.entities}
    counts = {t: _query(case.database, f'SELECT count(*) FROM public."{t}"')[0][0] for t in tables}
    assert counts == {t: ROWS for t in tables}


def test_control_the_constraints_refuse_a_duplicate_key(case: Case) -> None:
    """The acceptance above means something only if the database enforces."""
    table, key = _single_column_key(case)
    refused = _apply(case.database, [f'INSERT INTO public."{table}" SELECT * FROM public."{table}" LIMIT 1'])
    assert [r["sqlstate"] for r in refused] == ["23505"], refused or f"{table}.{key}: duplicate accepted"


def test_control_the_seed_unquoted_is_refused(case: Case) -> None:
    """Quoting is load-bearing where the fixture has a name PostgreSQL would fold."""
    unquoted = case.seed_sql.replace('"', "")
    if unquoted == case.seed_sql or all(n == n.lower() for e in case.model.entities
                                        for n in [e.entity_name, *(c.name for c in e.columns)]):
        pytest.skip(f"{case.stem}: every name is lower case, so quoting changes nothing")
    database = f"{case.database}_unquoted"
    _fresh_database(database)
    exporter = ExporterService(source_dialect=case.dialect)
    assert not _apply(database, exporter.generate_ddl_export(case.model, "postgres").statements)
    refused = _apply(database, _inserts(unquoted))
    assert refused, "the unquoted seed was accepted, so the quoting test above proves nothing"
    assert {r["sqlstate"] for r in refused} <= {"42P01", "42703", "42601", "23503"}, refused[:3]


# ---------------------------------------------------------------------------
# The dbt project builds, and its tests can fail
# ---------------------------------------------------------------------------
def test_dbt_build_succeeds(case: Case) -> None:
    assert case.build.success, case.build.output
    tests = {k: v for k, v in case.build.status.items() if k.startswith("test.")}
    models = {k: v for k, v in case.build.status.items() if k.startswith("model.")}
    assert len(models) == len(case.model.entities), "one staging model per entity"
    assert tests and set(tests.values()) == {"pass"}, {k: v for k, v in tests.items() if v != "pass"}


def _manifest(case: Case) -> dict[str, Any]:
    return json.loads((case.project / "target" / "manifest.json").read_text(encoding="utf-8"))


def _tests_on(case: Case, kind: str) -> list[dict[str, Any]]:
    """Test nodes of a generic test kind, each with the table its model stages."""
    manifest = _manifest(case)
    out = []
    for node in manifest["nodes"].values():
        if node["resource_type"] != "test" or (node.get("test_metadata") or {}).get("name") != kind:
            continue
        model = manifest["nodes"][node["attached_node"]]
        sources = [manifest["sources"][s] for s in model["depends_on"]["nodes"] if s.startswith("source.")]
        column = (node.get("column_name") or "").strip('"')
        out.append({"id": node["unique_id"], "table": sources[0]["identifier"] if sources else "",
                    "column": column, "kwargs": node["test_metadata"].get("kwargs", {}),
                    "model": node["attached_node"]})
    return out


def _single_column_key(case: Case) -> tuple[str, str]:
    # A table with no generated column, so a whole row can be copied back in.
    for entity in sorted(case.model.entities, key=lambda e: e.entity_name):
        if len(entity.primary_key) == 1 and all(c.data_type != "COMPUTED" for c in entity.columns):
            return entity.entity_name, entity.primary_key[0]
    raise AssertionError(f"fixture sanity: {case.stem} has a table with a single-column key")


def _failed(run: DbtRun) -> set[str]:
    return {k for k, v in run.status.items() if k.startswith("test.") and v in ("fail", "error")}


def _restore(case: Case, table: str) -> None:
    assert not _apply(case.database, [f'TRUNCATE "{case.raw_schema}"."{table}"',
                                      f'INSERT INTO "{case.raw_schema}"."{table}" SELECT * FROM public."{table}"'])


def test_dbt_tests_fail_on_a_duplicate_grain_key(case: Case) -> None:
    assert case.build.success, "precondition: the conforming build passes"
    table, key = _single_column_key(case)
    guards = [t for t in _tests_on(case, "unique") if t["table"] == table and t["column"] == key]
    assert guards, f"fixture sanity: {table}.{key} has an exported unique test"
    applied = _apply(case.database, [
        f'INSERT INTO "{case.raw_schema}"."{table}" SELECT * FROM "{case.raw_schema}"."{table}" LIMIT 1'])
    assert not applied
    try:
        run = _dbt(case.project, "test")
    finally:
        _restore(case, table)
    failed = _failed(run)
    assert {g["id"] for g in guards} <= failed, f"the unique test on {table}.{key} did not fail"
    # Every failure is on the table that was changed: nothing else was broken.
    staged = {t["model"] for t in _tests_on(case, "unique") if t["table"] == table}
    manifest = _manifest(case)
    assert all(manifest["nodes"][k]["attached_node"] in staged for k in failed), sorted(failed)


def test_dbt_tests_fail_on_an_orphan_foreign_key(case: Case) -> None:
    assert case.build.success, "precondition: the conforming build passes"
    numeric = {"smallint", "integer", "bigint", "numeric"}
    for guard in sorted(_tests_on(case, "relationships"), key=lambda t: t["id"]):
        found = _query(case.database, "SELECT data_type FROM information_schema.columns WHERE table_schema = %s "
                       "AND table_name = %s AND column_name = %s", (case.raw_schema, guard["table"], guard["column"]))
        if found and found[0][0] in numeric:
            break
    else:
        raise AssertionError(f"fixture sanity: {case.stem} has a numeric foreign key with a relationships test")
    table, column = guard["table"], guard["column"]
    referenced = re.search(r"ref\('([^']+)'\)", str(guard["kwargs"].get("to", "")))
    assert referenced, f"fixture sanity: {guard['id']} names its parent model: {guard['kwargs']}"
    parent = next(e.entity_name for e in case.model.entities if f"stg_{e.entity_name}" == referenced.group(1))
    field = str(guard["kwargs"].get("field", "")).strip('"')
    orphan = _query(case.database, f'SELECT min(v) FROM generate_series(1, 1000000) v '
                    f'WHERE v NOT IN (SELECT "{field}" FROM public."{parent}" WHERE "{field}" IS NOT NULL)')[0][0]
    assert not _apply(case.database, [(
        f'UPDATE "{case.raw_schema}"."{table}" SET "{column}" = {orphan} WHERE ctid = '
        f'(SELECT ctid FROM "{case.raw_schema}"."{table}" LIMIT 1)')])
    try:
        run = _dbt(case.project, "test")
    finally:
        _restore(case, table)
    failed = _failed(run)
    assert guard["id"] in failed, f"the relationships test on {table}.{column} did not fail"
    manifest = _manifest(case)
    changed = {t["model"] for t in _tests_on(case, "relationships") if t["table"] == table}
    assert all(manifest["nodes"][k]["attached_node"] in changed for k in failed), sorted(failed)


# ---------------------------------------------------------------------------
# A T-SQL LIKE character class keeps its meaning (Sprint 9 Step 2c)
# ---------------------------------------------------------------------------
_SHELF = "CK_ProductInventory_Shelf"


def _outcomes(database: str, statements: list[str]) -> list[tuple[str, str]]:
    """(SQLSTATE or "", constraint or "") per statement, in one transaction
    that is rolled back at the end, so the database is left as it was. A refused
    statement is undone to its savepoint; an accepted one stands for the next."""
    import psycopg2

    connection = _connect(database)
    connection.autocommit = False
    out = []
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute("SAVEPOINT s")
                try:
                    cursor.execute(statement)
                    out.append(("", ""))
                    cursor.execute("RELEASE SAVEPOINT s")
                except psycopg2.Error as exc:
                    out.append((exc.pgcode or "", (exc.diag.constraint_name or "") if exc.diag else ""))
                    cursor.execute("ROLLBACK TO SAVEPOINT s")
    finally:
        connection.rollback()
        connection.close()
    return out


def _set_shelf(values: list[str]) -> list[str]:
    return [f'UPDATE public."ProductInventory" SET "Shelf" = \'{v}\' WHERE ctid = '
            f'(SELECT ctid FROM public."ProductInventory" LIMIT 1)' for v in values]


def test_the_shelf_check_means_what_sql_server_means(tmp_path_factory: pytest.TempPathFactory) -> None:
    """SQL Server's [A-Za-z] is exactly one letter: one letter or 'N/A' passes,
    two letters or a digit does not."""
    case = _case("adventureworks", tmp_path_factory)
    accepted, refused = ["B", "z", "N/A"], ["AB", "1", "[A-Za-z]"]
    outcomes = _outcomes(case.database, _set_shelf(accepted + refused))
    assert outcomes[:len(accepted)] == [("", "")] * len(accepted)
    assert outcomes[len(accepted):] == [("23514", _SHELF)] * len(refused)


def test_the_seed_draws_from_the_one_letter_branch(tmp_path_factory: pytest.TempPathFactory) -> None:
    """The seed needs no workaround: its one-letter shelves load under the CHECK."""
    case = _case("adventureworks", tmp_path_factory)
    assert not case.seed_refused
    shelves = [s for (s,) in _query(case.database, 'SELECT "Shelf" FROM public."ProductInventory"')]
    assert len(shelves) == ROWS
    assert any(re.fullmatch("[A-Za-z]", s) for s in shelves), shelves


def test_control_without_the_translation_a_valid_letter_is_refused(
        tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same CHECK, written as the export wrote it before, refuses 'B'."""
    from app.services import ddl_export

    case = _case("adventureworks", tmp_path_factory)
    entity = next(e for e in case.model.entities if e.entity_name == "ProductInventory")
    check = next(c for c in entity.check_constraints if c.name == _SHELF)
    columns = [c.name for c in entity.columns]
    translated, problem = ddl_export.translate_check(check.expression, "tsql", "postgres", columns)
    assert problem is None and translated is not None and "SIMILAR TO" in translated
    monkeypatch.setattr(ddl_export, "_translate_tsql_like", lambda condition, target: (condition, None))
    verbatim, problem = ddl_export.translate_check(check.expression, "tsql", "postgres", columns)
    assert problem is None and verbatim is not None and "LIKE '[A-Za-z]'" in verbatim

    def table(condition: str) -> str:
        return f'CREATE TEMP TABLE shelf_check ("Shelf" VARCHAR(10) CONSTRAINT c CHECK ({condition}))'

    insert = "INSERT INTO shelf_check VALUES ('B')"
    assert _outcomes(case.database, [table(translated), insert]) == [("", ""), ("", "")]
    assert _outcomes(case.database, [table(verbatim), insert]) == [("", ""), ("23514", "c")]


def test_control_the_project_with_source_types_does_not_build(
        tmp_path_factory: pytest.TempPathFactory) -> None:
    """Oracle HR's declared types (NUMBER(6), VARCHAR2) are not PostgreSQL's."""
    case = _case("hr", tmp_path_factory)
    files = ExporterService(source_dialect=case.dialect).generate_dbt_project(case.model)
    assert "NUMBER" in "".join(v for k, v in files.items() if k.endswith(".sql")), \
        "fixture sanity: the source types appear in the staging models"
    # Its own target schema, so a failed run cannot touch the views built above.
    project = _write_project(tmp_path_factory.mktemp("dbt-hr-source-types"), files, case.database,
                             schema="analytics_source_types")
    run = _dbt(project, "run")
    assert not run.success
    assert any(v == "error" for v in run.status.values()), run.output
