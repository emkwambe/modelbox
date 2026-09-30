"""Each type, identity and sequence mapping, applied to a real PostgreSQL (Sprint 9 Step 1a).

``test_type_mappings`` asserts what the export says; this asserts what
PostgreSQL makes of it. Each mapping case (``fixtures/ddl_mappings/``) is
imported, exported as PostgreSQL DDL, applied statement by statement to an
empty database, and then read back from that database's own catalog
(``format_type``, ``pg_attribute.attidentity``, ``pg_sequence``,
``pg_get_expr``). Rows are then inserted that each constraint must accept or
refuse.

* The appliance's PostgreSQL 16.15 (the "Backend Pytest (Postgres)" job) runs
  every case but PostGIS, including ``CREATE EXTENSION ltree``, which ships with
  PostgreSQL.
* PostGIS is not part of PostgreSQL. Its case runs on the ``postgis/postgis``
  image the same job starts, pinned by digest in the workflow (asserted
  below), at ``MODELBOX_TEST_POSTGIS_URL``.

Where the job expects a server, a missing one fails rather than skips.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.services import ddl_export
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService
from tests._test_db import DATABASE_ENV, _admin_connection, make_test_engine
from tests.test_ddl_on_postgres import _apply

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

MAPPINGS = Path(__file__).resolve().parent / "fixtures" / "ddl_mappings"
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
ON_POSTGRES = os.environ.get("MODELBOX_TEST_DATABASE_EXPECT") == "postgresql"
POSTGIS_ENV = "MODELBOX_TEST_POSTGIS_URL"
POSTGIS_EXPECTED = os.environ.get("MODELBOX_TEST_POSTGIS_EXPECT") == "1"

needs_postgres = pytest.mark.skipif(
    not ON_POSTGRES and not os.environ.get(DATABASE_ENV),
    reason="needs the PostgreSQL test server (the Backend Pytest (Postgres) job runs it)",
)
needs_postgis = pytest.mark.skipif(
    not POSTGIS_EXPECTED and not os.environ.get(POSTGIS_ENV),
    reason="needs the PostGIS test server (the Backend Pytest (Postgres) job runs it)",
)


def test_the_postgres_job_has_its_servers() -> None:
    """A skipped gate must be loud: where a server is expected, it is present."""
    if ON_POSTGRES:
        assert os.environ.get(DATABASE_ENV, "").startswith("postgresql"), "no PostgreSQL test server"
    if POSTGIS_EXPECTED:
        assert os.environ.get(POSTGIS_ENV, "").startswith("postgresql"), "no PostGIS test server"


_PINNED = re.compile(r"postgis/postgis:[\w.-]+@sha256:[0-9a-f]{64}")


def _postgis_images(workflow_text: str) -> list[str]:
    return re.findall(r"postgis/postgis\S*", workflow_text)


def test_the_postgis_image_is_pinned_by_digest() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    steps = "\n".join(step.get("run", "") for step in jobs["backend-test-postgres"]["steps"])
    images = _postgis_images(steps)
    assert images, "the Postgres job starts no PostGIS image"
    assert all(_PINNED.fullmatch(image.strip('"')) for image in images), images


def test_negative_control_a_tag_alone_is_not_a_pin() -> None:
    assert not all(_PINNED.fullmatch(i.strip('"')) for i in _postgis_images('docker run "postgis/postgis:16-3.5"'))


def _export(dialect: str, stem: str, extensions: frozenset[str] = frozenset()) -> ddl_export.DdlExport:
    result = import_ddl((MAPPINGS / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert result.status == "reconciled" and result.model is not None, result.report["failures"][:3]
    return ExporterService(source_dialect=dialect).generate_ddl_export(result.model, "postgres", extensions)


async def _one(engine: AsyncEngine, sql: str) -> object:
    """The single value a query returns."""
    async with engine.begin() as conn:
        return (await conn.exec_driver_sql(sql)).scalar()


async def _run(engine: AsyncEngine, sql: str) -> None:
    """A statement that returns no rows."""
    async with engine.begin() as conn:
        await conn.exec_driver_sql(sql)


async def _refused(engine: AsyncEngine, sql: str) -> str:
    """The error PostgreSQL gives for ``sql``; fails the test if it is accepted."""
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(sql)
    except Exception as exc:  # noqa: BLE001 - the refusal's text is what is asserted
        return str(exc)
    raise AssertionError(f"PostgreSQL accepted: {sql}")


_COLUMN = """
SELECT format_type(a.atttypid, a.atttypmod) AS type, a.attidentity::text AS identity,
       pg_get_expr(d.adbin, d.adrelid) AS default
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE c.relname = '{table}' AND a.attname = '{column}'
"""


async def _column(engine: AsyncEngine, table: str, column: str) -> dict:
    async with engine.connect() as conn:
        row = (await conn.exec_driver_sql(_COLUMN.format(table=table, column=column))).mappings().one()
    return dict(row)


async def _sequence(engine: AsyncEngine, name: str) -> tuple:
    async with engine.connect() as conn:
        return tuple((await conn.exec_driver_sql(
            "SELECT seqstart, seqincrement, seqmin, seqmax FROM pg_sequence "
            f"WHERE seqrelid = to_regclass('{name}')")).one())


async def _identity_sequence(engine: AsyncEngine, table: str, column: str) -> tuple:
    name = await _one(engine, f"SELECT pg_get_serial_sequence('\"{table}\"', '{column}')")
    assert name, f"{table}.{column} has no identity sequence"
    return await _sequence(engine, str(name))


@pytest_asyncio.fixture
async def target() -> AsyncIterator[AsyncEngine]:
    engine = make_test_engine()
    assert engine.dialect.name == "postgresql", "fixture sanity: this test applies DDL to PostgreSQL"
    yield engine
    await engine.dispose()


# --- SQL Server: money, smallmoney, bit, IDENTITY ------------------------------------

@needs_postgres
async def test_sql_server_types_and_identity_on_postgresql(target: AsyncEngine) -> None:
    export = _export("tsql", "type_mappings")
    assert await _apply(target, export.statements) == []

    assert (await _column(target, "Ledger", "Amount"))["type"] == "numeric(19,4)"
    assert (await _column(target, "Ledger", "Fee"))["type"] == "numeric(10,4)"
    active, void = await _column(target, "Ledger", "IsActive"), await _column(target, "Ledger", "IsVoid")
    assert (active["type"], active["default"], void["type"], void["default"]) == ("boolean", "true", "boolean", "false")
    ledger = await _column(target, "Ledger", "LedgerID")
    assert (ledger["type"], ledger["identity"]) == ("integer", "d")  # d: GENERATED BY DEFAULT
    assert (await _identity_sequence(target, "Ledger", "LedgerID"))[:2] == (100000, 5)
    batch = await _column(target, "Batch", "BatchID")
    assert (batch["type"], batch["identity"]) == ("bigint", "d")
    assert (await _identity_sequence(target, "Batch", "BatchID"))[:2] == (1, 1)

    # The identity numbers from its seed; money keeps four places exactly; the defaults apply.
    first = await _one(target, 'INSERT INTO "Ledger" ("Amount") VALUES (922337203685477.5807) RETURNING "LedgerID"')
    second = await _one(target, 'INSERT INTO "Ledger" ("Amount", "Fee") VALUES (0.0001, 214748.3647) '
                                'RETURNING "LedgerID"')
    assert (first, second) == (100000, 100005)
    assert str(await _one(target, 'SELECT "Amount" FROM "Ledger" WHERE "LedgerID" = 100000')) == "922337203685477.5807"
    assert await _one(target, 'SELECT "IsActive" AND NOT "IsVoid" FROM "Ledger" WHERE "LedgerID" = 100000') is True
    # The CHECKs, as translated, still mean what they said: void implies inactive, amount not negative.
    assert "CK_Ledger_VoidIsInactive" in await _refused(
        target, 'INSERT INTO "Ledger" ("Amount", "IsActive", "IsVoid") VALUES (1, TRUE, TRUE)')
    assert await _one(target, 'INSERT INTO "Ledger" ("Amount", "IsActive", "IsVoid") VALUES (1, FALSE, TRUE) '
                              'RETURNING "LedgerID"') == 100010
    assert "CK_Ledger_Amount" in await _refused(target, 'INSERT INTO "Ledger" ("Amount") VALUES (-0.01)')

    # Without the options, hierarchyid and geography are the named gaps' types.
    assert (await _column(target, "Batch", "Node"))["type"] == "character varying"
    assert (await _column(target, "Batch", "Location"))["type"] == "text"


@needs_postgres
async def test_negative_control_without_the_bit_mapping_postgresql_refuses_the_check(
    target: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With bit unmapped (a named gap, written TEXT), the translated CHECK
    compares text with an integer, and PostgreSQL refuses the table."""
    monkeypatch.setattr(ddl_export, "TYPE_MAPPINGS", tuple(m for m in ddl_export.TYPE_MAPPINGS if m.type != "BIT"))
    refused = await _apply(target, _export("tsql", "type_mappings").statements)
    assert any("operator does not exist: text = integer" in r for r in refused), refused[:2]


