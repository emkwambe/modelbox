"""Tests for synthetic seed generation + endpoint (FR-2.4).

Pure-unit coverage of SyntheticSeedGenerator (referential integrity, ordering,
determinism, formats) plus one ASGI integration test over an in-memory session.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models.metadata_store import Base, User, Workspace, WorkspaceMember
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
    SynthesizeRequest,
)
from app.services.seed_generator import SyntheticSeedGenerator
from app.services.synthesis_engine import SynthesisEngine
from tests._test_db import make_test_engine


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _col(name: str, dtype: str = "VARCHAR(64)", *, pk: bool = False, fk: bool = False) -> ColumnSchema:
    return ColumnSchema(
        name=name, data_type=dtype, is_primary_key=pk, is_foreign_key=fk
    )


def _entity(name: str, cols: list[ColumnSchema], etype: str = "TABLE") -> EntitySchema:
    return EntitySchema(entity_name=name, entity_type=etype, columns=cols)  # type: ignore[arg-type]


def _rel(from_ref: str, to_ref: str, cardinality: str = "N:1") -> RelationshipSchema:
    return RelationshipSchema.model_validate(
        {"from": from_ref, "to": to_ref, "cardinality": cardinality}
    )


def _ecommerce() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity(
                "customers",
                [
                    _col("id", "INTEGER", pk=True),
                    _col("email", "VARCHAR(255)"),
                    _col("full_name", "VARCHAR(255)"),
                ],
            ),
            _entity(
                "orders",
                [
                    _col("id", "INTEGER", pk=True),
                    _col("customer_id", "INTEGER", fk=True),
                    _col("total", "NUMERIC(12,2)"),
                ],
            ),
        ],
        relationships=[_rel("orders.customer_id", "customers.id")],
    )


def _cyclic() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity("a", [_col("id", "INTEGER", pk=True), _col("b_id", "INTEGER", fk=True)]),
            _entity("b", [_col("id", "INTEGER", pk=True), _col("a_id", "INTEGER", fk=True)]),
        ],
        relationships=[_rel("a.b_id", "b.id"), _rel("b.a_id", "a.id")],
    )


def _rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))


# ---------------------------------------------------------------------------
# Unit: SyntheticSeedGenerator
# ---------------------------------------------------------------------------
def test_generation_order_puts_parents_first() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 5, "csv")
    assert result.generation_order.index("customers") < result.generation_order.index("orders")


def test_row_count_per_entity() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 7, "csv")
    assert len(_rows(result.files["customers.csv"])) == 7
    assert len(_rows(result.files["orders.csv"])) == 7


def test_foreign_keys_reference_real_parent_rows() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 20, "csv")
    customer_ids = {r["id"] for r in _rows(result.files["customers.csv"])}
    order_fks = {r["customer_id"] for r in _rows(result.files["orders.csv"])}
    # Every child FK must point at an existing parent PK.
    assert order_fks
    assert order_fks <= customer_ids


def test_output_is_deterministic() -> None:
    a = SyntheticSeedGenerator().generate(_ecommerce(), 10, "sql_insert")
    b = SyntheticSeedGenerator().generate(_ecommerce(), 10, "sql_insert")
    assert a.files == b.files


def test_sql_insert_format() -> None:
    result = SyntheticSeedGenerator(dialect="postgres").generate(_ecommerce(), 3, "sql_insert")
    script = result.files["seed_postgres.sql"]
    assert "INSERT INTO customers (id, email, full_name) VALUES" in script
    assert "INSERT INTO orders (id, customer_id, total) VALUES" in script
    # customers must be inserted before orders (FK-safe order).
    assert script.index("INSERT INTO customers") < script.index("INSERT INTO orders")
    assert script.rstrip().endswith(";")


def test_email_heuristic_produces_addresses() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 5, "csv")
    for row in _rows(result.files["customers.csv"]):
        assert "@" in row["email"]


def test_pk_surrogates_are_unique_and_sequential() -> None:
    result = SyntheticSeedGenerator().generate(_ecommerce(), 6, "csv")
    ids = [int(r["id"]) for r in _rows(result.files["customers.csv"])]
    assert ids == [1, 2, 3, 4, 5, 6]


def test_cyclic_model_does_not_crash() -> None:
    # Falls back to declared order rather than raising on the FK cycle.
    result = SyntheticSeedGenerator().generate(_cyclic(), 3, "sql_insert")
    assert set(result.generation_order) == {"a", "b"}
    assert "INSERT INTO a" in result.files["seed_postgres.sql"]


def test_string_literals_are_escaped() -> None:
    model = SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[_entity("t", [_col("id", "INTEGER", pk=True), _col("label", "VARCHAR(64)")])],
    )
    script = SyntheticSeedGenerator().generate(model, 2, "sql_insert").files["seed_postgres.sql"]
    # No unescaped lone quotes would appear; labels are quoted string literals.
    assert "'label_1'" in script


# ---------------------------------------------------------------------------
# Unit: declared constraints (Sprint 9 Step 2b)
#
# Each case is one where the generator before Step 2b produced rows the
# database refuses, so each assertion distinguishes the two. The rows are
# checked by the CHECK itself, evaluated here in Python from the rows read back.
# ---------------------------------------------------------------------------
def _checked(name: str, cols: list[ColumnSchema], *checks: str, pk: list[str] | None = None,
             unique: list[list[str]] | None = None) -> EntitySchema:
    return EntitySchema.model_validate({
        "entity_name": name,
        # The flags derived from the lists below are left for the IR to derive.
        "columns": [c.model_dump(exclude={"is_primary_key", "is_unique", "check_expression"}) for c in cols],
        "primary_key": pk if pk is not None else [c.name for c in cols if c.is_primary_key],
        "unique_constraints": [{"columns": u} for u in (unique or [])],
        "check_constraints": [{"expression": c} for c in checks]})


def _model(*entities: EntitySchema, relationships: list[RelationshipSchema] | None = None) -> SynthesizedModel:
    return SynthesizedModel(paradigm="3NF", entities=list(entities),  # type: ignore[arg-type]
                            relationships=relationships or [])


def _csv(model: SynthesizedModel, rows: int, **kwargs: Any) -> dict[str, list[dict[str, str]]]:
    result = SyntheticSeedGenerator(**kwargs).generate(model, rows, "csv")
    return {name.removesuffix(".csv"): _rows(body) for name, body in result.files.items()}


def test_check_bounds_are_honoured() -> None:
    low, high = 6.5, 200.0
    model = _model(_checked("pay", [_col("id", "INTEGER", pk=True), _col("rate", "NUMERIC(8,2)"),
                                    _col("salary", "NUMERIC(8,2)")],
                            f"rate >= {low} AND rate <= {high}", "salary > 0"))
    rows = _csv(model, 30)["pay"]
    assert len(rows) == 30
    assert all(low <= float(r["rate"]) <= high and float(r["salary"]) > 0 for r in rows)


def test_check_ordering_between_two_columns_is_honoured() -> None:
    model = _model(_checked("job_history", [_col("id", "INTEGER", pk=True), _col("start_date", "DATE"),
                                            _col("end_date", "DATE")], "end_date > start_date"))
    rows = _csv(model, 30)["job_history"]
    assert len(rows) == 30 and all(r["end_date"] > r["start_date"] for r in rows)


def test_check_value_lists_under_upper_are_honoured() -> None:
    allowed = ["M", "F"]
    model = _model(_checked("person", [_col("id", "INTEGER", pk=True), _col("gender", "CHAR(1)")],
                            " OR ".join(f"UPPER(gender) = '{v}'" for v in allowed)))
    rows = _csv(model, 20)["person"]
    assert {r["gender"].upper() for r in rows} <= set(allowed)


def test_equality_is_preferred_to_a_dialect_specific_like_pattern() -> None:
    # T-SQL's [A-Za-z] is a character class; in PostgreSQL it is literal text.
    model = _model(_checked("bin", [_col("id", "INTEGER", pk=True), _col("shelf", "VARCHAR(10)")],
                            "shelf LIKE '[A-Za-z]' OR shelf = 'N/A'"))
    rows = _csv(model, 5, source_dialect="tsql")["bin"]
    assert {r["shelf"] for r in rows} == {"N/A"}


def test_is_json_check_is_honoured() -> None:
    model = _model(_checked("product", [_col("id", "NUMBER", pk=True), _col("details", "BLOB")],
                            "details IS JSON"))
    for row in _csv(model, 5, source_dialect="oracle")["product"]:
        json.loads(row["details"])


def test_an_unsatisfiable_check_leaves_rows_out_and_says_so() -> None:
    # NOT NULL: a NULL would make the CHECK unknown, which SQL accepts.
    model = _model(_checked("t", [_col("id", "INTEGER", pk=True),
                                  ColumnSchema(name="x", data_type="INTEGER", is_nullable=False)],
                            "x > 10 AND x < 5"))
    result = SyntheticSeedGenerator().generate(model, 4, "csv")
    assert _rows(result.files["t.csv"]) == []
    assert result.rows_skipped == {"t": 4}


def test_a_check_between_foreign_keys_is_evaluated() -> None:
    # Read by no value list or bound: only the evaluator can enforce it.
    parent = _entity("part", [_col("id", "INTEGER", pk=True)])
    bom = _entity("bom", [_col("id", "INTEGER", pk=True), _col("assembly_id", "INTEGER", fk=True),
                          _col("component_id", "INTEGER", fk=True)])
    bom = _checked("bom", bom.columns, "assembly_id <> component_id")
    model = _model(parent, bom, relationships=[_rel("bom.assembly_id", "part.id"),
                                               _rel("bom.component_id", "part.id")])
    rows = _csv(model, 30)["bom"]
    assert len(rows) == 30 and all(r["assembly_id"] != r["component_id"] for r in rows)


def test_composite_keys_of_foreign_keys_are_distinct() -> None:
    actor = _entity("actor", [_col("id", "INTEGER", pk=True)])
    film = _entity("film", [_col("id", "INTEGER", pk=True)])
    link = _checked("film_actor", [_col("actor_id", "INTEGER", fk=True), _col("film_id", "INTEGER", fk=True)],
                    pk=["actor_id", "film_id"])
    model = _model(actor, film, link, relationships=[_rel("film_actor.actor_id", "actor.id"),
                                                     _rel("film_actor.film_id", "film.id")])
    tables = _csv(model, 15)
    pairs = [(r["actor_id"], r["film_id"]) for r in tables["film_actor"]]
    assert len(pairs) == 15 and len(set(pairs)) == len(pairs)
    assert {a for a, _ in pairs} <= {r["id"] for r in tables["actor"]}
    assert {f for _, f in pairs} <= {r["id"] for r in tables["film"]}


def test_unique_constraints_are_distinct() -> None:
    model = _model(_checked("country", [_col("id", "INTEGER", pk=True), _col("code", "CHAR(2)")],
                            unique=[["code"]]))
    codes = [r["code"] for r in _csv(model, 40)["country"]]
    assert len(codes) == 40 and len(set(codes)) == 40


def test_a_self_reference_repeats_an_earlier_row() -> None:
    employees = _entity("employees", [_col("id", "INTEGER", pk=True), _col("manager_id", "INTEGER", fk=True)])
    model = _model(employees, relationships=[_rel("employees.manager_id", "employees.id")])
    rows = _csv(model, 10)["employees"]
    seen: set[str] = set()
    for row in rows:
        assert row["manager_id"] == "" or row["manager_id"] in seen
        seen.add(row["id"])
    assert rows[0]["manager_id"] == ""  # the first row has nobody to reference


def test_a_nullable_foreign_key_breaks_a_cycle() -> None:
    departments = _entity("departments", [_col("id", "INTEGER", pk=True), _col("manager_id", "INTEGER", fk=True)])
    employees = _entity("employees", [_col("id", "INTEGER", pk=True),
                                      ColumnSchema(name="department_id", data_type="INTEGER", is_foreign_key=True,
                                                   is_nullable=False)])
    model = _model(departments, employees, relationships=[_rel("departments.manager_id", "employees.id"),
                                                         _rel("employees.department_id", "departments.id")])
    result = SyntheticSeedGenerator().generate(model, 5, "csv")
    # The NOT NULL key decides the order; the nullable one waits as NULL.
    assert result.generation_order == ["departments", "employees"]
    assert {r["manager_id"] for r in _rows(result.files["departments.csv"])} == {""}
    ids = {r["id"] for r in _rows(result.files["departments.csv"])}
    assert {r["department_id"] for r in _rows(result.files["employees.csv"])} <= ids


def test_mixed_case_names_are_quoted() -> None:
    model = _model(_entity("Customer", [_col("CustomerID", "INTEGER", pk=True), _col("name", "VARCHAR(20)")]))
    script = SyntheticSeedGenerator().generate(model, 2, "sql_insert").files["seed_postgres.sql"]
    assert 'INSERT INTO "Customer" ("CustomerID", name) VALUES' in script


def test_values_are_generated_for_the_target_type() -> None:
    cols = [_col("id", "UNIQUEIDENTIFIER", pk=True), _col("active", "BIT"), _col("at", "TIME"),
            ColumnSchema(name="total", data_type="COMPUTED", computed_expression="1")]
    model = _model(_entity("t", cols))
    script = SyntheticSeedGenerator(source_dialect="tsql").generate(model, 3, "sql_insert").files[
        "seed_postgres.sql"]
    assert 'INSERT INTO t (id, active, at) VALUES' in script  # the computed column is not written
    values = re.findall(r"\('([0-9a-f-]{36})', (TRUE|FALSE), '(\d\d:\d\d:\d\d)'\)", script)
    assert len(values) == 3
    # Control: without a source dialect the declared T-SQL types are used as they are.
    declared = SyntheticSeedGenerator().generate(model, 3, "sql_insert").files["seed_postgres.sql"]
    assert "TRUE" not in declared and "FALSE" not in declared


# ---------------------------------------------------------------------------
# Integration: POST /api/v1/model/{id}/export/synthetic-data
# ---------------------------------------------------------------------------
class _StubGateway:
    def __init__(self, model: SynthesizedModel) -> None:
        self._model = model

    async def structured_completion(
        self, task: str, prompt: str, response_model: type[Any], **_: Any
    ) -> SynthesizedModel:
        return self._model


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def test_synthetic_data_endpoint_returns_seed(session: AsyncSession) -> None:
    from app.api.v1.dependencies import get_current_user, get_synthesis_engine
    from app.core.database import get_db_session
    from app.main import create_app

    user = User(email="owner@example.com", hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()
    workspace = Workspace(name="ws")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id, user_id=user.user_id, role="OWNER"
        )
    )
    await session.flush()

    resp = await SynthesisEngine(session, _StubGateway(_ecommerce())).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="ecommerce",
            target_paradigm="3NF",  # type: ignore[arg-type]
            dialect="postgres",
            workspace_id=workspace.workspace_id,
        )
    )
    model_id = str(resp.model_id)

    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_synthesis_engine] = lambda: SynthesisEngine(
        session, _StubGateway(_ecommerce())
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/model/{model_id}/export/synthetic-data",
            json={"row_count_per_entity": 8, "format": "sql_insert", "dialect": "postgres"},
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generation_order"].index("customers") < body["generation_order"].index("orders")
    assert body["rows_skipped"] == {}
    script = body["files"]["seed_postgres.sql"]
    assert "INSERT INTO customers" in script
    assert "INSERT INTO orders" in script
