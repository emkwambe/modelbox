"""The drift report's own rules (Sprint 8 Step 5, items 1, 3-6).

No guessed renames, with the possible-rename hint only where type and
position match; the header's sources, version, time and reconciliation; the
unreconciled warning first; the verified-field flag; the three formats; the
endpoint, driven with real credentials. Each rule has a case where it could
fail beside the case where it holds.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_model import SynthesizedModel
from app.services import drift_report
from app.services.drift_report import Source
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)


def _model(columns: list[dict[str, Any]], **entity: Any) -> SynthesizedModel:
    return SynthesizedModel.model_validate({"paradigm": "3NF", "entities": [
        {"entity_name": "t", "columns": columns, "primary_key": ["id"], **entity}]})


ID = {"name": "id", "data_type": "INTEGER", "is_nullable": False}
DESIGN = Source("Design", "Orders design", "reconciled", version=7, model_id="m1")
DEPLOYED = Source("Deployed", "prod.sql", "reconciled", imported_at="2026-09-29T18:00:00+00:00", dialect="postgres")


def _build(design: SynthesizedModel, deployed: SynthesizedModel, statuses: dict | None = None,
           deployed_source: Source = DEPLOYED) -> dict[str, Any]:
    return drift_report.build(design, deployed, DESIGN, deployed_source, statuses, "postgres")


def _kinds(doc: dict[str, Any]) -> list[tuple[str, str | None]]:
    return [(d["kind"], d["column"]) for d in doc["drifts"]]


# --- no guessed renames --------------------------------------------------------


def test_a_rename_is_a_removal_and_an_addition_with_a_hint() -> None:
    doc = _build(_model([ID, {"name": "street", "data_type": "TEXT"}]),
                 _model([ID, {"name": "address_line", "data_type": "TEXT"}]))
    assert _kinds(doc) == [("column_added", "address_line"), ("column_removed", "street")]
    assert [d["class"] for d in doc["drifts"]] == ["non-breaking", "breaking"]
    assert doc["possible_renames"] == [{"table": "t", "removed": "street", "added": "address_line",
                                        "type": "TEXT", "position": 2}]
    assert doc["summary"]["total"] == 2, "a hint is never counted as a rename"


@pytest.mark.parametrize(("deployed", "why"), [
    ([ID, {"name": "address_line", "data_type": "VARCHAR(10)"}], "the type differs"),
    ([ID, {"name": "note_id", "data_type": "INTEGER"}, {"name": "address_line", "data_type": "TEXT"}],
     "the position differs"),
])
def test_negative_control_no_hint_without_type_and_position(deployed: list, why: str) -> None:
    doc = _build(_model([ID, {"name": "street", "data_type": "TEXT"}]), _model(deployed))
    assert doc["possible_renames"] == [], why


def test_column_identity_is_never_used_to_pair() -> None:
    """Two separately saved models both number their columns from 1: equal
    stable ids on different columns are not a rename."""
    design = _model([{**ID, "stable_id": 1}, {"name": "email", "data_type": "TEXT", "stable_id": 2}])
    deployed = _model([{**ID, "stable_id": 1}, {"name": "phone", "data_type": "TEXT", "stable_id": 2},
                       {"name": "email", "data_type": "TEXT", "stable_id": 3}])
    assert _kinds(_build(design, deployed)) == [("column_added", "phone")]


# --- what is compared ----------------------------------------------------------


def test_each_column_property_is_compared() -> None:
    design = _model([ID, {"name": "c", "data_type": "VARCHAR(10)", "source_data_type": "varchar(10)",
                          "is_nullable": True, "default_value": "'a'", "description": "Old."}])
    deployed = _model([ID, {"name": "c", "data_type": "VARCHAR(20)", "source_data_type": "varchar(20)",
                            "is_nullable": False, "default_value": "'b'", "source_default_value": "'b'::text",
                            "description": "New."}])
    doc = _build(design, deployed)
    assert _kinds(doc) == [("type_changed", "c"), ("nullability_changed", "c"), ("default_changed", "c"),
                           ("description_changed", "c")]
    type_drift = doc["drifts"][0]
    assert (type_drift["before"], type_drift["after"]) == ("VARCHAR(10)", "VARCHAR(20)")
    assert type_drift["detail"] == {"declared_before": "varchar(10)", "declared_after": "varchar(20)"}
    assert doc["drifts"][2]["after"] == "'b'::text", "the default in its original text"


def test_a_respelled_default_is_not_a_drift() -> None:
    design = _model([ID, {"name": "at", "data_type": "TIMESTAMP", "default_value": "CURRENT_TIMESTAMP",
                          "source_default_value": "now()"}])
    deployed = _model([ID, {"name": "at", "data_type": "TIMESTAMP", "default_value": "CURRENT_TIMESTAMP",
                            "source_default_value": "CURRENT_TIMESTAMP"}])
    assert _build(design, deployed)["drifts"] == []


def test_composite_constraints_are_compared_as_ordered_lists() -> None:
    columns = [ID, {"name": "a", "data_type": "INTEGER", "is_nullable": False},
               {"name": "b", "data_type": "INTEGER", "is_nullable": False}]
    design = _model(columns, primary_key=["id", "a"], unique_constraints=[{"columns": ["a", "b"]}])
    deployed = _model(columns, primary_key=["a", "id"], unique_constraints=[{"columns": ["b", "a"]}])
    assert [(d["kind"], d["columns"]) for d in _build(design, deployed)["drifts"]] == [
        ("primary_key_changed", ["a", "id"]), ("unique_removed", ["a", "b"]), ("unique_added", ["b", "a"])]


# --- the header ----------------------------------------------------------------


def test_the_header_names_both_sources_version_time_and_reconciliation() -> None:
    md = drift_report.to_markdown(_build(_model([ID]), _model([ID])))
    assert "- **Design:** Design: Orders design, version 7 — reconciled" in md
    assert "- **Deployed:** Deployed: prod.sql, imported 2026-09-29T18:00:00+00:00, postgres — reconciled" in md
    assert "Unreconciled import" not in md
    assert "No drift" in md


def test_an_unreconciled_import_says_so_at_the_top_of_every_format() -> None:
    unreconciled = Source("Deployed", "prod.sql", "unreconciled", imported_at="now")
    doc = _build(_model([ID]), _model([ID]), deployed_source=unreconciled)
    assert drift_report.to_markdown(doc).splitlines()[2].startswith("> **Unreconciled import.** Deployed is")
    html = drift_report.to_html(doc)
    assert html.index('role="alert"') < html.index("<strong>Design:</strong>")
    parsed = json.loads(drift_report.to_json(doc))
    assert list(parsed)[:2] == ["report", "warnings"] and parsed["warnings"]


# --- the verified flag ---------------------------------------------------------


def test_a_drift_on_a_verified_field_is_flagged() -> None:
    design = _model([ID, {"name": "c", "data_type": "VARCHAR(10)"}])
    deployed = _model([ID, {"name": "c", "data_type": "VARCHAR(5)"}])
    doc = _build(design, deployed, {("t", "c", "data_type"): "verified"})
    (drift,) = doc["drifts"]
    assert drift["flag"] == "verified field affected by drift"
    assert drift["verified_fields_affected"] == ["t.c.data_type"]
    assert doc["summary"]["verified_fields_affected"] == 1
    assert "verified field affected by drift: t.c.data_type" in drift_report.to_markdown(doc)


@pytest.mark.parametrize("status", ["pending", "recorded"])
def test_negative_control_an_unverified_field_is_not_flagged(status: str) -> None:
    doc = _build(_model([ID, {"name": "c", "data_type": "VARCHAR(10)"}]),
                 _model([ID, {"name": "c", "data_type": "VARCHAR(5)"}]), {("t", "c", "data_type"): status})
    assert doc["drifts"][0]["flag"] is None
    assert "verified field affected" not in drift_report.to_markdown(doc)


def test_a_removed_column_flags_every_verified_field_it_held() -> None:
    doc = _build(_model([ID, {"name": "c", "data_type": "TEXT"}]), _model([ID]),
                 {("t", "c", "description"): "verified", ("t", "c", "unit"): "pending",
                  ("t", "id", "data_type"): "verified"})
    assert doc["drifts"][0]["verified_fields_affected"] == ["t.c.description"]


# --- the endpoint ----------------------------------------------------------------

DESIGN_DDL = b"""
CREATE TABLE public.customer (
    customer_id integer NOT NULL,
    email character varying(255),
    CONSTRAINT customer_pkey PRIMARY KEY (customer_id)
);
"""
DEPLOYED_DDL = DESIGN_DDL.replace(b"email character varying(255),",
                                  b"email character varying(255) NOT NULL,\n    phone text,")


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    member = await make_user(session, "member@example.com")
    viewer = await make_user(session, "viewer@example.com")
    outsider = await make_user(session, "outsider@example.com")
    workspace = await make_workspace(session, "W", {member: "MEMBER", viewer: "VIEWER"})
    await make_workspace(session, "Other", {outsider: "OWNER"})
    await session.commit()
    return {"member": member, "viewer": viewer, "outsider": outsider, "ws": workspace}


async def _drift(c: AsyncClient, model: str, who: Any, fmt: str) -> Any:
    return await c.post(f"/api/v1/model/{model}/drift", headers=bearer(who),
                        files={"file": ("prod.sql", DEPLOYED_DDL, "application/sql")},
                        data={"dialect": "postgres", "format": fmt})


async def test_the_endpoint_reports_drift_in_each_format(session, world) -> None:
    async with real_client(session) as c:
        imported = await c.post("/api/v1/import/ddl", params={"workspace_id": str(world["ws"].workspace_id)},
                                files={"file": ("design.sql", DESIGN_DDL, "application/sql")},
                                data={"dialect": "postgres"}, headers=bearer(world["member"]))
        assert imported.status_code == 201, imported.text
        model = imported.json()["model_id"]
        responses = {fmt: await _drift(c, model, world["viewer"], fmt) for fmt in ("markdown", "html", "json")}
        refused = await _drift(c, model, world["outsider"], "json")
    assert {fmt: r.status_code for fmt, r in responses.items()} == {"markdown": 200, "html": 200, "json": 200}
    doc = json.loads(responses["json"].json()["files"]["drift_report.json"])
    assert [(d["kind"], d["column"], d["class"]) for d in doc["drifts"]] == [
        ("column_added", "phone", "non-breaking"), ("nullability_changed", "email", "breaking")]
    assert doc["design"]["version"] == 1 and doc["deployed"]["name"] == "prod.sql"
    assert doc["deployed"]["reconciliation"] == "reconciled" and doc["deployed"]["imported_at"]
    assert "drift_report.md" in responses["markdown"].json()["files"]
    assert "<table>" in responses["html"].json()["files"]["drift_report.html"]
    assert refused.status_code == 403
