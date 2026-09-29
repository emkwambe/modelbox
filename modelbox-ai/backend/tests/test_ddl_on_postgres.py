"""The exported PostgreSQL DDL, applied to a real PostgreSQL, matches the catalog.

Sprint 8 Step 4a, item 1. Step 3's round trip checked the exported DDL by
importing it again, which proves ModelBox can read what it wrote, not that
PostgreSQL accepts it. Here each certified fixture (Oracle HR, Oracle CO,
Pagila, AdventureWorks) is imported, saved, reopened and exported as
PostgreSQL DDL, the DDL is **applied to the appliance's own PostgreSQL 16.15**,
and tables, columns, primary keys, foreign keys, CHECK constraints and table
and column descriptions are **counted from that database's catalog**
(`pg_class`, `pg_attribute`, `pg_constraint`, `pg_description`), then compared
with the original catalog manifest. As in Step 3, the expected shortfall is
computed from the named export gaps and must equal the actual shortfall
exactly. Partitions are excluded, as in Step 3.

Every statement is applied in its own transaction, so one failure cannot hide
another; any statement PostgreSQL refuses fails the test, with its error.

Runs where the suite has a PostgreSQL server (the CI job "Backend Pytest
(Postgres)", where ``MODELBOX_TEST_DATABASE_EXPECT=postgresql``). There it
cannot skip: a missing server fails. On the SQLite run it skips, saying why.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.metadata_store import Base
from app.services import ddl_export
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService
from tests._test_db import DATABASE_ENV, make_test_engine
from tests.test_ddl_round_trip import (
    CERTIFIED,
    COMPARED,
    DDL,
    _differences,
    _expected_shortfall,
    _manifest_tables,
    _save_and_reopen,
)

ON_POSTGRES = os.environ.get("MODELBOX_TEST_DATABASE_EXPECT") == "postgresql"

pytestmark = pytest.mark.skipif(
    not ON_POSTGRES and not os.environ.get(DATABASE_ENV),
    reason="needs the PostgreSQL test server (the Backend Pytest (Postgres) job runs it)",
)


def test_the_postgres_job_has_its_server() -> None:
    """A skipped gate must be loud: where PostgreSQL is expected, it is present."""
    if ON_POSTGRES:
        assert os.environ.get(DATABASE_ENV, "").startswith("postgresql"), "no PostgreSQL test server"


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def target() -> AsyncIterator[AsyncEngine]:
    """An empty PostgreSQL database the exported DDL is applied to."""
    engine = make_test_engine()
    assert engine.dialect.name == "postgresql", "fixture sanity: this test applies DDL to PostgreSQL"
    yield engine
    await engine.dispose()


async def _apply(engine: AsyncEngine, statements: list[str]) -> list[str]:
    """Apply each statement in its own transaction; PostgreSQL's refusals, by statement."""
    refused: list[str] = []
    for statement in statements:
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(statement)
        except Exception as exc:  # noqa: BLE001 - every refusal is reported, whatever its class
            head = " ".join(statement.split())[:120]
            refused.append(f"{head}\n    -> {str(exc).splitlines()[0][:300]}")
    return refused


# Counted from PostgreSQL's own catalog, per ordinary table in the public schema.
_CATALOG_COUNTS = """
SELECT c.relname AS table_name,
  (SELECT count(*) FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped)
    AS columns,
  (SELECT count(*) FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') AS primary_keys,
  (SELECT count(*) FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'f') AS foreign_keys,
  (SELECT count(*) FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'c') AS check_constraints,
  (SELECT count(*) FROM pg_description d WHERE d.objoid = c.oid AND d.classoid = 'pg_class'::regclass
     AND d.objsubid = 0 AND d.description <> '') AS table_descriptions,
  (SELECT count(*) FROM pg_description d WHERE d.objoid = c.oid AND d.classoid = 'pg_class'::regclass
     AND d.objsubid > 0 AND d.description <> '') AS column_descriptions
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
"""


async def _catalog(engine: AsyncEngine) -> dict[str, dict[str, int]]:
    async with engine.connect() as conn:
        rows = (await conn.exec_driver_sql(_CATALOG_COUNTS)).mappings().all()
    return {row["table_name"]: {kind: int(row[kind]) for kind in COMPARED} for row in rows}


async def _export(session: AsyncSession, dialect: str, stem: str) -> tuple[ddl_export.DdlExport, object]:
    imported = import_ddl((DDL / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert imported.status == "reconciled" and imported.model is not None
    reopened = await _save_and_reopen(session, imported.model, dialect)
    return ExporterService(source_dialect=dialect).generate_ddl_export(reopened, "postgres"), reopened


@pytest.mark.parametrize(("dialect", "stem"), CERTIFIED, ids=[s for _, s in CERTIFIED])
async def test_postgresql_accepts_the_export_and_its_catalog_matches_the_manifest(
    session: AsyncSession, target: AsyncEngine, dialect: str, stem: str
) -> None:
    export, reopened = await _export(session, dialect, stem)
    refused = await _apply(target, export.statements)
    assert refused == [], f"PostgreSQL refused {len(refused)} statements:\n" + "\n".join(refused)
    catalog = _manifest_tables(dialect, stem)
    applied = await _catalog(target)
    assert _differences(catalog, applied) == _expected_shortfall(reopened, export.gaps)  # type: ignore[arg-type]


async def test_negative_control_an_invalid_export_makes_the_check_fail(
    session: AsyncSession, target: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the TINYINT substitution, AdventureWorks' DDL names a type
    PostgreSQL does not have, and applying it is refused."""
    monkeypatch.setitem(ddl_export._TYPE_GAPS, "postgres",
                        {k: v for k, v in ddl_export._TYPE_GAPS["postgres"].items() if k != "UTINYINT"})
    export, _ = await _export(session, "tsql", "adventureworks")
    refused = await _apply(target, export.statements)
    assert refused, "the invalid export was accepted"
    assert all("utinyint" in r.lower() for r in refused), refused[:3]
