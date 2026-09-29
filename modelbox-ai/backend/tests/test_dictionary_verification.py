"""Field verification, lapse, and the classification scale (Sprint 8 Step 4b evidence).

Driven over HTTP with real credentials (`tests/_real_auth.py`); what is stored
is read back by raw SQL, not through the ORM that wrote it. Each claim has a
case where it could fail:

* "verified" needs all three conditions. An **unreconciled import**, a
  **definition failing the ISO/IEC 11179-4 rules**, and a **value without
  provenance** each keep a field unverified; the control for each is the same
  field with that one condition met, which verifies.
* **Editing a verified field's value makes it pending**, with one
  FIELD_STATUS_CHANGED event; the control saves the same graph unchanged and
  the field stays verified with no event.
* **Deleting a classification level in use is refused**; the control deletes an
  unused level. Renaming a level renames every use without changing its value.
* **Setting "verified" directly is refused**: a verify request stating a
  status, a graph carrying a status, and a write to the attestations route.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import definition_rules
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)

RECONCILED = b"""
CREATE TABLE public.customer (
    customer_id integer NOT NULL,
    email character varying(255),
    CONSTRAINT customer_pkey PRIMARY KEY (customer_id)
);
COMMENT ON TABLE public.customer IS 'A person or organisation that buys from us.';
COMMENT ON COLUMN public.customer.customer_id IS 'Number the billing system assigns to each buyer.';
COMMENT ON COLUMN public.customer.email IS 'Address the buyer receives invoices at.';
"""
# A HYBRID TABLE is a named import failure: the model is saved unreconciled.
UNRECONCILED = b"""
create or replace TABLE CUSTOMER (
    CUSTOMER_ID NUMBER(38,0) NOT NULL,
    EMAIL VARCHAR(255),
    primary key (CUSTOMER_ID)
);
create or replace HYBRID TABLE H (
    ID NUMBER(38,0) NOT NULL,
    primary key (ID)
);
"""
GOOD_DEFINITION = "Address the buyer receives invoices at."


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    approver = await make_user(session, "approver@example.com")
    member = await make_user(session, "member@example.com")
    admin = await make_user(session, "admin@example.com")
    outsider = await make_user(session, "outsider@example.com")
    workspace = await make_workspace(session, "W", {approver: "APPROVER", member: "MEMBER", admin: "ADMIN"})
    other = await make_workspace(session, "Other", {outsider: "OWNER"})
    await session.commit()
    return {"approver": approver, "member": member, "admin": admin, "outsider": outsider, "ws": workspace,
            "other": other}


async def _ok(response: Any, *codes: int) -> Any:
    assert response.status_code in codes, f"{response.request.url}: {response.status_code} {response.text[:400]}"
    return response.json() if response.content else None


async def _import(c: AsyncClient, w: dict[str, Any], raw: bytes, dialect: str) -> str:
    body = await _ok(await c.post(
        "/api/v1/import/ddl", params={"workspace_id": str(w["ws"].workspace_id)},
        files={"file": (f"{dialect}.sql", raw, "application/sql")}, data={"dialect": dialect},
        headers=bearer(w["member"])), 201)
    return body["model_id"]


async def _graph(c: AsyncClient, w: dict[str, Any], model_id: str) -> dict[str, Any]:
    return await _ok(await c.get(f"/api/v1/model/{model_id}", headers=bearer(w["member"])), 200)


async def _save(c: AsyncClient, w: dict[str, Any], model_id: str, graph: dict[str, Any], *codes: int) -> Any:
    return await _ok(await c.put(f"/api/v1/model/{model_id}/graph", headers=bearer(w["member"]),
                                 json={"entities": graph["entities"], "relationships": graph["relationships"]}),
                     *(codes or (200,)))


def _column(graph: dict[str, Any], name: str) -> dict[str, Any]:
    return next(col for e in graph["entities"] for col in e["columns"] if col["name"].lower() == name)


async def _verify(c: AsyncClient, w: dict[str, Any], model_id: str, fields: list[dict[str, Any]] | None) -> dict:
    return await _ok(await c.post(f"/api/v1/model/{model_id}/attestations/verify", headers=bearer(w["approver"]),
                                  json={"fields": fields}), 200)


async def _status(session: AsyncSession, model_id: str, column: str | None, field: str) -> tuple | None:
    """The field's row as the database holds it, by raw SQL."""
    rows = (await session.execute(text(
        "SELECT a.status, a.provenance, a.verified_by FROM field_attestations a "
        "LEFT JOIN entity_columns c ON c.column_id = a.column_id "
        "WHERE a.model_id = :m AND a.field_key = :f AND "
        "(lower(c.column_name) = :c OR (:c IS NULL AND a.column_id IS NULL))"),
        {"m": model_id.replace("-", ""), "f": field, "c": column})).all()
    if not rows:  # SQLite stores UUIDs without dashes; PostgreSQL with
        rows = (await session.execute(text(
            "SELECT a.status, a.provenance, a.verified_by FROM field_attestations a "
            "LEFT JOIN entity_columns c ON c.column_id = a.column_id "
            "WHERE CAST(a.model_id AS VARCHAR(40)) = :m AND a.field_key = :f AND "
            "(lower(c.column_name) = :c OR (:c IS NULL AND a.column_id IS NULL))"),
            {"m": model_id, "f": field, "c": column})).all()
    assert len(rows) <= 1
    return tuple(rows[0]) if rows else None