@needs_postgres
async def test_hierarchyid_as_ltree_on_postgresql(target: AsyncEngine) -> None:
    export = _export("tsql", "type_mappings", frozenset({"ltree"}))
    assert export.statements[0] == "CREATE EXTENSION IF NOT EXISTS ltree"
    assert await _apply(target, export.statements) == []
    assert (await _column(target, "Batch", "Node"))["type"] == "ltree"
    # ltree's own operators work on it: the depth of a path is nlevel().
    await _run(target, """INSERT INTO "Batch" ("Node") VALUES ('1.3.7')""")
    assert await _one(target, 'SELECT nlevel("Node") FROM "Batch"') == 3


# --- Oracle: identity on NUMBER and INTEGER, a trigger-filled column ----------------

@needs_postgres
async def test_oracle_identity_columns_on_postgresql(target: AsyncEngine) -> None:
    export = _export("oracle", "identity")
    assert await _apply(target, export.statements) == []

    # NUMBER(*,0): a sequence default with the source's seed, on NUMERIC(38,0).
    account = await _column(target, "ACCOUNTS", "ACCOUNT_ID")
    assert (account["type"], account["identity"]) == ("numeric(38,0)", "")
    assert account["default"] == "nextval('accounts_account_id_seq'::regclass)"
    assert (await _sequence(target, "accounts_account_id_seq"))[:2] == (393, 1)
    assert await _one(target, """INSERT INTO "ACCOUNTS" ("NAME") VALUES ('a') RETURNING "ACCOUNT_ID\"""") == 393

    # INTEGER: an identity column, BY DEFAULT, with its seed and increment.
    ticket = await _column(target, "TICKETS", "TICKET_ID")
    assert (ticket["type"], ticket["identity"]) == ("integer", "d")
    assert (await _identity_sequence(target, "TICKETS", "TICKET_ID"))[:2] == (7, 3)
    assert [await _one(target, """INSERT INTO "TICKETS" ("TITLE") VALUES ('t') RETURNING "TICKET_ID\"""")
            for _ in range(2)] == [7, 10]

    # The trigger-filled column is a named gap: nothing numbers it here.
    notes = await _column(target, "NOTES", "NOTE_ID")
    assert (notes["identity"], notes["default"]) == ("", None)
    assert "null value" in await _refused(target, """INSERT INTO "NOTES" ("BODY") VALUES ('n')""")


