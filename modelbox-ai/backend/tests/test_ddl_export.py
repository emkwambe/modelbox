"""DDL export: composite keys, composite foreign keys, UNIQUE, CHECK and
descriptions, or a named export gap (Sprint 8 Step 3, item 6).

The emitted SQL is parsed back and asserted on its tree, not searched for
substrings.
"""

from __future__ import annotations

import json

import sqlglot
from sqlglot import exp

from app.schemas.data_model import GraphUpdateRequest, SynthesizedModel
from app.services import ddl_export
from app.services.exporter_service import ExporterService
from tests.test_keys_and_constraints import GRAPH


def _model(graph: dict | None = None) -> SynthesizedModel:
    parsed = GraphUpdateRequest.model_validate(json.loads(json.dumps(graph or GRAPH)))
    return SynthesizedModel(paradigm="3NF", entities=parsed.entities,  # type: ignore[arg-type]
                            relationships=parsed.relationships)


def _tables(sql: str, dialect: str = "postgres") -> dict[str, exp.Schema]:
    return {s.this.this.name: s.this for s in sqlglot.parse(sql, read=dialect)
            if isinstance(s, exp.Create) and isinstance(s.this, exp.Schema)}


def _names(node: exp.Expression) -> list[str]:
    return [c.name for c in node.expressions]


def test_postgres_states_every_key_constraint_and_description() -> None:
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(), "postgres")
    tables = _tables(export.sql)
    orders, line = tables["orders"], tables["order_line"]

    primary = next(node for node in orders.expressions if isinstance(node, exp.PrimaryKey))
    assert _names(primary) == ["order_id", "region"]
    unique = [c for c in orders.find_all(exp.Constraint) if c.name == "uq_orders_placed"]
    assert unique and _names(unique[0].find(exp.UniqueColumnConstraint).this) == ["placed_at", "region"]

    foreign = next(line.find_all(exp.ForeignKey))
    assert _names(foreign) == ["order_id", "region"]
    reference = foreign.args["reference"].this
    assert reference.this.name == "orders" and _names(reference) == ["order_id", "region"]

    checks = [c.this.sql("postgres") for c in line.find_all(exp.CheckColumnConstraint)]
    assert checks == ["qty > 0", "qty <= max_qty"]

    comments = [s for s in sqlglot.parse(export.sql, read="postgres") if isinstance(s, exp.Comment)]
    assert [(c.this.sql("postgres"), c.expression.name) for c in comments] == [("order_line.qty", "Units.")]


def test_an_unresolved_relationship_is_a_named_gap_not_a_foreign_key() -> None:
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(), "postgres")
    assert [(g.kind, g.entity) for g in export.gaps] == [("unresolved_relationship", "audit_note")]
    assert not list(_tables(export.sql)["audit_note"].find_all(exp.ForeignKey))
    assert export.sql.startswith("-- Export gaps (1)")


def test_what_a_dialect_cannot_express_is_a_named_gap() -> None:
    snowflake = ExporterService(source_dialect="postgres").generate_ddl_export(_model(), "snowflake")
    assert sorted(g.kind for g in snowflake.gaps) == [
        "check_constraint", "check_constraint", "check_constraint", "unresolved_relationship"]
    assert not list(_tables(snowflake.sql, "snowflake")["order_line"].find_all(exp.CheckColumnConstraint))
    bigquery = ExporterService(source_dialect="postgres").generate_ddl_export(_model(), "bigquery")
    assert {g.kind for g in bigquery.gaps} == {
        "unique_constraint", "check_constraint", "description", "unresolved_relationship"}


def test_a_check_that_is_not_one_expression_is_a_gap_and_never_emitted() -> None:
    graph = json.loads(json.dumps(GRAPH))
    graph["entities"][1]["check_constraints"] = [
        {"expression": "qty > 0); DROP TABLE orders; --", "columns": ["qty"]}]
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(graph), "postgres")
    # The gap header quotes the refused text, on comment lines; no statement carries it.
    statements = "\n".join(line for line in export.sql.splitlines() if not line.startswith("--"))
    assert "DROP" not in statements.upper()
    assert all(isinstance(s, exp.Create | exp.Comment) for s in sqlglot.parse(export.sql, read="postgres"))
    assert any(g.kind == "check_constraint" and "not a single" in g.detail for g in export.gaps)


def test_mixed_case_and_reserved_names_are_quoted() -> None:
    graph = {"entities": [{"entity_name": "Order", "columns": [
        {"name": "Group", "data_type": "INTEGER"}, {"name": "id", "data_type": "INTEGER"}],
        "primary_key": ["id"]}], "relationships": []}
    sql = ExporterService(source_dialect="postgres").generate_ddl(_model(graph), "postgres")
    table = _tables(sql)["Order"]
    assert table.this.this.args.get("quoted") is True
    assert [c.this.args.get("quoted") for c in table.expressions if isinstance(c, exp.ColumnDef)] == [True, False]


