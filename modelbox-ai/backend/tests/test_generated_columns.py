"""SQL Server computed columns exported as PostgreSQL generated columns (Sprint 9 Step 1b).

What the export does:

* an expression is translated only when every node in it is on the allowlist
  (column references, numeric and string literals, arithmetic, COALESCE, CAST);
  sqlglot writes ISNULL as COALESCE and CONVERT as CAST;
* ModelBox's own rewrite writes ``+`` as ``||`` where either side is a string
  literal or a cast to a character type (sqlglot keeps ``+``, which PostgreSQL
  refuses for text);
* anything else (a function or method call, or an unknown node) is a named
  gap quoting the file's own text;
* every generated column is labelled with where the source stores it
  ("virtual in source" or, for PERSISTED, "stored in source"), "stored in
  target", and how its type was chosen.

Expected values are derived here from the fixtures' own text by patterns
that share nothing with the importer or the exporter, never written by hand.
PostgreSQL's acceptance is ``test_type_mappings_on_postgres``, and the
AdventureWorks export applied whole is ``test_ddl_on_postgres``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlglot
from sqlalchemy import Uuid, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlglot import exp

from app.models.metadata_store import Base, DataModel, Workspace
from app.schemas.data_model import SynthesizedModel
from app.services import ddl_export
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService
from app.services.graph_repository import GraphRepository
from app.services.synthesis_engine import SynthesisEngine
from tests._test_db import make_test_engine

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASE = FIXTURES / "ddl_mappings" / "tsql" / "computed_columns.sql"
ADVENTUREWORKS = FIXTURES / "ddl" / "tsql" / "adventureworks.sql"

# A computed column as the file declares it, one per line: [name]  AS (…) [PERSISTED] [NOT NULL][,]
_DECLARED = re.compile(r"^\s*\[(?P<name>\w+)\]\s+AS\s+(?P<expr>\(.*\))(?P<persisted>\s+PERSISTED)?"
                       r"(?:\s+NOT\s+NULL)?\s*,?\s*$", re.IGNORECASE | re.MULTILINE)
_TABLE = re.compile(r"^CREATE\s+TABLE\s+\[\w+\]\.\[(?P<table>\w+)\]", re.IGNORECASE | re.MULTILINE)
# A call the allowlist refuses: a method or schema-qualified function ([a].[b](…)),
# or any function other than ISNULL and CONVERT.
_CALL = re.compile(r"\]\s*\.\s*\[\w+\]\s*\(|\b(?!isnull\b|convert\b)[a-z_]\w*\s*\(", re.IGNORECASE)


def _declared(path: Path) -> dict[tuple[str, str], tuple[str, bool]]:
    """(table, column) -> (expression as written, PERSISTED), read from the file's text."""
    body = path.read_text(encoding="utf-8")
    tables = [(m.start(), m.group("table")) for m in _TABLE.finditer(body)]
    found: dict[tuple[str, str], tuple[str, bool]] = {}
    for match in _DECLARED.finditer(body):
        table = next(name for start, name in reversed(tables) if start < match.start())
        found[(table, match.group("name"))] = (match.group("expr"), bool(match.group("persisted")))
    return found


def _refused(declared: dict[tuple[str, str], tuple[str, bool]]) -> set[tuple[str, str]]:
    return {key for key, (expr, _) in declared.items() if _CALL.search(expr)}


def _import(path: Path) -> SynthesizedModel:
    result = import_ddl(path.read_bytes(), "tsql", path.name)
    assert result.status == "reconciled" and result.model is not None, result.report["failures"][:3]
    return result.model


def _export(model: SynthesizedModel, target: str = "postgres") -> ddl_export.DdlExport:
    return ExporterService(source_dialect="tsql").generate_ddl_export(model, target)


def _generated(export: ddl_export.DdlExport) -> dict[tuple[str, str], tuple[str, exp.Expression]]:
    """(table, column) -> (declared type, generation expression) for each generated column emitted."""
    out: dict[tuple[str, str], tuple[str, exp.Expression]] = {}
    for statement in export.statements:
        tree = sqlglot.parse_one(statement, read="postgres")
        if not (isinstance(tree, exp.Create) and isinstance(tree.this, exp.Schema)):
            continue
        for column in tree.this.expressions:
            computed = column.find(exp.ComputedColumnConstraint) if isinstance(column, exp.ColumnDef) else None
            if computed is not None:
                out[(tree.this.this.name, column.name)] = (column.args["kind"].sql("postgres"), computed.this)
    return out


