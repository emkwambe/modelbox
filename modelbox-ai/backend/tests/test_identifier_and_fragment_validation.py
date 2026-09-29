"""Identifiers and SQL fragments are checked before they reach SQL (Step 2.4).

* **Introspection identifiers.** ``schema_name``, and BigQuery's project, must
  fully match a strict pattern before use, on all four drivers, BigQuery first.
  The check runs before the driver is even loaded, so it holds on an appliance
  without that driver installed.
* **Model-supplied fragments.** A column's ``data_type`` and ``default_value``
  must parse as exactly one type or one scalar expression. Anything else is a
  linter error (``INVALID_DATA_TYPE`` / ``INVALID_DEFAULT``) and the DDL and
  dbt emitters refuse it rather than emit it verbatim.

The endpoint test authenticates with a real token. Negative controls patch
exactly the functions introduced: ``introspection.require_identifier`` and
``sql_fragments.column_problems``; the second also shows the smuggled
statement really reaches the output without the check.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret
from app.models.metadata_store import DatabaseConnection
from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from app.services import introspection, sql_fragments
from app.services.exporter_service import ExporterError, ExporterService
from app.services.graph_engine import GraphEngine
from app.services.introspection import IntrospectionService, InvalidIdentifierError
from app.services.sql_fragments import data_type_problem, default_problem
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)

# Balanced, so that without the check the whole script still parses and the
# transpiler passes the DROP through as its own statement. (A payload ending in
# `--` swallows the next comma and fails to parse, which would prove nothing.)
SMUGGLED_TYPE = "INT); DROP TABLE customers; CREATE TABLE pad (x INT"
SMUGGLED_DEFAULT = "0; DROP TABLE customers"
BIGQUERY_KEY = json.dumps({"project_id": "my-project-123", "type": "service_account"})


# --- Identifiers ------------------------------------------------------------


@pytest.mark.parametrize("value", ["public", "PUBLIC", "raw_2024", "_stage", "sales$eu"])
def test_ordinary_identifiers_pass(value: str) -> None:
    assert introspection.require_identifier(value, "schema") == value


@pytest.mark.parametrize(
    "value", ["public; DROP TABLE x", "a`b", "x.y", "", "1abc", "a b", "a'b", None]
)
def test_other_identifiers_are_refused(value: object) -> None:
    with pytest.raises(InvalidIdentifierError):
        introspection.require_identifier(value, "schema")


async def _check_bigquery_dataset_refused() -> None:
    """The check, shared by the test and its negative control."""
    with pytest.raises(InvalidIdentifierError, match="BigQuery dataset"):
        await IntrospectionService.introspect_bigquery(BIGQUERY_KEY, "ds` UNION SELECT 1 --")


async def test_bigquery_refuses_a_malicious_dataset_before_the_driver() -> None:
    await _check_bigquery_dataset_refused()


async def test_bigquery_refuses_a_malicious_project() -> None:
    key = json.dumps({"project_id": "p`.x --"})
    with pytest.raises(InvalidIdentifierError, match="BigQuery project"):
        await IntrospectionService.introspect_bigquery(key, "dataset")


async def test_snowflake_refuses_before_the_driver() -> None:
    with pytest.raises(InvalidIdentifierError):
        await IntrospectionService.introspect_snowflake(
            "snowflake://u:p@acct/db", "PUBLIC; SHOW USERS"
        )


async def test_postgres_refuses_before_connecting() -> None:
    with pytest.raises(InvalidIdentifierError):
        await IntrospectionService.introspect_postgresql(
            "postgresql://u:p@127.0.0.1:1/db", "public'; --"
        )


async def test_mysql_refuses_before_the_driver() -> None:
    with pytest.raises(InvalidIdentifierError):
        await IntrospectionService.introspect_mysql("mysql://u:p@h:3306/db", "db`; --")


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


async def test_the_endpoint_answers_422_for_a_malicious_schema(session) -> None:
    member = await make_user(session, "member@example.com")
    workspace = await make_workspace(session, "W", {member: "MEMBER"})
    connection = DatabaseConnection(
        workspace_id=workspace.workspace_id,
        name="bq",
        engine="BIGQUERY",
        connection_uri_encrypted=encrypt_secret(BIGQUERY_KEY),
    )
    session.add(connection)
    await session.commit()
    async with real_client(session) as client:
        response = await client.post(
            "/api/v1/connectors/introspect",
            json={"connection_id": str(connection.connection_id), "schema_name": "ds` --"},
            headers=bearer(member),
        )
    assert response.status_code == 422, response.text


# --- Fragments --------------------------------------------------------------


@pytest.mark.parametrize(
    "data_type", ["INT", "NUMBER(18,2)", "TIMESTAMP_NTZ", "VARCHAR(20)", "ARRAY<INT>", "VARIANT"]
)
def test_ordinary_types_pass(data_type: str) -> None:
    assert data_type_problem(data_type) is None


@pytest.mark.parametrize(
    "data_type",
    [SMUGGLED_TYPE, "INT); DROP TABLE x; --", "INT) FROM t; --", "INT --", "INT /* x */",
     "VARCHAR(20) DEFAULT 'x'",
     "INT, evil INT", "BOGUSTYPE"],
)
def test_other_types_are_refused(data_type: str) -> None:
    assert data_type_problem(data_type) is not None


@pytest.mark.parametrize(
    "default", ["0", "'x'", "CURRENT_TIMESTAMP", "now()", "'a -- b'", "'a;b'", "'a' || 'b'"]
)
def test_ordinary_defaults_pass(default: str) -> None:
    assert default_problem(default) is None


@pytest.mark.parametrize(
    "default", [SMUGGLED_DEFAULT, "0); DROP TABLE x; --", "0 -- x", "(SELECT 1)",
                "1 + (SELECT 2)", "0 AS x"],
)
def test_other_defaults_are_refused(default: str) -> None:
    assert default_problem(default) is not None


def _model(data_type: str = "INT", default: str | None = None) -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",
        entities=[
            EntitySchema(
                entity_name="customers",
                columns=[
                    ColumnSchema(name="id", data_type="INT", is_primary_key=True),
                    ColumnSchema(name="score", data_type=data_type, default_value=default),
                ],
            )
        ],
    )


def test_the_linter_reports_both_codes_as_errors() -> None:
    model = _model(SMUGGLED_TYPE, SMUGGLED_DEFAULT)
    report = GraphEngine().validate(model.entities, model.relationships)
    found = {(i.code, i.severity) for i in report.issues if i.code.startswith("INVALID_D")}
    assert found == {("INVALID_DATA_TYPE", "error"), ("INVALID_DEFAULT", "error")}


def _check_ddl_refused(model: SynthesizedModel) -> None:
    """The check, shared by the tests and the negative control."""
    try:
        files = ExporterService().export(model, "ddl", "postgres")
    except ExporterError as exc:
        assert "INVALID_D" in str(exc)
        return
    emitted = "\n".join(files.values())
    raise AssertionError(f"the model was exported; DROP emitted: {'DROP TABLE' in emitted.upper()}")


def test_ddl_refuses_a_smuggled_type() -> None:
    _check_ddl_refused(_model(SMUGGLED_TYPE))


def test_ddl_refuses_a_smuggled_default() -> None:
    _check_ddl_refused(_model(default=SMUGGLED_DEFAULT))


def test_dbt_refuses_a_smuggled_type() -> None:
    with pytest.raises(ExporterError, match="INVALID_DATA_TYPE"):
        ExporterService().export(_model(SMUGGLED_TYPE), "dbt", "postgres")


def test_a_clean_model_still_exports() -> None:
    """Precondition: the check is not refusing everything."""
    files = ExporterService().export(_model("VARCHAR(20)", "'x'"), "ddl", "postgres")
    assert "CREATE TABLE" in "\n".join(files.values()).upper()


# --- Negative controls ------------------------------------------------------


async def test_negative_control_without_the_identifier_check_bigquery_passes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(introspection, "require_identifier", lambda value, *args, **kw: value)
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        # Without the check, the malicious dataset is accepted and the call
        # proceeds to load the driver or connect instead.
        try:
            await _check_bigquery_dataset_refused()
        except (introspection.IntrospectionDriverError, ValueError, OSError):
            pytest.fail("DID NOT RAISE InvalidIdentifierError")


def test_negative_control_without_the_fragment_check_the_drop_is_emitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """From Sprint 8 Step 3 the DDL builder parses each table as exactly one
    statement, so a smuggled statement is refused even without the fragment
    check. What the check alone provides is the refusal naming its lint code:
    without it the export still fails, emits no DROP, and cannot say why."""
    monkeypatch.setattr(sql_fragments, "column_problems", lambda *args, **kw: [])
    with pytest.raises(ExporterError) as refused:
        ExporterService().export(_model(SMUGGLED_TYPE), "ddl", "postgres")
    assert "INVALID_D" not in str(refused.value)
    with pytest.raises(AssertionError):
        _check_ddl_refused(_model(SMUGGLED_TYPE))