def test_a_check_names_its_columns_as_the_target_spells_them() -> None:
    """Oracle folds an unquoted name up, PostgreSQL down: an Oracle CHECK on
    `web_address` means "WEB_ADDRESS", and must say so in PostgreSQL."""
    written, problem = ddl_export.translate_check(
        "web_address IS NOT NULL", "oracle", "postgres", ["WEB_ADDRESS"])
    assert problem is None and written == 'NOT "WEB_ADDRESS" IS NULL'


def test_negative_control_without_the_entitys_columns_the_name_is_folded() -> None:
    written, _ = ddl_export.translate_check("web_address IS NOT NULL", "oracle", "postgres")
    assert written == "NOT web_address IS NULL"


def test_export_reads_the_normalized_default_never_the_source_text() -> None:
    """Item 5: comparisons and exports use the normalized form; the file's own
    spelling is provenance. Pagila's `now()` is CURRENT_TIMESTAMP either way."""
    graph = {"entities": [{"entity_name": "t", "columns": [
        {"name": "id", "data_type": "INT"},
        {"name": "at", "data_type": "TIMESTAMPTZ", "default_value": "CURRENT_TIMESTAMP",
         "source_default_value": "now()"}], "primary_key": ["id"]}], "relationships": []}
    sql = ExporterService(source_dialect="postgres").generate_ddl(_model(graph), "postgres")
    column = next(c for c in _tables(sql)["t"].expressions if isinstance(c, exp.ColumnDef) and c.name == "at")
    default = column.find(exp.DefaultColumnConstraint)
    assert default is not None and default.this.sql("postgres") == "CURRENT_TIMESTAMP"
    assert "now()" not in sql


_CYCLE = {"entities": [
    {"entity_name": "dept", "columns": [{"name": "dept_id", "data_type": "INTEGER"},
                                        {"name": "manager_id", "data_type": "INTEGER"}], "primary_key": ["dept_id"]},
    {"entity_name": "emp", "columns": [{"name": "emp_id", "data_type": "INTEGER"},
                                       {"name": "dept_id", "data_type": "INTEGER"}], "primary_key": ["emp_id"]}],
    "relationships": [
        {"from": "dept", "to": "emp", "from_columns": ["manager_id"], "to_columns": ["emp_id"], "cardinality": "N:1"},
        {"from": "emp", "to": "dept", "from_columns": ["dept_id"], "to_columns": ["dept_id"], "cardinality": "N:1"}]}


def test_a_foreign_key_cycle_is_closed_by_alter_table_after_every_table() -> None:
    """Step 4a: HR's DEPARTMENTS and EMPLOYEES reference each other, so no
    order creates both first; PostgreSQL refused the forward reference."""
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(_CYCLE), "postgres")
    trees = [sqlglot.parse_one(s, read="postgres") for s in export.statements]
    created = [t.this.this.name for t in trees if isinstance(t, exp.Create)]
    alters = [t for t in trees if isinstance(t, exp.Alter)]
    assert len(created) == 2 and len(alters) == 1 and trees.index(alters[0]) == 2
    first = created[0]
    assert not list(next(t for t in trees if isinstance(t, exp.Create) and t.this.this.name == first)
                    .find_all(exp.ForeignKey)), "the first table cannot name a table not yet created"
    assert alters[0].this.name == first and alters[0].find(exp.ForeignKey) is not None
    assert export.gaps == []


def test_negative_control_a_target_without_alter_names_the_cycle_as_a_gap() -> None:
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(_CYCLE), "duckdb")
    assert [g.kind for g in export.gaps] == ["foreign_key"] and "cycle" in export.gaps[0].detail
    assert not any(isinstance(sqlglot.parse_one(s, read="duckdb"), exp.Alter) for s in export.statements)


def _column(sql: str, table: str, name: str) -> exp.ColumnDef:
    return next(c for c in _tables(sql)[table].expressions if isinstance(c, exp.ColumnDef) and c.name == name)