async def _events(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(text(
        "SELECT detail FROM audit_event WHERE action = 'FIELD_STATUS_CHANGED' ORDER BY occurred_at"))).all()
    return [d if isinstance(d, dict) else json.loads(d) for (d,) in rows]


def _field(entity: str, column: str | None, field: str) -> dict[str, Any]:
    return {"entity": entity, "column": column, "field": field}


# --- the three conditions ------------------------------------------------------


async def test_a_reconciled_import_with_a_sound_definition_and_provenance_verifies(session, world) -> None:
    """The control for the three refusals below: every condition holds."""
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        result = await _verify(c, world, model, [_field("customer", "email", "description"),
                                                 _field("customer", "email", "data_type")])
    assert [r["status"] for r in result["results"]] == ["verified", "verified"]
    assert result["results"][0]["conditions"] == {"reconciled_import": True, "definition_failures": [],
                                                  "provenance": "source_comment", "provenance_verifiable": True}
    assert await _status(session, model, "email", "description") == (
        "verified", "source_comment", "approver@example.com")
    assert await _status(session, model, "email", "data_type") == ("verified", "ddl", "approver@example.com")
    assert [(e["field"], e["from"], e["to"]) for e in await _events(session)] == [
        ("description", "pending", "verified"), ("data_type", "pending", "verified")]


async def test_an_unreconciled_import_keeps_a_field_unverified(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, UNRECONCILED, "snowflake")
        graph = await _graph(c, world, model)
        _column(graph, "email")["description"] = GOOD_DEFINITION  # conditions 2 and 3 now hold
        await _save(c, world, model, graph)
        result = await _verify(c, world, model, [_field("CUSTOMER", "EMAIL", "description")])
    (only,) = result["results"]
    assert only["status"] == "pending"
    assert only["conditions"] == {"reconciled_import": False, "definition_failures": [], "provenance": "person",
                                  "provenance_verifiable": True}
    assert await _status(session, model, "email", "description") == ("pending", "person", None)
    assert await _events(session) == []


