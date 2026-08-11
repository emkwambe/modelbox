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
    min_value: float | None = None,
    max_value: float | None = None,
    regex_pattern: str | None = None,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type=dtype,
        is_primary_key=pk,
        is_foreign_key=fk,
        is_metric=metric,
        aggregation=agg,
        description=desc,
        min_value=min_value,
        max_value=max_value,
        regex_pattern=regex_pattern,
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
    # dbt 1.8+ renamed `tests:` to `data_tests:`.
    assert "unique" in pk_col["data_tests"]
    assert "not_null" in pk_col["data_tests"]

    # FK column carries a relationships test to the parent staging model.
    fact = next(m for m in schema["models"] if m["name"] == "stg_fact_orders")
    fk_col = next(c for c in fact["columns"] if c["name"] == "customer_hk")
    rel_test = next(t for t in fk_col["data_tests"] if isinstance(t, dict))
    # Generic-test arguments nest under `arguments:` in dbt 1.11.
    args = rel_test["relationships"]["arguments"]
    assert args["to"] == "ref('stg_dim_customer')"
    assert args["field"] == "customer_hk"


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

    status_tests = cols["order_status"].get("data_tests", [])
    accepted = next(
        (t["accepted_values"] for t in status_tests if isinstance(t, dict) and "accepted_values" in t),
        None,
    )
    assert accepted == {"arguments": {"values": ["ACTIVE", "INACTIVE", "PENDING"]}}

    # Numeric and free-text columns get no accepted_values test.
    for other in ("amount", "note"):
        tests = cols[other].get("data_tests", [])
        assert not any(
            isinstance(t, dict) and "accepted_values" in t for t in tests
        )


def test_governance_metadata_propagates_to_exports() -> None:
    model = SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="fact_orders",
                entity_type="FACT",  # type: ignore[arg-type]
                grain="per order",
                description="Orders.",
                tier="TIER_1_CRITICAL",  # type: ignore[arg-type]
                freshness_sla="< 1h",
                columns=[_col("id", "INT", pk=True, desc="pk")],
            )
        ],
    )
    # OpenDataContract: tier + slaProperties.
    odcs = yaml.safe_load(
        ExporterService().export_data_contract(model, "opendatacontract", "sales")[
            "datacontract.yaml"
        ]
    )
    table = odcs["schema"][0]
    # `tier` is not an ODCS v3.1.0 schema key, so it travels as a custom
    # property rather than as invented vocabulary. slaProperties is standard.
    assert {"property": "tier", "value": "TIER_1_CRITICAL"} in table[
        "customProperties"
    ]
    assert table["slaProperties"] == [{"property": "freshness", "value": "< 1h"}]

    # dbt schema.yml: meta block.
    dbt = yaml.safe_load(
        ExporterService().generate_dbt_project(model)["models/staging/schema.yml"]
    )
    meta = dbt["models"][0]["meta"]
    assert meta["tier"] == "TIER_1_CRITICAL"
    assert meta["freshness_sla"] == "< 1h"


def test_quality_rules_propagate_to_exports() -> None:
    model = SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="fact_orders",
                entity_type="FACT",  # type: ignore[arg-type]
                grain="per order",
                description="Orders.",
                columns=[
                    _col("id", "INT", pk=True, desc="pk"),
                    _col("score", "INT", min_value=0, max_value=100),
                    _col("email", "VARCHAR(320)", regex_pattern=r"^[^@]+@[^@]+$"),
                ],
            )
        ],
    )
    # dbt: range -> expect_column_values_to_be_between; regex -> match_regex.
    dbt = yaml.safe_load(
        ExporterService().generate_dbt_project(model)["models/staging/schema.yml"]
    )
    cols = {c["name"]: c for c in dbt["models"][0]["columns"]}
    score_tests = cols["score"]["data_tests"]
    between = next(
        t["dbt_expectations.expect_column_values_to_be_between"]
        for t in score_tests
        if isinstance(t, dict)
        and "dbt_expectations.expect_column_values_to_be_between" in t
    )
    assert between == {"min_value": 0, "max_value": 100}
    email_tests = cols["email"]["data_tests"]
    regex = next(
        t["dbt_expectations.expect_column_values_to_match_regex"]
        for t in email_tests
        if isinstance(t, dict)
        and "dbt_expectations.expect_column_values_to_match_regex" in t
    )
    assert regex == {"regex": r"^[^@]+@[^@]+$"}

    # ODCS: column-level quality assertions.
    odcs = yaml.safe_load(
        ExporterService().export_data_contract(model, "opendatacontract", "sales")[
            "datacontract.yaml"
        ]
    )
    props = {p["name"]: p for p in odcs["schema"][0]["properties"]}
    assert props["score"]["quality"] == [
        {"rule": "range", "mustBeGreaterThanOrEqualTo": 0, "mustBeLessThanOrEqualTo": 100}
    ]
    assert props["email"]["quality"] == [
        {"rule": "regex", "pattern": r"^[^@]+@[^@]+$"}
    ]


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
                # A measure needs a time axis: MetricFlow requires
                # defaults.agg_time_dimension on any semantic model declaring
                # measures, so an entity without one is dimension-only.
                agg_time_column="ordered_at",
                columns=[
                    _col("order_id", "INTEGER", pk=True),
                    _col("ordered_at", "TIMESTAMP"),
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
    # 'avg' is not a MetricFlow AggregationType; it is mapped to 'average'.
    assert measures["total_rating"]["agg"] == "average"
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
