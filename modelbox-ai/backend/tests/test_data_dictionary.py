"""The data dictionary exporter and endpoint (Pick 2; rebuilt in Sprint 8 Step 4a)."""

from __future__ import annotations

import json
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
from app.services.exporter_service import ExporterError, ExporterService
from app.services.synthesis_engine import SynthesisEngine
from tests._test_db import make_test_engine


def _col(
    name: str,
    dtype: str,
    *,
    pk: bool = False,
    fk: bool = False,
    pii: bool = False,
    ptype: str | None = None,
    desc: str | None = None,
) -> ColumnSchema:
    return ColumnSchema(
        name=name,
        data_type=dtype,
        is_primary_key=pk,
        is_foreign_key=fk,
        is_pii=pii,
        pii_type=ptype,  # type: ignore[arg-type]
        description=desc,
    )


def _model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="dim_customer",
                entity_type="DIMENSION",  # type: ignore[arg-type]
                description="One row per customer.",
                columns=[
                    _col("customer_sk", "INTEGER", pk=True, desc="Surrogate key."),
                    _col("email", "VARCHAR(255)", pii=True, ptype="EMAIL"),
                ],
            ),
            EntitySchema(
                entity_name="fact_orders",
                entity_type="FACT",  # type: ignore[arg-type]
                grain="One row per order.",
                columns=[
                    _col("order_id", "INTEGER", pk=True),
                    _col("customer_sk", "INTEGER", fk=True),
                    _col("total", "NUMERIC(12,2)"),
                ],
            ),
        ],
        relationships=[
            RelationshipSchema.model_validate(
                {"from": "fact_orders.customer_sk", "to": "dim_customer.customer_sk",
                 "cardinality": "N:1"}
            )
        ],
    )


# R2_DICTIONARY_STTM_FIELDS.md, R2-2, the fields the model holds, in its order
# (Sprint 8 Step 4a; owner decisions of 2026-09-29).
R2_ORDER = ["name", "position", "data_type", "declared_type", "nullable", "default", "primary_key",
            "unique", "foreign_key", "check", "description", "pii", "validation_rules"]
LEFT_OUT = ["business name", "owner", "critical data element", "permissible", "review status",
            "classification", "glossary"]


def _export(fmt: str, model: SynthesizedModel | None = None, reconciliation: str | None = None) -> dict[str, str]:
    return ExporterService().export_data_dictionary(model or _model(), fmt, "Sales", reconciliation)


def _with_everything() -> SynthesizedModel:
    """Composite UNIQUE, a CHECK over two columns, rules, an unresolved relationship."""
    return SynthesizedModel.model_validate({
        "paradigm": "3NF",
        "entities": [
            {"entity_name": "orders", "columns": [
                {"name": "order_id", "data_type": "INTEGER"},
                {"name": "region", "data_type": "VARCHAR(8)", "source_data_type": "varchar2(8 char)",
                 "default_value": "'EU'", "source_default_value": "'EU' /* home */"},
                {"name": "qty", "data_type": "INTEGER", "min_value": 0, "max_value": 99},
                {"name": "cap", "data_type": "INTEGER"}],
             "primary_key": ["order_id"],
             "unique_constraints": [{"columns": ["order_id", "region"]}],
             "check_constraints": [{"expression": "qty <= cap", "columns": ["qty", "cap"]}]},
            {"entity_name": "note", "columns": [{"name": "note_id", "data_type": "INTEGER"}],
             "primary_key": ["note_id"]},
        ],
        "relationships": [{"from": "note", "to": "orders", "cardinality": "N:1"}],
    })


def test_the_fields_are_in_r2_order_and_nothing_unstored_is_shown() -> None:
    doc = json.loads(_export("json")["data_dictionary.json"])
    assert list(doc["entities"][0]["columns"][0]) == R2_ORDER
    header = next(line for line in _export("markdown")["data_dictionary.md"].splitlines()
                  if line.startswith("| Column"))
    assert header == ("| Column | Position | Type | Declared type | Nullable | Default | Primary key | Unique "
                      "| Foreign key | Check | Description | PII (as recorded) | Validation rules (as recorded) |")
    for fmt, name in (("markdown", "data_dictionary.md"), ("html", "data_dictionary.html"),
                      ("json", "data_dictionary.json")):
        text = _export(fmt, _with_everything())[name].lower()
        assert [word for word in LEFT_OUT if word in text] == [], fmt


