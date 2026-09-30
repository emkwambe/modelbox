"""Source-to-target mapping over HTTP, with real credentials (Sprint 9 Step 3).

The Oracle HR export is imported as the source, and a target derived from it
(``dim_employee``) is imported beside it. Both go through the product's own
import route, and everything the tests assert about what is stored is read
back by raw SQL. Each negative control removes one thing and expects the
document, or the database, to say so:

* a pending proposal is never counted as mapped;
* deleting one accepted mapping is reported as missing;
* removing a mapped source column raises the drift flag;
* a proposal cannot become accepted without a person's identity: no
  credentials, an API key, and a body naming a decider are each refused, and
  the proposal stays pending.
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

from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)
from tests.test_ddl_round_trip import DDL

TARGET_DDL = b"""
CREATE TABLE public.dim_employee (
    employee_key integer NOT NULL,
    employee_id numeric(6,0),
    full_name character varying(46),
    email character varying(25),
    hire_date date,
    department_name character varying(30),
    salary numeric(8,2),
    load_batch character varying(20),
    CONSTRAINT dim_employee_pkey PRIMARY KEY (employee_key)
);
"""
TARGET_COLUMNS = 8  # the table above


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    member = await make_user(session, "member@example.com")
    viewer = await make_user(session, "viewer@example.com")
    admin = await make_user(session, "admin@example.com")
    outsider = await make_user(session, "outsider@example.com")
    workspace = await make_workspace(session, "W", {member: "MEMBER", viewer: "VIEWER", admin: "ADMIN"})
    other = await make_workspace(session, "Other", {outsider: "OWNER"})
    await session.commit()
    return {"member": member, "viewer": viewer, "admin": admin, "outsider": outsider, "ws": workspace,
            "other": other}


async def _ok(response: Any, *codes: int) -> Any:
    assert response.status_code in codes, f"{response.request.url}: {response.status_code} {response.text[:500]}"
    return response.json() if response.content else None


async def _import(c: AsyncClient, w: dict[str, Any], raw: bytes, dialect: str, name: str) -> str:
    body = await _ok(await c.post(
        "/api/v1/import/ddl", params={"workspace_id": str(w["ws"].workspace_id)},
        files={"file": (name, raw, "application/sql")}, data={"dialect": dialect},
        headers=bearer(w["member"])), 201)
    return body["model_id"]


async def _document(c: AsyncClient, w: dict[str, Any]) -> tuple[str, str, str]:
    source = await _import(c, w, (DDL / "oracle" / "hr.sql").read_bytes(), "oracle", "hr.sql")
    target = await _import(c, w, TARGET_DDL, "postgres", "dim.sql")
    report = await _ok(await c.post(f"/api/v1/model/{target}/mappings", headers=bearer(w["member"]),
                                    json={"source_model_id": source, "title": "HR to dim_employee",
                                          "source_system": "HR", "target_system": "EDW"}), 201)
    return report["document"]["document_id"], source, target


def _pick(entity: str, column: str) -> dict[str, str]:
    return {"entity": entity, "column": column}


# Every target column of dim_employee, accounted for by a person.
PLAN: list[dict[str, Any]] = [
    {"target": _pick("dim_employee", "employee_key"), "kind": "derived",
     "fields": {"rule_description": "surrogate key assigned by the load"}},
    {"target": _pick("dim_employee", "employee_id"), "kind": "mapped",
     "sources": [_pick("EMPLOYEES", "EMPLOYEE_ID")], "fields": {"transformation_type": "IDENTITY"}},
    {"target": _pick("dim_employee", "full_name"), "kind": "mapped",
     "sources": [_pick("EMPLOYEES", "FIRST_NAME"), _pick("EMPLOYEES", "LAST_NAME")],
     "fields": {"transformation_type": "TRANSFORMATION", "logic": "FIRST_NAME || ' ' || LAST_NAME"}},
    {"target": _pick("dim_employee", "email"), "kind": "mapped", "sources": [_pick("EMPLOYEES", "EMAIL")]},
    {"target": _pick("dim_employee", "hire_date"), "kind": "mapped", "sources": [_pick("EMPLOYEES", "HIRE_DATE")]},
    {"target": _pick("dim_employee", "department_name"), "kind": "mapped",
     "sources": [_pick("DEPARTMENTS", "DEPARTMENT_NAME")],
     "fields": {"transformation_type": "JOIN", "join_filter": "EMPLOYEES.DEPARTMENT_ID = DEPARTMENTS.DEPARTMENT_ID"}},
    {"target": _pick("dim_employee", "salary"), "kind": "mapped", "sources": [_pick("EMPLOYEES", "SALARY")]},
    {"target": _pick("dim_employee", "load_batch"), "kind": "constant", "fields": {"rule_description": "batch id"}},
]


async def _author(c: AsyncClient, w: dict[str, Any], document: str, plan: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for entry in plan:
        report = await _ok(await c.post(f"/api/v1/mappings/{document}/entries", headers=bearer(w["member"]),
                                        json=entry), 201)
    return report


async def _count(session: AsyncSession, sql: str, **params: object) -> int:
    return int((await session.execute(text(sql), params)).scalar_one())


# --- the evidence case -------------------------------------------------------------


async def test_hr_to_a_derived_target_accounts_for_every_target_column(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        report = await _author(c, world, document, PLAN)
    done = report["completeness"]
    mapped = sum(1 for p in PLAN if p["kind"] == "mapped")
    assert (done["total"], done["mapped"], done["explicitly_unmapped"], done["silent"], done["pending"]) == (
        TARGET_COLUMNS, mapped, len(PLAN) - mapped, 0, 0)
    assert done["complete"] and done["summary"].startswith(
        f"{mapped} of {TARGET_COLUMNS} target columns mapped, {len(PLAN) - mapped} explicitly unmapped, 0 silent")
    # Read back by SQL: one entry and one decision per target column, each by the member.
    assert await _count(session, "SELECT count(*) FROM mapping_entries") == len(PLAN)
    assert await _count(session, "SELECT count(*) FROM mapping_decisions WHERE decided_by_email = :e",
                        e="member@example.com") == len(PLAN)
    kinds = {r for (r,) in (await session.execute(text("SELECT DISTINCT decision FROM mapping_decisions"))).all()}
    assert kinds == {"authored", "declared_unmapped"}


async def test_the_exports_are_served_in_every_format(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        report = await _author(c, world, document, PLAN[:-1])  # load_batch left silent
        for fmt in ("csv", "markdown", "html", "json"):
            body = await _ok(await c.get(f"/api/v1/mappings/{document}/export", params={"format": fmt},
                                         headers=bearer(world["viewer"])), 200)
            assert report["completeness"]["summary"] in body["content"], fmt
        refused = await c.get(f"/api/v1/mappings/{document}/export", params={"format": "xlsx"},
                              headers=bearer(world["viewer"]))
        assert refused.status_code == 422
    csv_body = [line for line in body["content"].splitlines()]  # json, the last one
    assert csv_body and json.loads(body["content"])["completeness"]["silent"] == 1


async def test_the_lineage_of_a_target_column_names_its_sources_and_decisions(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        await _author(c, world, document, PLAN)
        lineage = await _ok(await c.get(f"/api/v1/mappings/{document}/lineage", headers=bearer(world["viewer"]),
                                        params={"entity": "dim_employee", "column": "full_name"}), 200)
    assert [(s["entity"], s["column"], s["exists"]) for s in lineage["row"]["entry"]["sources"]] == [
        ("EMPLOYEES", "FIRST_NAME", True), ("EMPLOYEES", "LAST_NAME", True)]
    assert [d["decision"] for d in lineage["decisions"]] == ["authored"]
    evidence = lineage["decisions"][0]["evidence"]
    assert [s["column"] for s in evidence["sources"]] == ["FIRST_NAME", "LAST_NAME"]
    assert evidence["target"]["type"] and evidence["before"] is None and evidence["after"]["kind"] == "mapped"


# --- the negative controls ---------------------------------------------------------


async def test_control_a_pending_proposal_is_never_counted_as_mapped(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        before = await _author(c, world, document, [PLAN[0]])
        after = await _ok(await c.post(f"/api/v1/mappings/{document}/proposals", headers=bearer(world["member"])),
                          200)
    assert after["completeness"]["pending_proposals"] > 0
    assert after["completeness"]["mapped"] == before["completeness"]["mapped"] == 0
    assert after["completeness"]["pending"] > 0 and not after["completeness"]["complete"]
    assert await _count(session, "SELECT count(*) FROM mapping_entries") == 1  # proposals are not entries
    email = next(r for r in after["rows"] if r["target"]["column"] == "email")
    assert email["status"] == "pending" and email["entry"] is None
    best = email["proposals"][0]
    assert best["sources"][0]["column"] == "EMAIL"
    assert best["confidence"] == pytest.approx(0.7 * best["name_similarity"] + 0.3 * best["type_compatibility"],
                                               abs=1e-4)


async def test_accepting_a_proposal_records_the_person_and_the_evidence_shown(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        proposed = await _ok(await c.post(f"/api/v1/mappings/{document}/proposals", headers=bearer(world["member"])),
                             200)
        email = next(r for r in proposed["rows"] if r["target"]["column"] == "email")
        offered = email["proposals"][0]
        accepted = await _ok(await c.post(
            f"/api/v1/mappings/{document}/proposals/{offered['proposal_id']}/accept",
            headers=bearer(world["member"])), 200)
    row = next(r for r in accepted["rows"] if r["target"]["column"] == "email")
    assert row["status"] == "mapped" and row["proposals"] == []  # the others are superseded
    decision = (await session.execute(text(
        "SELECT decision, decided_by_email, evidence FROM mapping_decisions"))).one()
    evidence = decision[2] if isinstance(decision[2], dict) else json.loads(decision[2])
    assert (decision[0], decision[1]) == ("accepted", "member@example.com")
    assert evidence["proposal"]["confidence"] == offered["confidence"]
    assert evidence["proposal"]["name_similarity"] == offered["name_similarity"]
    statuses = {s for (s,) in (await session.execute(text(
        "SELECT status FROM mapping_proposals WHERE target_column = 'email'"))).all()}
    assert "accepted" in statuses and "pending" not in statuses


async def test_control_deleting_one_accepted_mapping_is_reported_as_missing(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        report = await _author(c, world, document, PLAN)
        key = next(r["entry"]["mapping_key"] for r in report["rows"] if r["target"]["column"] == "email")
        after = await _ok(await c.delete(f"/api/v1/mappings/{document}/entries/{key}",
                                         headers=bearer(world["member"])), 200)
    assert after["completeness"]["silent"] == 1 and not after["completeness"]["complete"]
    assert [r["target"]["column"] for r in after["rows"] if r["status"] == "silent"] == ["email"]
    # The removal is a decision, and the ledger keeps it.
    assert await _count(session, "SELECT count(*) FROM mapping_decisions WHERE decision = 'removed' "
                                 "AND mapping_key = :k", k=key) == 1


async def test_control_removing_a_mapped_source_column_raises_the_drift_flag(session, world) -> None:
    async with real_client(session) as c:
        document, source, _ = await _document(c, world)
        await _author(c, world, document, PLAN)
        graph = await _ok(await c.get(f"/api/v1/model/{source}", headers=bearer(world["member"])), 200)
        employees = next(e for e in graph["entities"] if e["entity_name"] == "EMPLOYEES")
        employees["columns"] = [col for col in employees["columns"] if col["name"] != "EMAIL"]
        employees["unique_constraints"] = [u for u in employees.get("unique_constraints", [])
                                           if "EMAIL" not in u["columns"]]
        await _ok(await c.put(f"/api/v1/model/{source}/graph", headers=bearer(world["member"]),
                              json={"entities": graph["entities"], "relationships": graph["relationships"]}), 200)
        after = await _ok(await c.get(f"/api/v1/mappings/{document}", headers=bearer(world["viewer"])), 200)
    row = next(r for r in after["rows"] if r["target"]["column"] == "email")
    assert row["status"] == "drift" and row["drift"] == ["source column missing: EMPLOYEES.EMAIL"]
    assert row["entry"] is not None  # flagged, never dropped
    assert after["completeness"]["in_drift"] == 1 and not after["completeness"]["complete"]
    assert await _count(session, "SELECT count(*) FROM mapping_entries") == len(PLAN)


async def test_control_a_proposal_cannot_be_accepted_without_a_person(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        proposed = await _ok(await c.post(f"/api/v1/mappings/{document}/proposals", headers=bearer(world["member"])),
                             200)
        proposal = next(r for r in proposed["rows"] if r["proposals"])["proposals"][0]["proposal_id"]
        url = f"/api/v1/mappings/{document}/proposals/{proposal}/accept"
        # No credentials at all.
        assert (await c.post(url)).status_code == 401
        # A body naming a decider: refused, never read.
        named = await c.post(url, headers=bearer(world["member"]),
                             json={"decided_by_user_id": str(world["admin"].user_id)})
        assert named.status_code == 422
        # An API key with MEMBER rights: the route is open to it, the decision is not.
        minted = await _ok(await c.post("/api/v1/auth/api-keys", headers=bearer(world["admin"]),
                                        json={"name": "agent", "workspace_id": str(world["ws"].workspace_id),
                                              "role_cap": "MEMBER"}), 201)
        key = {"X-API-Key": minted["api_key"]}
        by_key = await c.post(url, headers=key)
        assert by_key.status_code == 403 and "person" in by_key.text
        # Control: the same key may run the proposer, which decides nothing.
        await _ok(await c.post(f"/api/v1/mappings/{document}/proposals", headers=key), 200)
    assert await _count(session, "SELECT count(*) FROM mapping_decisions") == 0
    assert await _count(session, "SELECT count(*) FROM mapping_entries") == 0
    assert await _count(session, "SELECT count(*) FROM mapping_proposals WHERE status <> 'pending'") == 0
    # Control for the controls: the member, signed in, can accept it.
    async with real_client(session) as c:
        await _ok(await c.post(url, headers=bearer(world["member"])), 200)
    assert await _count(session, "SELECT count(*) FROM mapping_decisions WHERE decision = 'accepted'") == 1


async def test_a_viewer_cannot_decide_and_an_outsider_cannot_see(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        assert (await c.post(f"/api/v1/mappings/{document}/entries", headers=bearer(world["viewer"]),
                             json=PLAN[0])).status_code == 403
        assert (await c.get(f"/api/v1/mappings/{document}", headers=bearer(world["outsider"]))).status_code == 403
        await _ok(await c.get(f"/api/v1/mappings/{document}", headers=bearer(world["viewer"])), 200)


async def test_a_source_model_in_another_workspace_is_not_found(session, world) -> None:
    async with real_client(session) as c:
        target = await _import(c, world, TARGET_DDL, "postgres", "dim.sql")
        body = await _ok(await c.post(
            "/api/v1/import/ddl", params={"workspace_id": str(world["other"].workspace_id)},
            files={"file": ("dim.sql", TARGET_DDL, "application/sql")}, data={"dialect": "postgres"},
            headers=bearer(world["outsider"])), 201)
        refused = await c.post(f"/api/v1/model/{target}/mappings", headers=bearer(world["member"]),
                               json={"source_model_id": body["model_id"], "title": "x"})
    assert refused.status_code == 404


async def test_deleting_the_document_keeps_its_decisions(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        await _author(c, world, document, PLAN[:2])
        await _ok(await c.delete(f"/api/v1/mappings/{document}", headers=bearer(world["member"])), 204)
    assert await _count(session, "SELECT count(*) FROM mapping_documents") == 0
    assert await _count(session, "SELECT count(*) FROM mapping_entries") == 0
    assert await _count(session, "SELECT count(*) FROM mapping_decisions") == 2


async def test_an_entry_the_rules_refuse_says_why(session, world) -> None:
    async with real_client(session) as c:
        document, _, _ = await _document(c, world)
        for body, reason in (
            ({"target": _pick("dim_employee", "email"), "kind": "mapped"}, "at least one source"),
            ({"target": _pick("dim_employee", "nope"), "kind": "constant"}, "not a column"),
            ({"target": _pick("dim_employee", "email"), "kind": "mapped",
              "sources": [_pick("EMPLOYEES", "NOPE")]}, "not a column"),
        ):
            refused = await c.post(f"/api/v1/mappings/{document}/entries", headers=bearer(world["member"]), json=body)
            assert refused.status_code == 422 and reason in refused.text, refused.text
        await _author(c, world, document, [PLAN[3]])
        twice = await c.post(f"/api/v1/mappings/{document}/entries", headers=bearer(world["member"]), json=PLAN[3])
        assert twice.status_code == 422 and "already has an entry" in twice.text
