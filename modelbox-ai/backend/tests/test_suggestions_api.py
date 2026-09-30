"""Suggestions over HTTP, with real credentials (Sprint 9 Step 4).

The Oracle HR and SQL Server AdventureWorks exports are imported through the
product's own route, and everything asserted about what is stored is read
back by raw SQL, never through the ORM.

* **Running the rules changes nothing.** Suggestions are stored ``pending``
  with provenance ``heuristic``, and the model, its version and every export
  are exactly as they were.
* **A suggestion never reaches "verified" without an approver.** A member
  accepts; the value is written as the member's and its field is pending. The
  member's verify request is refused. Only an approver's request can verify
  the field, and only when Step 4b's three conditions hold; the suggestion
  itself stays ``accepted``. Negative controls: no credentials, a viewer, an
  API key, and a body naming a status or a decider are each refused and leave
  the suggestion pending; the database refuses a ``verified`` suggestion and
  any provenance but ``heuristic``.
* **An AdventureWorks entity gets MetricFlow measures only after a person
  confirms its time column.** Before, and with the suggestion pending (the
  control), SalesOrderHeader declares none.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import yaml
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)
from tests.test_ddl_round_trip import DDL


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    member = await make_user(session, "member@example.com")
    viewer = await make_user(session, "viewer@example.com")
    approver = await make_user(session, "approver@example.com")
    admin = await make_user(session, "admin@example.com")
    workspace = await make_workspace(session, "W", {member: "MEMBER", viewer: "VIEWER", approver: "APPROVER",
                                                    admin: "ADMIN"})
    await session.commit()
    return {"member": member, "viewer": viewer, "approver": approver, "admin": admin, "ws": workspace}


async def _ok(response: Any, *codes: int) -> Any:
    assert response.status_code in codes, f"{response.request.url}: {response.status_code} {response.text[:500]}"
    return response.json() if response.content else None


async def _import(c: AsyncClient, w: dict[str, Any], path: str, dialect: str) -> str:
    body = await _ok(await c.post(
        "/api/v1/import/ddl", params={"workspace_id": str(w["ws"].workspace_id)},
        files={"file": (path.rsplit("/", 1)[-1], (DDL / path).read_bytes(), "application/sql")},
        data={"dialect": dialect}, headers=bearer(w["member"])), 201)
    return body["model_id"]


async def _run(c: AsyncClient, w: dict[str, Any], model: str) -> dict[str, Any]:
    return await _ok(await c.post(f"/api/v1/model/{model}/suggestions", headers=bearer(w["member"])), 200)


def _one(body: dict[str, Any], entity: str, column: str, category: str) -> dict[str, Any]:
    found = [s for s in body["suggestions"] if (s["entity"], s["column"], s["category"]) == (entity, column, category)]
    assert len(found) == 1, f"expected one {category} suggestion on {entity}.{column}: {found}"
    return found[0]


async def _rows(session: AsyncSession, sql: str, **params: object) -> list[dict[str, Any]]:
    """Raw SQL on the session the app writes through: it bypasses the identity
    map, so nothing is expired (expiring would unload the test's users)."""
    return [dict(r._mapping) for r in (await session.execute(text(sql), params)).all()]


async def _suggestion(session: AsyncSession, suggestion_id: str) -> dict[str, Any]:
    rows = await _rows(session, "SELECT status, provenance, decided_by_email, decided_at FROM model_suggestions "
                                "WHERE suggestion_id = :s", s=suggestion_id.replace("-", ""))
    if not rows:  # a UUID column may hold its hyphenated text, by dialect
        rows = await _rows(session, "SELECT status, provenance, decided_by_email, decided_at FROM model_suggestions "
                                    "WHERE suggestion_id = :s", s=suggestion_id)
    assert len(rows) == 1, f"fixture sanity: suggestion {suggestion_id} is stored once"
    return rows[0]


async def _column(session: AsyncSession, model: str, entity: str, column: str) -> dict[str, Any]:
    rows = await _rows(session, "SELECT c.column_id, c.is_pii, c.pii_type FROM entity_columns c "
                                "JOIN model_entities e ON e.entity_id = c.entity_id "
                                "WHERE e.entity_name = :e AND c.column_name = :c", e=entity, c=column)
    assert len(rows) == 1, f"fixture sanity: one {entity}.{column}"
    return rows[0]


async def _pii_attestation(session: AsyncSession, column_id: Any) -> dict[str, Any]:
    rows = await _rows(session, "SELECT status, provenance, provenance_by, verified_by FROM field_attestations "
                                "WHERE column_id = :c AND field_key = 'pii'", c=column_id)
    assert len(rows) == 1, "the accepted value has one attestation row"
    return rows[0]


# --- running the rules changes nothing ----------------------------------------------


async def _exports(c: AsyncClient, w: dict[str, Any], model: str) -> dict[str, Any]:
    h = bearer(w["member"])
    out: dict[str, Any] = {}
    for fmt, dialect in (("ddl", "postgres"), ("ddl", "snowflake"), ("dbt", "postgres"), ("cube", "postgres")):
        out[f"{fmt}/{dialect}"] = (await _ok(await c.get(f"/api/v1/model/{model}/export", headers=h,
                                                         params={"format": fmt, "dialect": dialect}), 200))["files"]
    for engine in ("cube", "lookml", "metricflow"):
        out[f"semantic/{engine}"] = (await _ok(await c.get(f"/api/v1/model/{model}/export/semantic", headers=h,
                                                           params={"engine": engine}), 200))["files"]
    out["contract"] = (await _ok(await c.get(f"/api/v1/model/{model}/export/contract", headers=h), 200))["files"]
    for fmt in ("markdown", "html", "json", "csv"):
        out[f"dictionary/{fmt}"] = (await _ok(await c.get(f"/api/v1/model/{model}/export/dictionary", headers=h,
                                                          params={"format": fmt}), 200))["files"]
    return out


async def test_running_the_rules_stores_pending_guesses_and_changes_nothing(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        graph_before = await _ok(await c.get(f"/api/v1/model/{model}", headers=bearer(world["member"])), 200)
        exports_before = await _exports(c, world, model)
        version_before = await _rows(session, "SELECT version_number FROM data_models")
        body = await _run(c, world, model)
        graph_after = await _ok(await c.get(f"/api/v1/model/{model}", headers=bearer(world["member"])), 200)
        exports_after = await _exports(c, world, model)
        assert (await c.post(f"/api/v1/model/{model}/suggestions", headers=bearer(world["viewer"]))).status_code == 403
        listed = await _ok(await c.get(f"/api/v1/model/{model}/suggestions", headers=bearer(world["viewer"])), 200)

    assert body["created"] == len(body["suggestions"]) > 0
    assert body["counts"]["statement"] == f"{body['created']} suggestions pending review"
    assert listed["suggestions"] == body["suggestions"]
    stored = await _rows(session, "SELECT kind, provenance, status, confidence FROM model_suggestions")
    assert len(stored) == body["created"]
    assert {(r["provenance"], r["status"]) for r in stored} == {("heuristic", "pending")}
    assert all(r["confidence"] is None for r in stored if r["kind"] == "pii")
    assert all(r["confidence"] is not None for r in stored if r["kind"] == "agg_time_column")
    # Nothing written to the model, and no artifact shows a guess.
    assert graph_after["entities"] == graph_before["entities"]
    assert await _rows(session, "SELECT version_number FROM data_models") == version_before
    assert await _rows(session, "SELECT count(*) AS n FROM entity_columns WHERE is_pii") == [{"n": 0}]
    assert await _rows(session, "SELECT count(agg_time_column) AS n FROM model_entities") == [{"n": 0}]
    assert exports_after == exports_before


async def test_running_again_adds_nothing_twice(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        first = await _run(c, world, model)
        second = await _run(c, world, model)
    assert second["created"] == 0 and len(second["suggestions"]) == first["created"]


# --- never verified without an approver -------------------------------------------


async def test_a_suggestion_never_reaches_verified_without_an_approver(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        email = _one(await _run(c, world, model), "EMPLOYEES", "EMAIL", "EMAIL")
        url = f"/api/v1/model/{model}/suggestions/{email['suggestion_id']}/accept"
        assert email["status"] == "pending" and email["provenance"] == "heuristic"

        # Negative controls: none of these is a person's decision.
        assert (await c.post(url)).status_code == 401
        assert (await c.post(url, headers=bearer(world["viewer"]))).status_code == 403
        assert (await c.post(url, headers=bearer(world["member"]), json={"status": "verified"})).status_code == 422
        assert (await c.post(url, headers=bearer(world["member"]),
                             json={"decided_by_email": "approver@example.com"})).status_code == 422
        minted = await _ok(await c.post("/api/v1/auth/api-keys", headers=bearer(world["admin"]),
                                        json={"name": "agent", "workspace_id": str(world["ws"].workspace_id),
                                              "role_cap": "MEMBER"}), 201)
        by_key = await c.post(url, headers={"X-API-Key": minted["api_key"]})
        assert by_key.status_code == 403 and "person" in by_key.text
        assert (await _suggestion(session, email["suggestion_id"]))["status"] == "pending"

        # A member accepts: the value is the member's, and its field is pending.
        await _ok(await c.post(url, headers=bearer(world["member"])), 200)
        column = await _column(session, model, "EMPLOYEES", "EMAIL")
        assert (column["is_pii"], column["pii_type"]) == (True, "EMAIL")
        decided = await _suggestion(session, email["suggestion_id"])
        assert (decided["status"], decided["provenance"], decided["decided_by_email"]) == (
            "accepted", "heuristic", "member@example.com")
        field = await _pii_attestation(session, column["column_id"])
        assert (field["status"], field["provenance"], field["provenance_by"]) == (
            "pending", "person", "member@example.com")

        # The member cannot verify it.
        ref = {"fields": [{"entity": "EMPLOYEES", "column": "EMAIL", "field": "pii"}]}
        verify = f"/api/v1/model/{model}/attestations/verify"
        assert (await c.post(verify, headers=bearer(world["member"]), json=ref)).status_code == 403
        assert (await _pii_attestation(session, column["column_id"]))["status"] == "pending"

        # Only an approver can, and only where the three conditions hold.
        result = (await _ok(await c.post(verify, headers=bearer(world["approver"]), json=ref), 200))["results"][0]

    # All three hold here (observed 2026-09-30): HR is a reconciled import, the
    # column's definition passes the 11179-4 rules, and the value is a person's.
    assert result["conditions"] == {"reconciled_import": True, "definition_failures": [], "provenance": "person",
                                    "provenance_verifiable": True}
    assert result["status"] == "verified"
    field = await _pii_attestation(session, column["column_id"])
    assert (field["status"], field["verified_by"]) == ("verified", "approver@example.com")
    # The suggestion itself is never verified: it was accepted, and stays so.
    assert (await _suggestion(session, email["suggestion_id"]))["status"] == "accepted"


async def test_negative_control_the_database_refuses_a_verified_or_non_heuristic_suggestion(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        await _run(c, world, model)
    assert (await _rows(session, "SELECT count(*) AS n FROM model_suggestions"))[0]["n"] > 0, \
        "fixture sanity: there are suggestions to refuse changes to"
    for statement in ("UPDATE model_suggestions SET status = 'verified'",
                      "UPDATE model_suggestions SET provenance = 'person'",
                      # Decided with nobody named.
                      "UPDATE model_suggestions SET status = 'accepted'"):
        # A savepoint each: the app and the test share one uncommitted
        # session, so a full rollback would take the suggestions with it and
        # every later statement would match no row and "pass".
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(text(statement))
    assert await _rows(session, "SELECT DISTINCT status, provenance FROM model_suggestions") == [
        {"status": "pending", "provenance": "heuristic"}]


# --- decisions -------------------------------------------------------------------


async def test_a_rejected_suggestion_is_not_made_again(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        phone = _one(await _run(c, world, model), "EMPLOYEES", "PHONE_NUMBER", "PHONE")
        await _ok(await c.post(f"/api/v1/model/{model}/suggestions/{phone['suggestion_id']}/reject",
                               headers=bearer(world["member"])), 200)
        again = await _run(c, world, model)
        repeat = await c.post(f"/api/v1/model/{model}/suggestions/{phone['suggestion_id']}/accept",
                              headers=bearer(world["member"]))
    assert repeat.status_code == 409
    assert [s["status"] for s in again["suggestions"] if s["column"] == "PHONE_NUMBER"] == ["rejected"]
    decided = await _suggestion(session, phone["suggestion_id"])
    assert (decided["status"], decided["decided_by_email"]) == ("rejected", "member@example.com")
    assert not (await _column(session, model, "EMPLOYEES", "PHONE_NUMBER"))["is_pii"]
    events = await _rows(session, "SELECT action FROM audit_event WHERE action = 'SUGGESTION_DECIDED'")
    assert len(events) == 1


async def test_choosing_one_time_column_supersedes_the_other_candidates(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        body = await _run(c, world, model)
        start = _one(body, "JOB_HISTORY", "START_DATE", "agg_time_column")
        end = _one(body, "JOB_HISTORY", "END_DATE", "agg_time_column")
        await _ok(await c.post(f"/api/v1/model/{model}/suggestions/{start['suggestion_id']}/accept",
                               headers=bearer(world["member"])), 200)
    assert (await _suggestion(session, end["suggestion_id"]))["status"] == "superseded"
    assert await _rows(session, "SELECT agg_time_column FROM model_entities WHERE entity_name = 'JOB_HISTORY'") == [
        {"agg_time_column": "START_DATE"}]


async def _put_graph(c: AsyncClient, w: dict[str, Any], model: str, change: Any) -> None:
    graph = await _ok(await c.get(f"/api/v1/model/{model}", headers=bearer(w["member"])), 200)
    change(graph)
    await _ok(await c.put(f"/api/v1/model/{model}/graph", headers=bearer(w["member"]),
                          json={"entities": graph["entities"], "relationships": graph["relationships"]}), 200)


async def test_a_suggestion_whose_column_is_gone_is_stale_and_cannot_be_accepted(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        phone = _one(await _run(c, world, model), "EMPLOYEES", "PHONE_NUMBER", "PHONE")

        def drop(graph: dict[str, Any]) -> None:
            employees = next(e for e in graph["entities"] if e["entity_name"] == "EMPLOYEES")
            employees["columns"] = [col for col in employees["columns"] if col["name"] != "PHONE_NUMBER"]

        await _put_graph(c, world, model, drop)
        listed = await _ok(await c.get(f"/api/v1/model/{model}/suggestions", headers=bearer(world["member"])), 200)
        refused = await c.post(f"/api/v1/model/{model}/suggestions/{phone['suggestion_id']}/accept",
                               headers=bearer(world["member"]))
    assert refused.status_code == 409 and "no longer in the model" in refused.text
    shown = _one(listed, "EMPLOYEES", "PHONE_NUMBER", "PHONE")
    assert shown["status"] == "pending" and "no longer in the model" in shown["stale"]


async def test_a_field_a_person_filled_another_way_is_superseded(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        name = _one(await _run(c, world, model), "EMPLOYEES", "LAST_NAME", "NAME")

        def mark(graph: dict[str, Any]) -> None:
            employees = next(e for e in graph["entities"] if e["entity_name"] == "EMPLOYEES")
            column = next(col for col in employees["columns"] if col["name"] == "LAST_NAME")
            column["is_pii"], column["pii_type"] = True, "NAME"

        await _put_graph(c, world, model, mark)
        refused = await c.post(f"/api/v1/model/{model}/suggestions/{name['suggestion_id']}/accept",
                               headers=bearer(world["member"]))
        rerun = await _run(c, world, model)
    assert refused.status_code == 409 and "already holds a value" in refused.text
    assert rerun["superseded_now"] >= 1
    assert (await _suggestion(session, name["suggestion_id"]))["status"] == "superseded"


async def test_a_decision_reads_the_suggestion_as_the_database_holds_it(session, world) -> None:
    """A decision decided elsewhere after this session read the row is refused:
    the store re-reads it under the model's lock, not from the session's map."""
    from app.models.metadata_store import DataModel, ModelSuggestion
    from app.services import suggestion_store

    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        email = _one(await _run(c, world, model), "EMPLOYEES", "EMAIL", "EMAIL")

    held = await session.get(ModelSuggestion, uuid.UUID(email["suggestion_id"]))
    assert held is not None and held.status == "pending", "fixture sanity: the session holds it as pending"
    # Another request's decision, committed underneath this session's copy.
    await session.execute(text("UPDATE model_suggestions SET status = 'rejected', decided_by_user_id = :u, "
                               "decided_by_email = 'other@example.com', decided_at = CURRENT_TIMESTAMP "
                               "WHERE suggestion_id = :s"),
                          {"u": world["viewer"].user_id.hex, "s": held.suggestion_id.hex})
    model_row = await session.get(DataModel, uuid.UUID(model))
    with pytest.raises(suggestion_store.Refused, match="rejected"):
        await suggestion_store.accept(session, model_row, held.suggestion_id,
                                      suggestion_store.Actor(world["member"].user_id, "member@example.com"))


async def test_a_column_retyped_out_of_its_rule_is_stale(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "oracle/hr.sql", "oracle")
        email = _one(await _run(c, world, model), "EMPLOYEES", "EMAIL", "EMAIL")

        def retype(graph: dict[str, Any]) -> None:
            employees = next(e for e in graph["entities"] if e["entity_name"] == "EMPLOYEES")
            next(col for col in employees["columns"] if col["name"] == "EMAIL")["data_type"] = "INTEGER"

        await _put_graph(c, world, model, retype)
        refused = await c.post(f"/api/v1/model/{model}/suggestions/{email['suggestion_id']}/accept",
                               headers=bearer(world["member"]))
    assert refused.status_code == 409 and "no longer fits rule pii.email.name" in refused.text


def test_a_different_column_under_the_same_name_is_stale() -> None:
    from app.models.metadata_store import ModelSuggestion
    from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
    from app.services import suggestion_store

    def model(stable_id: int) -> SynthesizedModel:
        return SynthesizedModel(paradigm="3NF", entities=[EntitySchema(
            entity_name="t", entity_type="TABLE", columns=[
                ColumnSchema(name="id", data_type="INTEGER", is_primary_key=True, stable_id=1),
                ColumnSchema(name="email", data_type="VARCHAR(50)", stable_id=stable_id)])])

    row = ModelSuggestion(kind="pii", entity_name="t", column_name="email", column_stable_id=2,
                          rule_name="pii.email.name", suggested={}, signals={})
    assert suggestion_store.state(model(2), row).stale is None
    assert "different column" in (suggestion_store.state(model(7), row).stale or "")


# --- AdventureWorks and MetricFlow ---------------------------------------------


def _semantic_model(files: dict[str, str], name: str) -> dict[str, Any]:
    document = yaml.safe_load(files["semantic_models.yml"])
    found = [m for m in document["semantic_models"] if m["name"] == name]
    assert len(found) == 1, f"fixture sanity: one semantic model {name}"
    return found[0]


async def _metricflow(c: AsyncClient, w: dict[str, Any], model: str) -> dict[str, str]:
    return (await _ok(await c.get(f"/api/v1/model/{model}/export/semantic", headers=bearer(w["member"]),
                                  params={"engine": "metricflow"}), 200))["files"]


async def test_adventureworks_gets_metricflow_measures_only_after_a_person_confirms_the_time_column(
        session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, "tsql/adventureworks.sql", "tsql")
        imported = await _metricflow(c, world, model)
        body = await _run(c, world, model)
        pending = await _metricflow(c, world, model)
        order_date = _one(body, "SalesOrderHeader", "OrderDate", "agg_time_column")
        await _ok(await c.post(f"/api/v1/model/{model}/suggestions/{order_date['suggestion_id']}/accept",
                               headers=bearer(world["member"])), 200)
        confirmed = await _metricflow(c, world, model)

    # MetricFlow names are lower snake case (Step 5a.1); each expr is the column's own name.
    before = _semantic_model(imported, "sales_order_header")
    assert "measures" not in before and "defaults" not in before, "an import declares no measures"
    # Control: a pending suggestion is not a confirmation.
    assert pending == imported
    after = _semantic_model(confirmed, "sales_order_header")
    assert after["defaults"] == {"agg_time_dimension": "order_date"}
    # The count measure is emitted exactly when the entity has a time axis.
    assert {"name": "sales_order_header_count", "agg": "count", "expr": "1"} in after["measures"]
    # Only the entity a person confirmed.
    assert "measures" not in _semantic_model(confirmed, "sales_order_detail")
    assert await _rows(session, "SELECT entity_name, agg_time_column FROM model_entities "
                                "WHERE agg_time_column IS NOT NULL") == [
        {"entity_name": "SalesOrderHeader", "agg_time_column": "OrderDate"}]


def test_money_amounts_are_measures_once_a_time_column_is_confirmed() -> None:
    """Found in Step 4 as a strict xfail (MONEY was not numeric in the semantic
    exporters); fixed in Step 5a.1, see test_semantic_measures.py."""
    from app.services.ddl_import.importer import import_ddl
    from app.services.exporter_service import ExporterService

    model = import_ddl((DDL / "tsql" / "adventureworks.sql").read_bytes(), "tsql", "adventureworks.sql").model
    header = next(e for e in model.entities if e.entity_name == "SalesOrderHeader")
    header.agg_time_column = "OrderDate"
    files = ExporterService().export_semantic_layer(model, "metricflow")
    measures = {m["expr"] for m in _semantic_model(files, "sales_order_header")["measures"]}
    assert {"SubTotal", "TaxAmt", "Freight"} <= measures