def _gaps(export: ddl_export.DdlExport, kind: str) -> dict[tuple[str, str], str]:
    return {(g.entity or "", g.detail.split(" ", 1)[0].rstrip(":")): g.detail for g in export.gaps if g.kind == kind}


# --- The importer keeps the expression as the file wrote it -------------------------

@pytest.mark.parametrize("path", [CASE, ADVENTUREWORKS], ids=["case", "adventureworks"])
def test_the_model_holds_each_expression_exactly_as_declared(path: Path) -> None:
    declared = _declared(path)
    assert declared, "fixture sanity: the file declares computed columns"
    held = {(e.entity_name, c.name): (c.computed_expression, c.computed_persisted)
            for e in _import(path).entities for c in e.columns if c.data_type == "COMPUTED"}
    assert held == declared


# --- Emitted, or a named gap quoting the file --------------------------------------

def _counts(path: Path) -> tuple[int, int]:
    declared = _declared(path)
    return len(declared) - len(_refused(declared)), len(_refused(declared))


@pytest.mark.parametrize(
    "path", [CASE, ADVENTUREWORKS],
    ids=[f"{p.stem}-{e}-emitted-{r}-gaps" for p in (CASE, ADVENTUREWORKS) for e, r in [_counts(p)]])
def test_each_computed_column_is_emitted_or_a_gap_quoting_the_file(path: Path) -> None:
    declared = _declared(path)
    refused = _refused(declared)
    export = _export(_import(path))
    emitted, gaps = _generated(export), _gaps(export, "computed_column")
    assert set(emitted) == set(declared) - refused
    assert set(gaps) == refused
    for key in refused:
        # The gap quotes the expression as the file declared it.
        assert f"{key[1]} AS {declared[key][0]}:" in gaps[key], gaps[key]


def test_adventureworks_is_seven_emitted_and_three_gaps() -> None:
    """The count the prompt expects, derived from the file rather than asserted
    in the abstract: its ten computed columns, three of which call a method or a
    function the model does not hold."""
    emitted, refused = _counts(ADVENTUREWORKS)
    export = _export(_import(ADVENTUREWORKS))
    assert (len(_generated(export)), len(_gaps(export, "computed_column"))) == (emitted, refused) == (7, 3)


def test_a_method_and_a_function_are_named_as_what_they_are() -> None:
    gaps = _gaps(_export(_import(ADVENTUREWORKS)), "computed_column")
    assert "calls the method GetLevel() on OrganizationNode" in gaps[("Employee", "OrganizationLevel")]
    assert "calls the function [dbo].[ufnLeadingZeros]" in gaps[("Customer", "AccountNumber")]


# --- The label ----------------------------------------------------------------------

@pytest.mark.parametrize("path", [CASE, ADVENTUREWORKS], ids=["case", "adventureworks"])
def test_every_generated_column_is_labelled_by_where_the_source_stores_it(path: Path) -> None:
    declared = _declared(path)
    labels = _gaps(_export(_import(path)), "generated_column")
    assert set(labels) == set(declared) - _refused(declared)
    for key, label in labels.items():
        storage = "stored in source" if declared[key][1] else "virtual in source"
        assert f"{key[1]}: {storage}, stored in target; type " in label, label


# --- The + rewrite ------------------------------------------------------------------

def _pluses_between_strings(node: exp.Expression) -> list[exp.Add]:
    return [a for a in node.find_all(exp.Add) if ddl_export._is_string(a.this) or ddl_export._is_string(a.expression)]


def test_string_plus_is_written_as_concatenation_and_numeric_plus_is_not() -> None:
    emitted = _generated(_export(_import(CASE)))
    order_type, order_number = emitted[("OrderLine", "OrderNumber")]
    assert order_type == "TEXT" and order_number.find(exp.DPipe) is not None
    assert _pluses_between_strings(order_number) == []
    _, total = emitted[("OrderLine", "TotalDue")]
    assert total.find(exp.DPipe) is None and total.find(exp.Add) is not None, "numeric + stays +"