def test_sql_server_money_smallmoney_and_bit_are_exact_mappings() -> None:
    """SYNTHESIS P1-A. money and smallmoney are exact in NUMERIC(19, 4) and
    NUMERIC(10, 4); bit is BOOLEAN with its 0 and 1 written FALSE and TRUE.
    Each is an exact equivalent, so none is a gap. PostgreSQL's acceptance is
    test_type_mappings_on_postgres."""
    graph = {"entities": [{"entity_name": "t", "columns": [
        {"name": "id", "data_type": "INT"},
        {"name": "rate", "data_type": "MONEY"},
        {"name": "fee", "data_type": "SMALLMONEY"},
        {"name": "flag", "data_type": "BIT", "default_value": "((1))"},
        {"name": "off", "data_type": "BIT", "default_value": "((0))"}], "primary_key": ["id"],
        "check_constraints": [{"expression": "([flag]=(1) OR [off]<>(0))", "columns": ["flag", "off"]}]}],
        "relationships": []}
    export = ExporterService(source_dialect="tsql").generate_ddl_export(_model(graph), "postgres")
    assert _column(export.sql, "t", "rate").args["kind"].sql("postgres") == "DECIMAL(19, 4)"
    assert _column(export.sql, "t", "fee").args["kind"].sql("postgres") == "DECIMAL(10, 4)"
    flag, off = _column(export.sql, "t", "flag"), _column(export.sql, "t", "off")
    assert flag.args["kind"].sql("postgres") == "BOOLEAN"
    assert flag.find(exp.DefaultColumnConstraint).this.sql("postgres") == "TRUE"
    assert off.find(exp.DefaultColumnConstraint).this.sql("postgres") == "FALSE"
    check = _tables(export.sql)["t"].find(exp.CheckColumnConstraint)
    assert check is not None and check.this.sql("postgres") == "(flag = TRUE OR off <> FALSE)"
    assert export.gaps == []


def test_a_bit_check_keeps_its_integers_on_a_column_that_is_not_bit() -> None:
    """Only a column now BOOLEAN has its 0 and 1 rewritten; the negative
    control is an INT column compared with the same literal."""
    graph = {"entities": [{"entity_name": "t", "columns": [
        {"name": "id", "data_type": "INT"}, {"name": "flag", "data_type": "BIT"},
        {"name": "n", "data_type": "INT"}], "primary_key": ["id"],
        "check_constraints": [{"expression": "([flag]=(1) AND [n]=(1))", "columns": ["flag", "n"]}]}],
        "relationships": []}
    export = ExporterService(source_dialect="tsql").generate_ddl_export(_model(graph), "postgres")
    check = _tables(export.sql)["t"].find(exp.CheckColumnConstraint)
    assert check is not None and check.this.sql("postgres") == "(flag = TRUE AND n = (1))"


def test_a_sequence_default_and_an_undefined_type_are_named_gaps() -> None:
    """Pagila: serial defaults call sequences the model does not hold, and
    columns use domains and enums it does not define."""
    graph = {"entities": [{"entity_name": "film", "columns": [
        {"name": "film_id", "data_type": "INTEGER",
         "default_value": "NEXTVAL(CAST('public.film_film_id_seq' AS REGCLASS))"},
        {"name": "rating", "data_type": "public.mpaa_rating",
         "default_value": "CAST('G' AS public.mpaa_rating)"}], "primary_key": ["film_id"]}],
        "relationships": []}
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(graph), "postgres")
    assert _column(export.sql, "film", "film_id").find(exp.DefaultColumnConstraint) is None
    rating = _column(export.sql, "film", "rating")
    assert rating.args["kind"].sql("postgres") == "TEXT"
    # The default keeps its value and loses the cast to the type the file does not create.
    assert rating.find(exp.DefaultColumnConstraint).this.sql("postgres") == "'G'"
    assert "mpaa_rating" not in "\n".join(export.statements)
    assert sorted(g.kind for g in export.gaps) == ["data_type", "default"]


def test_negative_control_an_unqualified_type_is_written_as_is() -> None:
    """tsvector is PostgreSQL's own; only a schema-qualified type is taken as
    one the file would have to create."""
    graph = {"entities": [{"entity_name": "film", "columns": [
        {"name": "film_id", "data_type": "INTEGER"}, {"name": "fulltext", "data_type": "tsvector"}],
        "primary_key": ["film_id"]}], "relationships": []}
    export = ExporterService(source_dialect="postgres").generate_ddl_export(_model(graph), "postgres")
    assert _column(export.sql, "film", "fulltext").args["kind"].sql("postgres").upper() == "TSVECTOR"
    assert export.gaps == []


def test_oracle_star_precision_is_written_as_38() -> None:
    graph = {"entities": [{"entity_name": "T", "columns": [{"name": "ID", "data_type": "NUMBER(*, 0)"}],
                           "primary_key": ["ID"]}], "relationships": []}
    sql = ExporterService(source_dialect="oracle").generate_ddl(_model(graph), "postgres")
    column = next(c for c in _tables(sql)["T"].expressions if isinstance(c, exp.ColumnDef))
    assert column.args["kind"].sql("postgres") == "DECIMAL(38, 0)"
