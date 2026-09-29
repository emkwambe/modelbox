"""SQL Server import: GO batches, the SQL Server normalizer, constraints added
by ALTER TABLE, MS_Description extended properties and user-defined types.

The real cases come from the AdventureWorks export in
`tests/fixtures/ddl/tsql/`, written by SSMS. Where that export never uses a
form SSMS can write (a partition scheme, WITH NOCHECK, CHECK NOT FOR
REPLICATION, a USE or a procedure), the case is a short synthetic batch in
SSMS's own layout, and says so.

Every check has a negative control that turns off exactly the piece under test
and shows the check then fails.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.services.ddl_import import counter, importer, splitter, sqlserver_normalizer
from app.services.ddl_import.importer import ImportResult, import_ddl
from app.services.ddl_import.report import to_markdown

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
AW = (DDL / "tsql" / "adventureworks.sql").read_text(encoding="utf-8")


def _file(*batches: str) -> bytes:
    return "".join(f"{batch}\nGO\n" for batch in batches).encode()


def _entity(result: ImportResult, name: str):
    assert result.model is not None, result.report["failures"]
    return next(e for e in result.model.entities if e.entity_name == name)


def _column(result: ImportResult, table: str, column: str):
    return next(c for c in _entity(result, table).columns if c.name == column)


# --- GO batches -------------------------------------------------------------------

SCRIPT = (
    "USE [Sales]",
    "SET ANSI_NULLS ON",
    "SET QUOTED_IDENTIFIER ON",
    ("CREATE TABLE [dbo].[Note](\n\t[NoteID] [int] NOT NULL,\n\t[Body] [nvarchar](40) NULL DEFAULT (N'a;b'),\n"
     " CONSTRAINT [PK_Note] PRIMARY KEY CLUSTERED \n(\n\t[NoteID] ASC\n)"
     "WITH (PAD_INDEX = OFF, IGNORE_DUP_KEY = OFF) ON [PRIMARY]\n) ON [PRIMARY]"),
    "CREATE PROCEDURE [dbo].[Touch] AS\nBEGIN\n\tSELECT 1;\n\tSELECT 2;\nEND",
    "CREATE VIEW [dbo].[Notes] AS SELECT [NoteID] FROM [dbo].[Note]",
)


def test_tsql_splits_at_go_lines_and_keeps_each_batch_whole() -> None:
    text = _file(*SCRIPT).decode().replace("END\nGO\n", "END\nGO 2\n").replace("[Note]\nGO\n", "[Note]\ngo\n")
    statements = splitter.split(text, "tsql")
    assert [s.kind for s in statements] == ["sql", "sql", "sql", "sql", "procedural", "sql"]
    assert statements[3].text.startswith("CREATE TABLE [dbo].[Note]") and "N'a;b'" in statements[3].text
    assert statements[4].text.endswith("SELECT 2;\nEND")
    assert [s.line for s in statements] == [1, 3, 5, 7, 16, 22]


def test_set_and_use_are_listed_and_procedures_are_listed_not_dropped() -> None:
    result = import_ddl(_file(*SCRIPT), "tsql")
    assert result.status == "reconciled", result.report["failures"]
    reasons = [(item["reason"], item["statement"].split()[0]) for item in result.report["not_imported"]]
    assert reasons == [("database selection", "USE"), ("session setting", "SET"), ("session setting", "SET"),
                       ("procedural object", "CREATE"), ("view", "CREATE")]
    assert _column(result, "Note", "NoteID").is_primary_key


def test_negative_control_without_go_splitting_the_table_is_not_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(splitter, "_GO", re.compile(r"(?!x)x"))
    result = import_ddl(_file(*SCRIPT), "tsql")
    assert result.status == "unreconciled"
    assert result.model is None


def test_a_skipped_batch_cannot_carry_a_table_past_the_importer() -> None:
    """SSMS separates statements with GO, but a hand-edited batch may not."""
    result = import_ddl(_file("SET ANSI_NULLS ON\nCREATE TABLE [dbo].[T]([a] [int] NULL)"), "tsql")
    assert result.status == "unreconciled"
    assert [f["statement"] for f in result.report["failures"]] == [1]


def test_negative_control_without_the_batch_guard_the_table_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer, "_LATER_TABLE_STATEMENT", re.compile(r"(?!x)x"))
    statement = splitter.split("SET ANSI_NULLS ON\nCREATE TABLE [dbo].[T]([a] [int] NULL)\nGO\n", "tsql")[0]
    assert importer.classify(statement) == ("skipped", "session setting")


def test_adventureworks_is_1943_batches_each_imported_or_listed() -> None:
    statements = splitter.split(AW, "tsql")
    kinds: dict[str, int] = {}
    for statement in statements:
        kind, _ = importer.classify(statement)
        kinds[kind] = kinds.get(kind, 0) + 1
    assert len(statements) == 1943
    assert kinds == {"extended_property": 1062, "skipped": 473, "alter_table": 179, "add_default": 152,
                     "create_table": 71, "type_alias": 6}


# --- The SQL Server normalizer: every rule has a case and a negative control ----------

# Forms SSMS writes that the AdventureWorks export happens not to use.
SYNTHETIC = {
    "partition_scheme": _file(
        "CREATE TABLE [dbo].[Reading](\n\t[TakenOn] [date] NOT NULL,\n\t[Value] [int] NULL\n)"
        " ON [ps_by_month]([TakenOn])"),
    "check_mode": _file(
        "CREATE TABLE [dbo].[Stock](\n\t[Qty] [int] NULL\n) ON [PRIMARY]",
        "ALTER TABLE [dbo].[Stock]  WITH NOCHECK ADD  CONSTRAINT [CK_Stock_Qty] CHECK  (([Qty]>=(0)))"),
    "not_for_replication": _file(
        "CREATE TABLE [dbo].[Stock](\n\t[Qty] [int] NULL\n) ON [PRIMARY]",
        "ALTER TABLE [dbo].[Stock]  WITH CHECK ADD  CONSTRAINT [CK_Stock_Qty] CHECK NOT FOR REPLICATION "
        "(([Qty]>=(0)))"),
}


def _faithful(result: ImportResult, raw: bytes) -> bool:
    """Imported with nothing lost: reconciled, and a partition scheme kept as metadata."""
    if result.status != "reconciled":
        return False
    if b" ON [ps_by_month]" in raw:
        return result.report["held"].get("Reading", {}).get("partitioning") == "ON [ps_by_month]([TakenOn])"
    return True


@contextmanager
def _without(rule: str) -> Iterator[None]:
    original = sqlserver_normalizer.normalize
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sqlserver_normalizer, "normalize",
                      lambda text, disabled=frozenset(): original(text, disabled | {rule}))
        yield


_CASES: dict[str, bytes] = {}


def _case_for(rule: str) -> bytes:
    """A file on which ``rule`` fires and without which the import is not faithful:
    a real AdventureWorks table where there is one, else the synthetic case."""
    if rule in _CASES:
        return _CASES[rule]
    if rule in SYNTHETIC:
        _CASES[rule] = SYNTHETIC[rule]
        return _CASES[rule]
    for statement in splitter.split(AW, "tsql"):
        if importer.classify(statement)[0] != "create_table":
            continue
        if rule not in sqlserver_normalizer.normalize(statement.text).applied:
            continue
        raw = _file(statement.text)
        with _without(rule):
            broken = import_ddl(raw, "tsql")
        if not _faithful(broken, raw):
            _CASES[rule] = raw
            return raw
    raise AssertionError(f"no AdventureWorks table shows rule {rule!r} is needed")


@pytest.mark.parametrize("rule", sqlserver_normalizer.RULE_NAMES)
def test_each_normalizer_rule_is_what_makes_its_case_import(rule: str) -> None:
    raw = _case_for(rule)
    result = import_ddl(raw, "tsql")
    assert result.report["normalizer"].get(rule, 0) >= 1
    assert _faithful(result, raw), result.report["failures"]


@pytest.mark.parametrize("rule", sqlserver_normalizer.RULE_NAMES)
def test_negative_control_each_rule_disabled_makes_its_case_fail(rule: str) -> None:
    raw = _case_for(rule)
    with _without(rule):
        assert not _faithful(import_ddl(raw, "tsql"), raw)


def test_the_counter_counts_a_check_not_for_replication() -> None:
    """Otherwise the import of that CHECK would reconcile as a gap it did not cause."""
    per_table = counter.count(SYNTHETIC["not_for_replication"].decode(), "tsql")
    assert per_table["Stock"].counts["check_constraints"] == 1


def test_every_rule_fires_on_adventureworks_or_has_a_synthetic_case() -> None:
    fired = _import_aw().report["normalizer"]
    assert set(sqlserver_normalizer.RULE_NAMES) == set(fired) | set(SYNTHETIC)


# Research R1: a prototype that stripped WITH ( … ) greedily took the primary
# key with it. This is the statement shape SSMS writes for every key.
def _aw_table(name: str) -> str:
    return next(s.text for s in splitter.split(AW, "tsql") if s.text.startswith(f"CREATE TABLE {name}("))


def test_regression_a_clustered_primary_key_with_options_on_primary_survives_normalization() -> None:
    statement = _aw_table("[Person].[AddressType]")
    assert re.search(r"PRIMARY KEY CLUSTERED\s*\(\s*\[AddressTypeID\] ASC\s*\)WITH \(PAD_INDEX = OFF.*\) ON \[PRIMARY\]",
                     statement, re.DOTALL), "fixture sanity: not the SSMS key shape"
    result = import_ddl(_file(statement), "tsql")
    assert result.status == "reconciled"
    assert [c.name for c in _entity(result, "AddressType").columns if c.is_primary_key] == ["AddressTypeID"]


def test_negative_control_a_greedy_with_strip_loses_the_primary_key(monkeypatch: pytest.MonkeyPatch) -> None:
    greedy = sqlserver_normalizer.Rule("index_options", "R1's prototype",
                                       lambda t: re.subn(r"\bWITH\s*\(.*\)", " ", t, flags=re.DOTALL))
    monkeypatch.setattr(sqlserver_normalizer, "RULES",
                        tuple(greedy if r.name == "index_options" else r for r in sqlserver_normalizer.RULES))
    result = import_ddl(_file(_aw_table("[Person].[AddressType]")), "tsql")
    keys = [] if result.model is None else [
        c.name for e in result.model.entities for c in e.columns if c.is_primary_key]
    assert keys != ["AddressTypeID"] or result.status != "reconciled"


def test_rules_never_touch_string_literals_or_bracketed_names() -> None:
    statement = ("CREATE TABLE [dbo].[T]([ON] [nvarchar](20) NULL DEFAULT (N'TEXTIMAGE_ON [x] ROWGUIDCOL'), "
                 "[CLUSTERED] [int] NULL) ON [PRIMARY]")
    normalized = sqlserver_normalizer.normalize(statement).text
    assert "[ON] [nvarchar](20)" in normalized
    assert "N'TEXTIMAGE_ON [x] ROWGUIDCOL'" in normalized
    assert "[CLUSTERED] [int]" in normalized
    assert "ON [PRIMARY]" not in normalized


# --- Constraints added by ALTER TABLE --------------------------------------------------

ALTERED = _file(
    "CREATE TABLE [dbo].[Customer](\n\t[CustomerID] [int] NOT NULL,\n"
    " CONSTRAINT [PK_Customer] PRIMARY KEY CLUSTERED \n(\n\t[CustomerID] ASC\n)"
    "WITH (PAD_INDEX = OFF) ON [PRIMARY]\n) ON [PRIMARY]",
    "CREATE TABLE [dbo].[Order](\n\t[OrderID] [int] NOT NULL,\n\t[CustomerID] [int] NULL,\n\t[Qty] [int] NULL\n)"
    " ON [PRIMARY]",
    "ALTER TABLE [dbo].[Order]  WITH CHECK ADD  CONSTRAINT [FK_Order_Customer] FOREIGN KEY([CustomerID])\n"
    "REFERENCES [dbo].[Customer] ([CustomerID])",
    "ALTER TABLE [dbo].[Order] CHECK CONSTRAINT [FK_Order_Customer]",
    "ALTER TABLE [dbo].[Order]  WITH NOCHECK ADD  CONSTRAINT [CK_Order_Qty] CHECK  (([Qty]>(0)))",
    "ALTER TABLE [dbo].[Order] NOCHECK CONSTRAINT [CK_Order_Qty]",
    "ALTER TABLE [dbo].[Order] ADD  CONSTRAINT [DF_Order_Qty]  DEFAULT ((1)) FOR [Qty]",
)


def test_constraints_added_with_check_and_with_nocheck_are_in_the_model() -> None:
    result = import_ddl(ALTERED, "tsql")
    assert result.status == "reconciled", result.report["failures"]
    assert result.model is not None
    assert [(r.from_ref, r.to_ref) for r in result.model.relationships] == [("Order.CustomerID", "Customer.CustomerID")]
    qty = _column(result, "Order", "Qty")
    assert qty.check_expression is not None and "0" in qty.check_expression
    assert qty.default_value == "((1))"
    # NOCHECK is recorded: the constraint holds for new rows, not those that existed.
    assert [n["index"] for n in result.report["not_validated"]] == [5]
    assert result.report["not_validated"][0]["statement"].startswith("ALTER TABLE [dbo].[Order] WITH NOCHECK ADD")
    states = [i["reason"] for i in result.report["not_imported"]]
    assert states == ["constraint state", "constraint state"]


def test_negative_control_alter_constraints_dropped_is_a_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer._Builder, "alter_table", lambda self, tree, statement: None)
    report = import_ddl(ALTERED, "tsql").report
    assert report["status"] == "unreconciled"
    assert {(g["table"], g["kind"]) for g in report["reconciliation"]["gaps"]} == {
        ("Order", "foreign_keys"), ("Order", "check_constraints")}


def test_the_constraint_state_rule_never_matches_adding_a_constraint() -> None:
    rule = dict(importer.SKIP_RULES)["constraint state"]
    assert rule.match("ALTER TABLE [dbo].[Order] WITH CHECK CHECK CONSTRAINT [FK_Order_Customer]")
    assert rule.match("ALTER TABLE [dbo].[Order] NOCHECK CONSTRAINT ALL")
    assert not rule.match("ALTER TABLE [dbo].[Order] WITH CHECK ADD CONSTRAINT [CK] CHECK (([Qty]>(0)))")
    assert not rule.match("ALTER TABLE [dbo].[Order] ADD CONSTRAINT [CK] CHECK (([Qty]>(0)))")


# --- MS_Description extended properties ----------------------------------------------

def _property(name: str, value: str, *levels: str) -> str:
    args = [f"@name=N'{name}'", f"@value=N'{value}'"]
    for n, (kind, target) in enumerate(zip(levels[::2], levels[1::2], strict=True)):
        args.append(f"@level{n}type=N'{kind}',@level{n}name=N'{target}'")
    return "EXEC sys.sp_addextendedproperty " + ", ".join(args)


DESCRIBED = _file(
    "CREATE TABLE [dbo].[Account](\n\t[AccountID] [int] NOT NULL,\n\t[Note] [nvarchar](20) NULL,\n"
    " CONSTRAINT [PK_Account] PRIMARY KEY CLUSTERED ([AccountID] ASC)\n) ON [PRIMARY]",
    _property("MS_Description", "An account''s ledger", "SCHEMA", "dbo", "TABLE", "Account"),
    _property("MS_Description", "Free text", "SCHEMA", "dbo", "TABLE", "Account", "COLUMN", "Note"),
    "EXEC sp_addextendedproperty N'MS_Description', N'Surrogate key', N'SCHEMA', N'dbo', N'TABLE', N'Account', "
    "N'COLUMN', N'AccountID'",
    _property("Owner", "finance", "SCHEMA", "dbo", "TABLE", "Account"),
    _property("MS_Description", "Primary key", "SCHEMA", "dbo", "TABLE", "Account", "CONSTRAINT", "PK_Account"),
    _property("MS_Description", "The default schema", "SCHEMA", "dbo"),
)


def test_ms_descriptions_are_in_the_model_and_other_properties_are_listed() -> None:
    result = import_ddl(DESCRIBED, "tsql")
    assert result.status == "reconciled", result.report["failures"]
    assert _entity(result, "Account").description == "An account's ledger"
    assert _column(result, "Account", "Note").description == "Free text"
    assert _column(result, "Account", "AccountID").description == "Surrogate key"
    assert [i["reason"] for i in result.report["not_imported"]] == [
        "extended property Owner on SCHEMA/TABLE",
        "extended property MS_Description on SCHEMA/TABLE/CONSTRAINT",
        "extended property MS_Description on SCHEMA",
    ]


def test_negative_control_descriptions_dropped_is_a_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer._Builder, "extended_property", lambda self, statement: None)
    report = import_ddl(DESCRIBED, "tsql").report
    assert report["status"] == "unreconciled"
    assert {(g["table"], g["kind"], g["source"], g["imported"]) for g in report["reconciliation"]["gaps"]} == {
        ("Account", "table_descriptions", 1, 0), ("Account", "column_descriptions", 2, 0)}


def test_adventureworks_lists_every_extended_property_that_is_not_a_description() -> None:
    counts = _import_aw_manifest_counts()
    listed = [i for i in _import_aw().report["not_imported"] if i["reason"].startswith("extended property")]
    described = counts["table_descriptions"] + counts["column_descriptions"]
    assert len(listed) == 1062 - described


# --- User-defined types -------------------------------------------------------------

TYPED = _file(
    "CREATE TYPE [dbo].[Name] FROM [nvarchar](50) NULL",
    "CREATE TABLE [dbo].[Place](\n\t[PlaceID] [uniqueidentifier] ROWGUIDCOL NOT NULL,\n\t[Name] [dbo].[Name] NOT NULL,\n"
    "\t[Login] [sysname] NOT NULL,\n\t[Node] [hierarchyid] NULL,\n\t[Spot] [geography] NULL,\n\t[Doc] [xml] NULL\n)"
    " ON [PRIMARY]",
)


def test_user_defined_types_resolve_and_built_ins_are_always_typed() -> None:
    result = import_ddl(TYPED, "tsql")
    assert result.status == "reconciled", result.report["failures"]
    types = {c.name: (c.data_type, c.source_data_type) for c in _entity(result, "Place").columns}
    assert types == {
        "PlaceID": ("UNIQUEIDENTIFIER", "[uniqueidentifier]"),
        "Name": ("NVARCHAR(50)", "[dbo].[Name]"),
        "Login": ("NVARCHAR(128)", "[sysname]"),
        "Node": ("HIERARCHYID", "[hierarchyid]"),
        "Spot": ("GEOGRAPHY", "[geography]"),
        "Doc": ("XML", "[xml]"),
    }
    assert "Place" not in result.report["held"]
    assert [t["alias"] for t in result.report["types"]] == ["Name"]


def test_negative_control_an_alias_with_no_create_type_is_held_unresolved() -> None:
    result = import_ddl(TYPED.split(b"GO\n", 1)[1], "tsql")
    held = result.report["held"]["Place"]["unresolved_types"]
    assert [(h["column"], h["type"]) for h in held] == [("Name", "[dbo].[Name]")]


def test_negative_control_without_the_built_in_map_sysname_is_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importer, "_BUILTIN_SPECIAL_TYPES", {})
    held = import_ddl(TYPED, "tsql").report["held"]["Place"]["unresolved_types"]
    assert {h["column"] for h in held} == {"Login", "Node"}


def test_adventureworks_has_no_unresolved_type() -> None:
    held = _import_aw().report["held"]
    assert [t for t, h in held.items() if "unresolved_types" in h] == []
    assert len(_import_aw().report["types"]) == 6


def test_the_markdown_report_names_nocheck_unresolved_and_computed_columns() -> None:
    nocheck = to_markdown(import_ddl(ALTERED, "tsql").report)
    assert "## Added WITH NOCHECK (1)" in nocheck
    assert "#5 ALTER TABLE [dbo].[Order] WITH NOCHECK ADD" in nocheck
    unresolved = to_markdown(import_ddl(TYPED.split(b"GO\n", 1)[1], "tsql").report)
    assert "**Place**, unresolved types: Name [dbo].[Name]" in unresolved
    computed = to_markdown(_import_aw().report)
    assert re.search(r"\*\*SalesOrderHeader\*\*, computed columns: SalesOrderNumber \S", computed)


# --- Shared -------------------------------------------------------------------------

_AW: list[ImportResult] = []


def _import_aw() -> ImportResult:
    if not _AW:
        _AW.append(import_ddl(AW.encode(), "tsql", "adventureworks.sql"))
    return _AW[0]


def _import_aw_manifest_counts() -> dict[str, int]:
    return json.loads((DDL / "tsql" / "adventureworks.manifest.json").read_text(encoding="utf-8"))["counts"]
