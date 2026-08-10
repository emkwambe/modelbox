"""Unit tests for the artifact ExporterService (pure, no DB/LLM)."""

from __future__ import annotations

import yaml

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SuggestedMetric,
    SynthesizedModel,
)
from app.services.exporter_service import ExporterError, ExporterService


def _col(
    name: str,
    dtype: str,
    *,
    pk: bool = False,
    fk: bool = False,
    metric: bool = False,
    agg: str | None = None,
    desc: str | None = None,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type=dtype,
        is_primary_key=pk,
        is_foreign_key=fk,
        is_metric=metric,
        aggregation=agg,
        description=desc,
    )


def _rel(from_ref: str, to_ref: str, cardinality: str = "1:N") -> RelationshipSchema:
    return RelationshipSchema.model_validate(
        {"from": from_ref, "to": to_ref, "cardinality": cardinality}
    )


def sample_model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="dim_customer",
                entity_type="DIMENSION",  # type: ignore[arg-type]
                description="Customer dimension.",
                columns=[
                    _col("customer_hk", "VARCHAR(64)", pk=True, desc="Surrogate key"),
                    _col("email", "VARCHAR(255)"),
                ],
            ),
            EntitySchema(
                entity_name="fact_orders",
                entity_type="FACT",  # type: ignore[arg-type]
                description="Order line facts.",
                columns=[
                    _col("order_id", "VARCHAR(32)", pk=True),
                    _col("customer_hk", "VARCHAR(64)", fk=True),
                    _col("total_amount", "NUMBER(18,2)", metric=True, agg="SUM"),
                ],
            ),
        ],
        relationships=[
            _rel("fact_orders.customer_hk", "dim_customer.customer_hk", "N:M")
        ],
        suggested_metrics=[
            SuggestedMetric(name="Revenue", formula="SUM(fact_orders.total_amount)")
        ],
    )


# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------
def test_generate_ddl_postgres() -> None:
    ddl = ExporterService().generate_ddl(sample_model(), "postgres")
    assert "CREATE TABLE dim_customer" in ddl
    assert "CREATE TABLE fact_orders" in ddl
    assert "PRIMARY KEY" in ddl
    assert "FOREIGN KEY" in ddl and "REFERENCES dim_customer" in ddl
    # NUMBER(18,2) transpiles to a Postgres numeric type.
    assert "DECIMAL" in ddl.upper() or "NUMERIC" in ddl.upper()


def test_generate_ddl_multi_dialect() -> None:
    exporter = ExporterService()
    model = sample_model()
    for dialect in ("snowflake", "databricks", "bigquery", "duckdb"):
        ddl = exporter.generate_ddl(model, dialect)
        assert "dim_customer" in ddl
        assert "fact_orders" in ddl


def test_generate_ddl_unknown_dialect_raises() -> None:
    try:
        ExporterService().generate_ddl(sample_model(), "oracle")
    except ExporterError as exc:
        assert "oracle" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ExporterError for unsupported dialect")


# ---------------------------------------------------------------------------
# dbt project
# ---------------------------------------------------------------------------
def test_generate_dbt_project() -> None:
    files = ExporterService().generate_dbt_project(sample_model())

    assert "models/staging/stg_dim_customer.sql" in files
    assert "models/staging/stg_fact_orders.sql" in files
    assert "models/staging/schema.yml" in files

    stg = files["models/staging/stg_fact_orders.sql"]
    assert "source('raw', 'fact_orders')" in stg
    assert "cast(total_amount as NUMBER(18,2)) as total_amount" in stg

    schema = yaml.safe_load(files["models/staging/schema.yml"])
    assert schema["version"] == 2
    model_names = {m["name"] for m in schema["models"]}
    assert model_names == {"stg_dim_customer", "stg_fact_orders"}

    # PK column carries unique + not_null tests.
    dim = next(m for m in schema["models"] if m["name"] == "stg_dim_customer")
    pk_col = next(c for c in dim["columns"] if c["name"] == "customer_hk")
    assert "unique" in pk_col["tests"] and "not_null" in pk_col["tests"]

    # FK column carries a relationships test to the parent staging model.
    fact = next(m for m in schema["models"] if m["name"] == "stg_fact_orders")
    fk_col = next(c for c in fact["columns"] if c["name"] == "customer_hk")
    rel_test = next(t for t in fk_col["tests"] if isinstance(t, dict))
    assert rel_test["relationships"]["to"] == "ref('stg_dim_customer')"
    assert rel_test["relationships"]["field"] == "customer_hk"


def test_dbt_accepted_values_for_categorical_columns() -> None:
    model = SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="orders",
                entity_type="TABLE",  # type: ignore[arg-type]
                columns=[
                    _col("id", "INT", pk=True),
                    _col("order_status", "VARCHAR(32)"),  # categorical -> accepted_values
                    _col("amount", "NUMERIC(12,2)"),  # numeric -> no accepted_values
                    _col("note", "VARCHAR(255)"),  # non-categorical string -> none
                ],
            )
        ],
    )
    schema = yaml.safe_load(
        ExporterService().generate_dbt_project(model)["models/staging/schema.yml"]
    )
    cols = {c["name"]: c for c in schema["models"][0]["columns"]}

    status_tests = cols["order_status"].get("tests", [])
    accepted = next(
        (t["accepted_values"] for t in status_tests if isinstance(t, dict) and "accepted_values" in t),
        None,
    )
    assert accepted == {"values": ["ACTIVE", "INACTIVE", "PENDING"]}

    # Numeric and free-text columns get no accepted_values test.
    for other in ("amount", "note"):
        tests = cols[other].get("tests", [])
        assert not any(
            isinstance(t, dict) and "accepted_values" in t for t in tests
        )


def test_metricflow_declared_measure_becomes_metric() -> None:
    # An explicitly declared measure (is_metric) is emitted as a measure + a
    # simple metric, even on a non-numeric column, using its aggregation.
    model = SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="fact_orders",
                entity_type="FACT",  # type: ignore[arg-type]
                grain="per order",
                columns=[
                    _col("order_id", "INTEGER", pk=True),
                    _col("rating", "VARCHAR(8)", metric=True, agg="avg"),  # declared
                    _col("amount", "NUMERIC(12,2)"),  # numeric heuristic
                ],
            )
        ],
    )
    doc = yaml.safe_load(
        ExporterService().export_semantic_layer(model, "metricflow")[
            "semantic_models.yml"
        ]
    )
    fo = doc["semantic_models"][0]
    measures = {m["name"]: m for m in fo["measures"]}
    assert "total_rating" in measures  # declared measure emitted despite VARCHAR
    assert measures["total_rating"]["agg"] == "avg"
    assert "total_amount" in measures
    metric_names = {m["name"] for m in doc["metrics"]}
    assert {"total_rating", "total_amount"} <= metric_names  # a metric per measure


# ---------------------------------------------------------------------------
# Cube.js
# ---------------------------------------------------------------------------
def test_generate_cube_schema() -> None:
    files = ExporterService().generate_cube_schema(sample_model())

    assert "schema/DimCustomer.js" in files
    assert "schema/FactOrders.js" in files

    fact = files["schema/FactOrders.js"]
    assert "cube(`FactOrders`" in fact
    assert "sql_table: `fact_orders`" in fact
    # Dimensions include the PK flagged as primaryKey.
    assert "primaryKey: true" in fact
    # Numeric metric becomes a measure.
    assert "totalTotalAmount" in fact
    assert "type: `sum`" in fact
    # Join to the referenced cube derived from the relationship.
    assert "DimCustomer:" in fact
    assert "relationship: `belongsTo`" in fact
