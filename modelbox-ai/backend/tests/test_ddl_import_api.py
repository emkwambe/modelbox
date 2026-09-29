"""The DDL import API, driven with real credentials and real uploads.

Callers authenticate with real bearer tokens through the real
`get_current_user` (`tests/_real_auth.py`). What an import stores is read back
by raw SQL, not through the ORM that wrote it.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import ddl_import as endpoint
from app.models.metadata_store import AuditEvent, DataModel
from app.services.ddl_import.importer import import_ddl
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
HR = (DDL / "oracle" / "hr.sql").read_bytes()


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


async def _upload(client: AsyncClient, world: dict[str, Any], who: str, raw: bytes, dialect: str,
                  name: str = "hr.sql") -> Any:
    return await client.post(
        "/api/v1/import/ddl",
        params={"workspace_id": str(world["ws"].workspace_id)},
        files={"file": (name, raw, "application/sql")},
        data={"dialect": dialect},
        headers=bearer(world[who]),
    )


async def _stored(session: AsyncSession) -> dict[str, Any]:
    """The one model a test imported, as the database holds it."""
    rows = (await session.execute(
        text("SELECT reconciliation_status, import_report, target_dialect FROM data_models")
    )).all()
    assert len(rows) == 1, f"expected one model, found {len(rows)}"
    status, report, dialect = rows[0]
    return {"status": status, "report": report if isinstance(report, dict) else json.loads(report),
            "dialect": dialect}


async def test_a_member_imports_oracle_hr_and_it_is_stored_reconciled(session, world) -> None:
    async with real_client(session) as client:
        response = await _upload(client, world, "member", HR, "oracle")
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["entities"], body["relationships"]) == ("reconciled", 7, 10)
    stored = await _stored(session)
    assert stored["status"] == "reconciled"
    assert stored["dialect"] == "oracle"
    assert stored["report"]["reconciliation"]["gaps"] == []
    entities = (await session.execute(text("SELECT count(*) FROM model_entities"))).scalar_one()
    assert entities == 7


async def test_a_utf16_upload_imports_the_same(session, world) -> None:
    async with real_client(session) as client:
        response = await _upload(client, world, "member", HR.decode("utf-8").encode("utf-16"), "oracle")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "reconciled"
    assert response.json()["report"]["encoding"] == "UTF-16 LE with BOM"


async def test_an_import_with_gaps_is_saved_unreconciled(session, world) -> None:
    raw = (DDL / "snowflake" / "ledger_schema.sql").read_bytes()
    async with real_client(session) as client:
        response = await _upload(client, world, "member", raw, "snowflake", "ledger_schema.sql")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "unreconciled"
    stored = await _stored(session)
    assert stored["status"] == "unreconciled"
    assert stored["report"]["failures"]


@pytest.mark.parametrize("who", ["viewer", "outsider"])
async def test_only_a_member_or_above_can_import(session, world, who: str) -> None:
    async with real_client(session) as client:
        response = await _upload(client, world, who, HR, "oracle")
    assert response.status_code == 403
    assert (await session.execute(select(DataModel))).scalars().all() == []


async def test_an_unknown_dialect_is_refused(session, world) -> None:
    async with real_client(session) as client:
        response = await _upload(client, world, "member", HR, "mysql")
    assert response.status_code == 422
    assert "not importable" in response.text


async def test_a_file_over_the_limit_is_refused_before_import(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(endpoint, "MAX_UPLOAD_BYTES", 100)
    async with real_client(session) as client:
        response = await _upload(client, world, "member", HR, "oracle")
    assert response.status_code == 413
    assert (await session.execute(select(DataModel))).scalars().all() == []


async def test_an_undecodable_file_creates_no_model_and_says_why(session, world) -> None:
    async with real_client(session) as client:
        response = await _upload(client, world, "member", "CREATE TABLE t (a int); -- é".encode("latin-1"),
                                 "postgres")
    assert response.status_code == 422
    assert "neither UTF-8 nor UTF-16" in response.text
    assert (await session.execute(select(DataModel))).scalars().all() == []


async def test_the_report_downloads_as_markdown_and_json_for_a_viewer(session, world) -> None:
    async with real_client(session) as client:
        model_id = (await _upload(client, world, "member", HR, "oracle")).json()["model_id"]
        markdown = await client.get(f"/api/v1/model/{model_id}/import-report",
                                    headers=bearer(world["viewer"]))
        as_json = await client.get(f"/api/v1/model/{model_id}/import-report",
                                   params={"format": "json"}, headers=bearer(world["viewer"]))
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "- **Status:** reconciled" in markdown.text
    assert "## Gaps (0)" in markdown.text
    assert as_json.status_code == 200
    assert as_json.json() == (await _stored(session))["report"]


async def test_a_model_that_was_not_imported_has_no_report(session, world) -> None:
    model = DataModel(workspace_id=world["ws"].workspace_id, title="drawn", target_dialect="postgres")
    session.add(model)
    await session.commit()
    async with real_client(session) as client:
        response = await client.get(f"/api/v1/model/{model.model_id}/import-report",
                                    headers=bearer(world["viewer"]))
    assert response.status_code == 404


async def test_the_import_is_audited_as_a_model_created_by_ddl_import(session, world) -> None:
    async with real_client(session) as client:
        model_id = (await _upload(client, world, "member", HR, "oracle")).json()["model_id"]
    events = (await session.execute(select(AuditEvent).where(AuditEvent.action == "MODEL_CREATED"))).scalars().all()
    assert [(e.resource_id, e.detail["via"], e.detail["reconciliation"]) for e in events] == [
        (model_id, "ddl_import", "reconciled")]


async def test_the_dialect_list_carries_each_dialects_evidence(session, world) -> None:
    async with real_client(session) as client:
        response = await client.get("/api/v1/import/dialects", headers=bearer(world["viewer"]))
    assert response.status_code == 200
    evidence = {d["dialect"]: d["evidence"] for d in response.json()}
    assert evidence == {"oracle": "genuine export", "postgres": "genuine export",
                        "tsql": "genuine export", "snowflake": "documentation-derived"}


async def _source_types(session: AsyncSession) -> dict[tuple[str, str], str | None]:
    """Each stored column's original type text, read by raw SQL."""
    rows = (await session.execute(text(
        "SELECT e.entity_name, c.column_name, c.source_data_type "
        "FROM entity_columns c JOIN model_entities e ON e.entity_id = c.entity_id"
    ))).all()
    return {(entity, column): source for entity, column, source in rows}