async def test_a_definition_failing_the_11179_rules_keeps_a_field_unverified(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        graph = await _graph(c, world, model)
        _column(graph, "email")["description"] = "Email."  # the name restated, one word
        await _save(c, world, model, graph)
        failing = await _verify(c, world, model, [_field("customer", "email", "description"),
                                                  _field("customer", "email", "data_type")])
        # The control: the same field, a sound definition.
        _column(graph, "email")["description"] = GOOD_DEFINITION
        await _save(c, world, model, graph)
        passing = await _verify(c, world, model, [_field("customer", "email", "description")])
    assert [r["status"] for r in failing["results"]] == ["pending", "pending"]
    assert failing["results"][0]["conditions"]["definition_failures"] == ["NOT_A_PHRASE", "CIRCULAR"]
    assert failing["results"][1]["conditions"]["definition_failures"] == ["NOT_A_PHRASE", "CIRCULAR"], \
        "every field of the column rests on the column's definition"
    assert passing["results"][0]["status"] == "verified"


async def test_a_value_without_provenance_keeps_a_field_unverified(session, world) -> None:
    """The shape 0026 gives an existing PII value: recorded, no provenance."""
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        await _forget_provenance(session)
        result = await _verify(c, world, model, [_field("customer", "email", "description")])
        listed = await _ok(await c.get(f"/api/v1/model/{model}/attestations", headers=bearer(world["member"])), 200)
    (only,) = result["results"]
    assert only["status"] == "recorded"
    assert only["conditions"] == {"reconciled_import": True, "definition_failures": [], "provenance": None,
                                  "provenance_verifiable": False}
    assert await _status(session, model, "email", "description") == ("recorded", None, None)
    assert {f["status"] for f in listed["fields"]} == {"recorded"}
    assert listed["summary"]["verified"] == 0


async def test_a_field_with_no_row_at_all_keeps_unverified(session, world) -> None:
    """A model saved before 0026 has no rows: its values are recorded."""
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        await session.execute(text("DELETE FROM field_attestations"))
        await session.commit()
        result = await _verify(c, world, model, None)  # every field
    assert {r["status"] for r in result["results"]} == {"recorded"}
    assert result["summary"]["verified"] == 0


async def test_an_ai_draft_is_never_verified(session, world, monkeypatch: pytest.MonkeyPatch) -> None:
    """R2-1.3: an AI draft is provenance of a kind that cannot support
    verified, even on a reconciled import with a sound definition. The import
    is written as the synthesis engine writes (source "ai")."""
    from app.api.v1.endpoints import ddl_import
    from app.services.graph_repository import GraphRepository

    real = GraphRepository.replace_graph

    async def as_ai(self, model_id, entities, relationships, **_: Any) -> None:  # type: ignore[no-untyped-def]
        await real(self, model_id, entities, relationships, source="ai")

    monkeypatch.setattr(ddl_import.GraphRepository, "replace_graph", as_ai)
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        result = await _verify(c, world, model, [_field("customer", "email", "description")])
    assert result["results"][0]["status"] == "pending"
    assert result["results"][0]["conditions"] == {"reconciled_import": True, "definition_failures": [],
                                                  "provenance": "ai_draft", "provenance_verifiable": False}


def _without(condition: str):  # type: ignore[no-untyped-def]
    """``attestation.evaluate`` with one condition forced to hold."""
    from app.services import attestation

    real = attestation.evaluate

    def patched(model, field, row):  # type: ignore[no-untyped-def]
        found = real(model, field, row)
        if condition == "reconciled":
            return attestation.Evaluation(found.key, True, found.definition_failures, found.provenance)
        if condition == "definition":
            return attestation.Evaluation(found.key, found.reconciled_import, [], found.provenance)
        return attestation.Evaluation(found.key, found.reconciled_import, found.definition_failures, "person")

    return patched


async def _refused_case(c: AsyncClient, session: AsyncSession, w: dict[str, Any], condition: str) -> str:
    """Each refusal's setting, with only ``condition`` failing; the field's status after verify."""
    if condition == "reconciled":
        model = await _import(c, w, UNRECONCILED, "snowflake")
        graph = await _graph(c, w, model)
        _column(graph, "email")["description"] = GOOD_DEFINITION
        await _save(c, w, model, graph)
        ref = _field("CUSTOMER", "EMAIL", "description")
    else:
        model = await _import(c, w, RECONCILED, "postgres")
        ref = _field("customer", "email", "description")
        if condition == "definition":
            graph = await _graph(c, w, model)
            _column(graph, "email")["description"] = "Email."
            await _save(c, w, model, graph)
        else:
            await _forget_provenance(session)
    return (await _verify(c, w, model, [ref]))["results"][0]["status"]


async def _forget_provenance(session: AsyncSession) -> None:
    """Every row as 0026 maps an existing PII value: recorded, no provenance."""
    await session.execute(text("UPDATE field_attestations SET status = 'recorded', provenance = NULL, "
                               "provenance_by = NULL, provenance_at = NULL"))
    await session.commit()


@pytest.mark.parametrize("condition", ["reconciled", "definition"])
async def test_negative_control_each_refusal_is_its_condition(session, world, monkeypatch, condition) -> None:
    """With the one failing condition forced to hold, the same field verifies."""
    from app.services import attestation

    monkeypatch.setattr(attestation, "evaluate", _without(condition))
    async with real_client(session) as c:
        assert await _refused_case(c, session, world, condition) == "verified"


async def test_negative_control_without_the_provenance_condition_the_database_refuses(
    session, world, monkeypatch
) -> None:
    """With the application's provenance condition forced to hold, the write
    reaches the database, whose CHECK refuses a verified row without
    provenance: two layers, and the first is what refuses in normal use."""
    from sqlalchemy.exc import IntegrityError

    from app.services import attestation

    monkeypatch.setattr(attestation, "evaluate", _without("provenance"))
    async with real_client(session) as c:
        with pytest.raises(IntegrityError, match="ck_field_attestations_verified|CHECK constraint"):
            await _refused_case(c, session, world, "provenance")


# --- lapse ------------------------------------------------------------------------


async def test_editing_a_verified_value_makes_it_pending(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        await _verify(c, world, model, [_field("customer", "email", "data_type"),
                                        _field("customer", "email", "description")])
        graph = await _graph(c, world, model)
        await _save(c, world, model, graph)  # the control: nothing changed
        unchanged = (await _status(session, model, "email", "data_type"),
                     await _status(session, model, "email", "description"))
        events_after_control = len(await _events(session))
        _column(graph, "email")["data_type"] = "VARCHAR(320)"
        await _save(c, world, model, graph)
    assert unchanged == (("verified", "ddl", "approver@example.com"),
                         ("verified", "source_comment", "approver@example.com"))
    assert events_after_control == 2, "saving an unchanged graph changes no status"
    assert await _status(session, model, "email", "data_type") == ("pending", "person", None)
    assert await _status(session, model, "email", "description") == (
        "verified", "source_comment", "approver@example.com"), "only the changed field lapses"
    last = (await _events(session))[-1]
    assert (last["field"], last["from"], last["to"], last["reason"]) == (
        "data_type", "verified", "pending", "the value changed")
    assert "VARCHAR" not in json.dumps(last), "the event names the field, never its value"


async def test_the_dictionary_shows_verified_only_where_the_attestation_says_so(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        await _verify(c, world, model, [_field("customer", "email", "description")])
        doc = json.loads((await _ok(await c.get(f"/api/v1/model/{model}/export/dictionary",
                                                params={"format": "json"}, headers=bearer(world["member"])),
                                    200))["files"]["data_dictionary.json"])
    customer = doc["entities"][0]
    verified = [(col["name"], k) for col in customer["columns"] for k, v in col["status"].items() if v == "verified"]
    verified += [(None, k) for k, v in customer["status"].items() if v == "verified"]
    assert verified == [("email", "description")]
    total = doc["verification"]["fields"]
    assert doc["verification"]["statement"] == f"1 of {total} fields verified, {total - 1} pending review"


# --- direct setting is refused ------------------------------------------------------


async def test_setting_verified_directly_is_refused(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        stated = await c.post(f"/api/v1/model/{model}/attestations/verify", headers=bearer(world["approver"]),
                              json={"fields": [_field("customer", "email", "unit")], "status": "verified"})
        in_field = await c.post(f"/api/v1/model/{model}/attestations/verify", headers=bearer(world["approver"]),
                                json={"fields": [{**_field("customer", "email", "description"),
                                                  "status": "verified"}]})
        graph = await _graph(c, world, model)
        _column(graph, "email")["field_status"] = {"description": "verified"}
        in_graph = await c.put(f"/api/v1/model/{model}/graph", headers=bearer(world["member"]),
                               json={"entities": graph["entities"], "relationships": graph["relationships"]})
        written = await c.patch(f"/api/v1/model/{model}/attestations", headers=bearer(world["approver"]),
                                json={"fields": [{**_field("customer", "email", "description"),
                                                  "status": "verified"}]})
        as_member = await c.post(f"/api/v1/model/{model}/attestations/verify", headers=bearer(world["member"]),
                                 json={"fields": [_field("customer", "email", "description")]})
    assert (stated.status_code, in_field.status_code, in_graph.status_code, written.status_code,
            as_member.status_code) == (422, 422, 422, 405, 403)
    assert "attestations/verify" in in_graph.text
    assert await _status(session, model, "email", "description") == ("pending", "source_comment", None)
    assert await _events(session) == []


async def test_negative_control_the_same_request_without_a_status_is_accepted(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        result = await _verify(c, world, model, [_field("customer", "email", "description")])
    assert result["results"][0]["status"] == "verified"


async def test_the_database_refuses_a_verified_row_without_a_reviewer(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError, match="ck_field_attestations_verified|CHECK constraint"):
        await session.execute(text("UPDATE field_attestations SET status = 'verified' WHERE field_key = 'unit' "
                                   "OR field_key = 'description'"))
    await session.rollback()
    assert model


# --- the classification scale ------------------------------------------------------


async def _scale(c: AsyncClient, w: dict[str, Any], who: str = "member") -> dict[str, Any]:
    return await _ok(await c.get(f"/api/v1/workspaces/{w['ws'].workspace_id}/classification",
                                 headers=bearer(w[who])), 200)


async def test_every_workspace_starts_with_the_four_levels(session, world) -> None:
    async with real_client(session) as c:
        scale = await _scale(c, world)
    assert [(lv["name"], lv["rank"]) for lv in scale["levels"]] == [
        ("Public", 1), ("Internal", 2), ("Confidential", 3), ("Restricted", 4)]


async def test_deleting_a_level_in_use_is_refused(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        scale = await _scale(c, world)
        confidential, public = scale["levels"][2]["level_id"], scale["levels"][0]["level_id"]
        graph = await _graph(c, world, model)
        _column(graph, "email")["classification_level_id"] = confidential
        await _save(c, world, model, graph)
        base = f"/api/v1/workspaces/{world['ws'].workspace_id}/classification/levels"
        refused = await c.delete(f"{base}/{confidential}", headers=bearer(world["admin"]))
        allowed = await c.delete(f"{base}/{public}", headers=bearer(world["admin"]))  # the control: unused
        after = await _scale(c, world)
    assert refused.status_code == 409 and "used by 1 column" in refused.text
    assert allowed.status_code == 204
    assert [lv["name"] for lv in after["levels"]] == ["Internal", "Confidential", "Restricted"]
    assert [lv["columns_using"] for lv in after["levels"]] == [0, 1, 0]
    # Two workspaces of four levels each; only the unused Public went.
    stored = (await session.execute(text("SELECT name, count(*) FROM classification_levels GROUP BY name"))).all()
    assert dict(stored) == {"Public": 1, "Internal": 2, "Confidential": 2, "Restricted": 2}


async def test_renaming_a_level_renames_every_use_without_changing_the_value(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        scale = await _scale(c, world)
        level = scale["levels"][2]["level_id"]
        graph = await _graph(c, world, model)
        _column(graph, "email")["classification_level_id"] = level
        await _save(c, world, model, graph)
        before = await _status(session, model, "email", "classification")
        await _ok(await c.patch(f"/api/v1/workspaces/{world['ws'].workspace_id}/classification/levels/{level}",
                                json={"name": "Commercial in confidence"}, headers=bearer(world["admin"])), 200)
        md = (await _ok(await c.get(f"/api/v1/model/{model}/export/dictionary", params={"format": "markdown"},
                                    headers=bearer(world["member"])), 200))["files"]["data_dictionary.md"]
        await _save(c, world, model, await _graph(c, world, model))
    assert "Commercial in confidence [pending review]" in md
    assert await _status(session, model, "email", "classification") == before == ("pending", "person", None)


async def test_a_level_from_another_workspace_is_refused(session, world) -> None:
    async with real_client(session) as c:
        model = await _import(c, world, RECONCILED, "postgres")
        foreign = (await _ok(await c.get(f"/api/v1/workspaces/{world['other'].workspace_id}/classification",
                                         headers=bearer(world["outsider"])), 200))["levels"][0]["level_id"]
        graph = await _graph(c, world, model)
        _column(graph, "email")["classification_level_id"] = foreign
        refused = await c.put(f"/api/v1/model/{model}/graph", headers=bearer(world["member"]),
                              json={"entities": graph["entities"], "relationships": graph["relationships"]})
    assert refused.status_code == 422 and "not a level of this workspace" in refused.text


async def test_only_an_admin_changes_the_scale(session, world) -> None:
    async with real_client(session) as c:
        base = f"/api/v1/workspaces/{world['ws'].workspace_id}/classification/levels"
        by_member = await c.post(base, json={"name": "Secret"}, headers=bearer(world["member"]))
        by_outsider = await c.get(f"/api/v1/workspaces/{world['ws'].workspace_id}/classification",
                                  headers=bearer(world["outsider"]))
        by_admin = await c.post(base, json={"name": "Secret"}, headers=bearer(world["admin"]))
    assert (by_member.status_code, by_outsider.status_code, by_admin.status_code) == (403, 403, 201)
    assert [lv["name"] for lv in by_admin.json()["levels"]][-1] == "Secret"


# --- the 11179-4 rules, one by one ----------------------------------------------------


@pytest.mark.parametrize(("definition", "names", "failures"), [
    ("Address the buyer receives invoices at.", ("email",), []),
    (None, ("email",), ["MISSING"]),
    ("   ", ("email",), ["MISSING"]),
    ("Email.", ("email",), ["NOT_A_PHRASE", "CIRCULAR"]),
    ("The customer id.", ("customer_id",), ["CIRCULAR"]),
    ("Customer identifier", ("customerId",), []),
    ("Not a billing address.", ("ship_to",), ["ONLY_NEGATIVE"]),
    ("Quantity ordered", ("qty", "Quantity ordered"), ["CIRCULAR"]),
])
def test_each_11179_rule(definition: str | None, names: tuple[str, ...], failures: list[str]) -> None:
    assert definition_rules.check(definition, *names) == failures