# --- PostgreSQL to PostgreSQL: the sequence is created and the default kept ----------

@needs_postgres
async def test_a_postgresql_sequence_default_on_postgresql(target: AsyncEngine) -> None:
    export = _export("postgres", "sequences")
    assert await _apply(target, export.statements) == []
    assert await _sequence(target, "public.invoice_no_seq") == (1000, 5, 1000, 999999)
    column = await _column(target, "invoice", "invoice_no")
    assert column["default"] == "nextval('invoice_no_seq'::regclass)"
    numbers = [await _one(target, "INSERT INTO invoice (amount) VALUES (1) RETURNING invoice_no") for _ in range(2)]
    assert numbers == [1000, 1005]


# --- PostGIS ------------------------------------------------------------------------

@pytest_asyncio.fixture
async def postgis() -> AsyncIterator[AsyncEngine]:
    """An empty database on the PostGIS server, dropped afterwards."""
    server = os.environ.get(POSTGIS_ENV, "")
    assert server.startswith("postgresql"), "no PostGIS test server"
    name = f"mbgis_{uuid.uuid4().hex[:16]}"
    admin = _admin_connection(server)
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{name}"')
    finally:
        admin.close()
    engine = create_async_engine(make_url(server).set(database=name).render_as_string(hide_password=False))
    yield engine
    await engine.dispose()
    admin = _admin_connection(server)
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        admin.close()


@needs_postgis
async def test_geography_as_postgis_geography(postgis: AsyncEngine) -> None:
    export = _export("tsql", "type_mappings", frozenset({"postgis"}))
    assert export.statements[0] == "CREATE EXTENSION IF NOT EXISTS postgis"
    assert await _apply(postgis, export.statements) == []
    assert (await _column(postgis, "Batch", "Location"))["type"] == "geography"
    await _run(postgis, """INSERT INTO "Batch" ("Location") VALUES (ST_GeogFromText('SRID=4326;POINT(-122.33 47.61)'))""")
    assert await _one(postgis, 'SELECT ST_AsText("Location") FROM "Batch"') == "POINT(-122.33 47.61)"