def test_nothing_in_any_format_says_verified() -> None:
    for fmt in ("markdown", "html", "json", "csv"):
        for reconciliation in ("reconciled", "unreconciled", None):
            for content in _export(fmt, _with_everything(), reconciliation).values():
                assert "verif" not in content.lower(), (fmt, reconciliation)


def test_each_field_reads_what_the_model_holds() -> None:
    doc = json.loads(_export("json", _with_everything())["data_dictionary.json"])
    orders = {c["name"]: c for c in doc["entities"][0]["columns"]}
    assert orders["order_id"]["primary_key"] == 1 and orders["order_id"]["unique"] == [["order_id", "region"]]
    assert orders["region"]["declared_type"] == "varchar2(8 char)"
    assert orders["region"]["default"] == "'EU' /* home */", "the default in its original text"
    assert orders["region"]["nullable"] is True and orders["order_id"]["nullable"] is False
    assert orders["qty"]["check"] == ["qty <= cap"] == orders["cap"]["check"]
    assert orders["qty"]["validation_rules"] == {"min": 0.0, "max": 99.0}
    email = next(c for e in json.loads(_export("json")["data_dictionary.json"])["entities"]
                 for c in e["columns"] if c["name"] == "email")
    assert email["pii"] == "EMAIL"
    fact = next(e for e in json.loads(_export("json")["data_dictionary.json"])["entities"]
                if e["name"] == "fact_orders")
    assert next(c for c in fact["columns"] if c["name"] == "customer_sk")["foreign_key"] == [
        "dim_customer.customer_sk"]


def test_relationships_list_their_pairs_and_name_the_unresolved() -> None:
    md = _export("markdown", _with_everything())["data_dictionary.md"]
    assert "| note | orders | UNRESOLVED: columns not chosen | N:1 |" in md
    resolved = _export("markdown")["data_dictionary.md"]
    assert "| fact_orders | dim_customer | customer_sk → customer_sk | N:1 |" in resolved
    doc = json.loads(_export("json", _with_everything())["data_dictionary.json"])
    assert doc["relationships"][0]["resolved"] is False
    rows = _export("csv", _with_everything())["data_dictionary_relationships.csv"].splitlines()
    assert rows[1].endswith("no: columns not chosen")


def test_an_unreconciled_source_says_so_first_in_every_format() -> None:
    md = _export("markdown", reconciliation="unreconciled")["data_dictionary.md"].splitlines()
    assert md[2].startswith("> **Unreconciled import.**")
    html = _export("html", reconciliation="unreconciled")["data_dictionary.html"]
    assert html.index('role="alert"') < html.index("<h2>")
    doc = json.loads(_export("json", reconciliation="unreconciled")["data_dictionary.json"])
    assert list(doc)[:3] == ["dataset", "generated_by", "source"] and doc["source"]["reconciliation"] == "unreconciled"
    csv_rows = _export("csv", reconciliation="unreconciled")["data_dictionary.csv"].splitlines()
    assert csv_rows[0].startswith("source_reconciliation,") and csv_rows[1].startswith("unreconciled,")


def test_negative_control_a_reconciled_source_carries_no_warning() -> None:
    md = _export("markdown", reconciliation="reconciled")["data_dictionary.md"]
    assert "Unreconciled import" not in md
    assert "- **Source:** Imported from a DDL file, and reconciled" in md
    assert "Not imported from a DDL file" in _export("markdown")["data_dictionary.md"]


def test_html_escapes_what_it_shows() -> None:
    model = _model()
    model.entities[0].description = "<b>bold</b> & more"
    html = _export("html", model)["data_dictionary.html"]
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; more" in html and "<b>bold</b>" not in html


def test_dictionary_unknown_format_raises() -> None:
    try:
        ExporterService().export_data_dictionary(_model(), "pdf", "Sales")
    except ExporterError:
        return
    raise AssertionError("expected ExporterError for unknown dictionary format")


# ---------------------------------------------------------------------------
# Endpoint
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


async def test_dictionary_endpoint(session: AsyncSession) -> None:
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

    resp = await SynthesisEngine(session, _StubGateway(_model())).synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="sales",
            target_paradigm="KIMBALL",  # type: ignore[arg-type]
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
        session, _StubGateway(_model())
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/api/v1/model/{model_id}/export/dictionary?format=json")
    app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    doc = json.loads(r.json()["files"]["data_dictionary.json"])
    # A synthesized model was not imported: the dictionary says there is no reconciliation.
    assert doc["source"]["reconciliation"] is None