ROUND_TRIP = [("oracle", "hr"), ("oracle", "co"), ("postgres", "pagila"), ("tsql", "adventureworks")]


@pytest.mark.parametrize(("dialect", "stem"), ROUND_TRIP, ids=[s for _, s in ROUND_TRIP])
async def test_original_type_text_survives_save_and_reload(session, world, dialect: str, stem: str) -> None:
    """The import stores each column's declared type; a canvas save of the
    reloaded model writes it back unchanged."""
    raw = (DDL / dialect / f"{stem}.sql").read_bytes()
    model = import_ddl(raw, dialect).model
    assert model is not None
    expected = {(e.entity_name, c.name): c.source_data_type for e in model.entities for c in e.columns}
    assert sum(1 for v in expected.values() if v) > 0, "fixture sanity: no column carries a source type"

    async with real_client(session) as client:
        uploaded = await _upload(client, world, "member", raw, dialect, f"{stem}.sql")
        assert uploaded.status_code == 201, uploaded.text
        model_id = uploaded.json()["model_id"]
        assert await _source_types(session) == expected

        reloaded = await client.get(f"/api/v1/model/{model_id}", headers=bearer(world["member"]))
        assert reloaded.status_code == 200, reloaded.text
        body = reloaded.json()
        assert {(e["entity_name"], c["name"]): c["source_data_type"]
                for e in body["entities"] for c in e["columns"]} == expected
        saved = await client.put(f"/api/v1/model/{model_id}/graph",
                                 json={"entities": body["entities"], "relationships": body["relationships"]},
                                 headers=bearer(world["member"]))
        assert saved.status_code == 200, saved.text
    assert await _source_types(session) == expected
