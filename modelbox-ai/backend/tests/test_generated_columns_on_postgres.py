"""Computed columns as generated columns, applied to a real PostgreSQL (Sprint 9 Step 1b).

``test_generated_columns`` asserts what the export says; this asserts what
PostgreSQL 16.15 makes of it. It accepts every emitted generation
expression, immutability included, and marks each column generated
(``pg_attribute.attgenerated = 's'``). A row inserted with chosen inputs
gets the values the source's expressions compute. Those values are
computed here, in Python, from the same inputs.

The negative control removes the ``+`` to ``||`` rewrite: PostgreSQL then
refuses AdventureWorks' SalesOrderNumber expression, and the table with it.

Runs where the suite has a PostgreSQL server (the "Backend Pytest
(Postgres)" job); there a missing server fails rather than skips.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services import ddl_export
from tests._test_db import DATABASE_ENV, make_test_engine
from tests.test_ddl_on_postgres import _apply
from tests.test_generated_columns import (
    ADVENTUREWORKS,
    CASE,
    _declared,
    _export,
    _generated,
    _import,
    _refused,
)

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

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
async def target() -> AsyncIterator[AsyncEngine]:
    engine = make_test_engine()
    assert engine.dialect.name == "postgresql", "fixture sanity: this test applies DDL to PostgreSQL"
    yield engine
    await engine.dispose()


async def _generated_columns(engine: AsyncEngine) -> set[tuple[str, str]]:
    async with engine.connect() as conn:
        rows = (await conn.exec_driver_sql(
            "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND a.attgenerated::text = 's'")).all()
    return {(table, column) for table, column in rows}


async def test_postgresql_computes_what_the_source_computes(target: AsyncEngine) -> None:
    export = _export(_import(CASE))
    assert await _apply(target, export.statements) == []
    assert await _generated_columns(target) == set(_generated(export))

    inputs = {"Qty": 3, "ScrappedQty": 1, "UnitPrice": Decimal("12.3400"), "UnitPriceDiscount": Decimal("0.1000"),
              "SubTotal": Decimal("100.1234"), "TaxAmt": Decimal("8.0100"), "Freight": Decimal("2.5000"),
              "ReceivedQty": Decimal("10.50"), "RejectedQty": Decimal("0.25")}
    columns = ", ".join(f'"{name}"' for name in inputs)
    values = ", ".join(str(value) for value in inputs.values())
    async with target.begin() as conn:
        row = (await conn.exec_driver_sql(
            f'INSERT INTO "OrderLine" ({columns}) VALUES ({values}) RETURNING "OrderID", "OrderNumber", '
            '"LineTotal", "TotalDue", "StockedQty", "AcceptedQty"')).mappings().one()

    # The seed the file declares, and each expression computed from the inputs.
    seed = int(re.search(r"\[OrderID\]\s+\[int\]\s+IDENTITY\((\d+),", CASE.read_text(encoding="utf-8")).group(1))
    expected = {
        "OrderID": seed,
        "OrderNumber": f"SO{seed}",
        "LineTotal": inputs["UnitPrice"] * (Decimal("1.0") - inputs["UnitPriceDiscount"]) * inputs["Qty"],
        "TotalDue": inputs["SubTotal"] + inputs["TaxAmt"] + inputs["Freight"],
        "StockedQty": inputs["Qty"] - inputs["ScrappedQty"],
        "AcceptedQty": inputs["ReceivedQty"] - inputs["RejectedQty"],
    }
    assert dict(row) == expected


async def test_every_adventureworks_generated_column_is_accepted(target: AsyncEngine) -> None:
    declared = _declared(ADVENTUREWORKS)
    export = _export(_import(ADVENTUREWORKS))
    assert await _apply(target, export.statements) == []
    assert len(await _generated_columns(target)) == len(declared) - len(_refused(declared))


async def test_negative_control_without_the_rewrite_postgresql_refuses_sales_order_number(
    target: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ddl_export, "concatenate_strings", lambda expression: expression)
    refused = await _apply(target, _export(_import(ADVENTUREWORKS)).statements)
    table = [r for r in refused if r.startswith('CREATE TABLE "SalesOrderHeader"')]
    assert table and "operator does not exist" in table[0], refused[:3]
