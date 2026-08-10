"""Tests for Snowflake introspection: pure type normalization + URI parsing.

The live connection path (driver + SHOW-key extraction) cannot run without a
real Snowflake account, so these tests cover the deterministic, driver-free core
that feeds IntrospectionService.build_graph.
"""

from __future__ import annotations

from app.services.introspection import (
    _SNOWFLAKE_TYPE_MAP,
    IntrospectionService,
)


def _cols(*specs: tuple[str, str, str, int]) -> list[dict]:
    return [
        {"table": t, "column": c, "data_type": dt, "ordinal": o}
        for (t, c, dt, o) in specs
    ]


def test_snowflake_type_normalization_into_build_graph() -> None:
    columns = _cols(
        ("orders", "id", "NUMBER", 1),
        ("orders", "amount", "NUMBER", 2),
        ("orders", "note", "TEXT", 3),
        ("orders", "created_at", "TIMESTAMP_NTZ", 4),
        ("orders", "updated_at", "TIMESTAMP_LTZ", 5),
        ("orders", "payload", "VARIANT", 6),
        ("orders", "is_paid", "BOOLEAN", 7),
        ("orders", "ratio", "FLOAT", 8),
    )
    model = IntrospectionService.build_graph(
        tables=["orders"],
        columns=columns,
        primary_keys={("orders", "id")},
        foreign_keys=[],
        type_map=_SNOWFLAKE_TYPE_MAP,
    )
    types = {c.name: c.data_type for c in model.entities[0].columns}
    assert types["id"] == "DECIMAL"  # NUMBER -> DECIMAL
    assert types["note"] == "VARCHAR"  # TEXT -> VARCHAR
    assert types["created_at"] == "TIMESTAMP"  # TIMESTAMP_NTZ -> TIMESTAMP
    assert types["updated_at"] == "TIMESTAMPTZ"  # TIMESTAMP_LTZ -> TIMESTAMPTZ
    assert types["payload"] == "VARIANT"
    assert types["is_paid"] == "BOOLEAN"
    assert types["ratio"] == "DOUBLE"  # FLOAT -> DOUBLE


def test_snowflake_unknown_type_falls_back_to_upper() -> None:
    model = IntrospectionService.build_graph(
        tables=["t"],
        columns=_cols(("t", "c", "some_future_type", 1)),
        primary_keys=set(),
        foreign_keys=[],
        type_map=_SNOWFLAKE_TYPE_MAP,
    )
    assert model.entities[0].columns[0].data_type == "SOME_FUTURE_TYPE"


def test_default_type_map_is_still_postgres() -> None:
    # Backward compatibility: omitting type_map keeps PostgreSQL normalization.
    model = IntrospectionService.build_graph(
        tables=["t"],
        columns=_cols(("t", "c", "character varying", 1)),
        primary_keys=set(),
        foreign_keys=[],
    )
    assert model.entities[0].columns[0].data_type == "VARCHAR"


def test_parse_snowflake_uri_full() -> None:
    params = IntrospectionService._parse_snowflake_uri(
        "snowflake://alice:s3cr3t@myacct-region/ANALYTICS/PUBLIC"
        "?warehouse=WH_XS&role=ANALYST"
    )
    assert params["user"] == "alice"
    assert params["password"] == "s3cr3t"
    assert params["account"] == "myacct-region"
    assert params["database"] == "ANALYTICS"
    assert params["schema"] == "PUBLIC"
    assert params["warehouse"] == "WH_XS"
    assert params["role"] == "ANALYST"


def test_parse_snowflake_uri_percent_encoded_password() -> None:
    params = IntrospectionService._parse_snowflake_uri(
        "snowflake://bob:p%40ss%2Fword@acct/DB"
    )
    assert params["password"] == "p@ss/word"
    assert params["database"] == "DB"
    assert "schema" not in params


def test_connect_kwargs_schema_name_is_authoritative() -> None:
    # Regression: the explicit schema_name must replace (not duplicate) the
    # schema parsed from the URI, so connect() never gets two 'schema' values.
    kwargs = IntrospectionService._snowflake_connect_kwargs(
        "snowflake://u:p@acct/DB/URI_SCHEMA?warehouse=WH", "ARG_SCHEMA"
    )
    assert kwargs["schema"] == "ARG_SCHEMA"
    assert kwargs["database"] == "DB"
    assert kwargs["warehouse"] == "WH"