def test_negative_control_without_the_rewrite_a_string_plus_remains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ddl_export, "concatenate_strings", lambda expression: expression)
    _, order_number = _generated(_export(_import(CASE)))[("OrderLine", "OrderNumber")]
    assert order_number.find(exp.DPipe) is None and _pluses_between_strings(order_number)


def test_sqlglot_itself_keeps_the_string_plus() -> None:
    """Why the rewrite is ours: sqlglot writes T-SQL's + between strings as +."""
    written = sqlglot.transpile("SELECT N'SO' + CONVERT(NVARCHAR(23), x)", read="tsql", write="postgres")[0]
    assert " + " in written and "||" not in written


# --- Types --------------------------------------------------------------------------

def test_each_type_is_chosen_as_its_label_says() -> None:
    export = _export(_import(CASE))
    emitted, labels = _generated(export), _gaps(export, "generated_column")
    for key, (declared_type, _) in emitted.items():
        stated = labels[key].split("; type ", 1)[1]
        # sqlglot writes an unbounded NUMERIC as DECIMAL; the label says NUMERIC.
        assert stated.startswith("NUMERIC" if declared_type == "DECIMAL" else declared_type), (key, stated)
    # Integer arithmetic stays integer; money with integers is money's exact mapping;
    # money times a decimal literal, and decimal arithmetic, are NUMERIC; a string is TEXT.
    assert emitted[("OrderLine", "StockedQty")][0] == "INT"
    assert emitted[("OrderLine", "TotalDue")][0] == "DECIMAL(19, 4)"
    assert emitted[("OrderLine", "LineTotal")][0] == emitted[("OrderLine", "AcceptedQty")][0] == "DECIMAL"
    assert emitted[("OrderLine", "OrderNumber")][0] == "TEXT"


# --- Other gaps ---------------------------------------------------------------------

def test_another_target_names_each_computed_column() -> None:
    declared = _declared(CASE)
    gaps = _gaps(_export(_import(CASE), "snowflake"), "computed_column")
    assert set(gaps) == set(declared)
    assert all("PostgreSQL only" in d for key, d in gaps.items() if key not in _refused(declared))


def test_a_generated_column_cannot_read_another() -> None:
    model = _import(CASE)
    line = next(c for c in model.entities[0].columns if c.name == "LineTotal")
    line.computed_expression = "([TotalDue]*(2))"
    gap = _gaps(_export(model), "computed_column")[("OrderLine", "LineTotal")]
    assert "reads the computed column TotalDue" in gap


def test_a_model_without_the_expression_names_the_column() -> None:
    model = _import(CASE)
    for column in model.entities[0].columns:
        column.computed_expression = None
    gaps = _gaps(_export(model), "computed_column")
    assert set(gaps) == set(_declared(CASE)) and all("holds no expression" in d for d in gaps.values())


# --- Stored and reopened, read back raw ---------------------------------------------

@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def test_the_expression_is_stored_and_reopened(session: AsyncSession) -> None:
    model = _import(CASE)
    workspace = Workspace(name="computed")
    session.add(workspace)
    await session.flush()
    row = DataModel(workspace_id=workspace.workspace_id, title="computed", target_dialect="tsql",
                    current_paradigm="3NF")
    session.add(row)
    await session.flush()
    await GraphRepository(session).replace_graph(row.model_id, model.entities, model.relationships)
    await session.commit()

    stored = (await session.execute(text(
        "SELECT c.column_name, c.computed_expression, c.computed_persisted FROM entity_columns c "
        "JOIN model_entities e ON e.entity_id = c.entity_id WHERE e.model_id = :m "
        "AND c.computed_expression IS NOT NULL").bindparams(bindparam("m", type_=Uuid)),
        {"m": row.model_id})).all()
    declared = {name: value for (_, name), value in _declared(CASE).items()}
    assert {name: (expr, bool(persisted)) for name, expr, persisted in stored} == declared

    reopened = await SynthesisEngine(session, None).get_model(row.model_id)  # type: ignore[arg-type]
    assert reopened is not None
    before = {c.name: (c.computed_expression, c.computed_persisted) for c in model.entities[0].columns}
    assert {c.name: (c.computed_expression, c.computed_persisted) for c in reopened.entities[0].columns} == before
