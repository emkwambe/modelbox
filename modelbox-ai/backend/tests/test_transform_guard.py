"""transform-paradigm refuses an approved version, and a result that fails lint.

Two guards, both before the stored graph is touched:

* **Approved.** A `MODEL_APPROVED` event at the model's current version (one
  definition: `app.services.approval.is_current_version_approved`) refuses the
  transform with 409, before the provider is called.
* **Lint.** A transformed graph with linter errors (`CYCLIC_FK`,
  `DANGLING_REF`) is refused with 422, and the model keeps the graph it had.

Callers authenticate with real tokens. The approval is recorded through the
real `/approve` route rather than written by hand, so the test exercises the
same rows the guard reads.

Negative controls patch exactly what the fix introduced: the translator's
`is_current_version_approved`, and the translator's `GraphEngine` call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_llm_gateway
from app.models.metadata_store import AuditEvent, DataModel
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
    ValidationReport,
)
from app.services import paradigm_translator
from app.services.approval import is_current_version_approved
from tests._real_auth import (
    bearer,
    make_user,
    make_workspace,
    real_client,
    sqlite_session,
)


def _entity(name: str) -> EntitySchema:
    return EntitySchema(
        entity_name=name,
        columns=[ColumnSchema(name=f"{name}_id", data_type="INTEGER", is_primary_key=True)],
    )


CLEAN = SynthesizedModel(paradigm="DATA_VAULT", entities=[_entity("hub_customer")])
DANGLING = SynthesizedModel(
    paradigm="DATA_VAULT",
    entities=[_entity("sat_customer")],
    relationships=[
        RelationshipSchema(
            from_ref="sat_customer.sat_customer_id",
            to_ref="hub_missing.hub_missing_id",
            cardinality="N:1",
        )
    ],
)


class _Gateway:
    def __init__(self, result: SynthesizedModel) -> None:
        self.result = result
        self.calls = 0

    async def structured_completion(self, *args: Any, **kwargs: Any) -> SynthesizedModel:
        self.calls += 1
        return self.result


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> dict[str, Any]:
    member = await make_user(session, "member@example.com")
    approver = await make_user(session, "approver@example.com")
    workspace = await make_workspace(session, "W", {member: "MEMBER", approver: "APPROVER"})
    model = DataModel(workspace_id=workspace.workspace_id, title="Ledger", target_dialect="postgres")
    session.add(model)
    await session.commit()
    return {"member": member, "approver": approver, "model": model}


async def _transform(client: AsyncClient, world: dict[str, Any]):
    return await client.post(
        f"/api/v1/model/{world['model'].model_id}/transform-paradigm",
        json={"target_paradigm": "DATA_VAULT"},
        headers=bearer(world["member"]),
    )


async def _approve(client: AsyncClient, world: dict[str, Any]) -> None:
    response = await client.post(
        f"/api/v1/model/{world['model'].model_id}/approve", headers=bearer(world["approver"])
    )
    assert response.status_code == 204, response.text


async def _version(session: AsyncSession, model: DataModel) -> int:
    await session.refresh(model)
    return model.version_number


# --- Approved --------------------------------------------------------------


async def _check_approved_is_refused(session: AsyncSession, world: dict[str, Any]) -> None:
    """The check, shared by the test and its negative control."""
    gateway = _Gateway(CLEAN)
    async with real_client(session, {get_llm_gateway: lambda: gateway}) as client:
        await _approve(client, world)
        before = await _version(session, world["model"])
        response = await _transform(client, world)
    assert response.status_code == 409, response.text
    assert gateway.calls == 0, "the provider was called for a transform that cannot be saved"
    assert await _version(session, world["model"]) == before


async def test_an_approved_version_is_not_transformed(session, world) -> None:
    await _check_approved_is_refused(session, world)


async def test_an_edit_lapses_the_approval(session, world) -> None:
    """Approval covers the version signed. After an edit, transform proceeds."""
    gateway = _Gateway(CLEAN)
    async with real_client(session, {get_llm_gateway: lambda: gateway}) as client:
        await _approve(client, world)
        edited = await client.put(
            f"/api/v1/model/{world['model'].model_id}/graph",
            json={"entities": [_entity("t").model_dump()], "relationships": []},
            headers=bearer(world["member"]),
        )
        assert edited.status_code == 200, edited.text
        response = await _transform(client, world)
    assert response.status_code == 200, response.text


async def test_the_approval_function_matches_only_the_current_version(session, world) -> None:
    model = world["model"]
    assert not await is_current_version_approved(session, model)
    for version, outcome in ((model.version_number + 1, "SUCCESS"), (model.version_number, "FAILURE")):
        session.add(
            AuditEvent(
                action="MODEL_APPROVED",
                outcome=outcome,
                scope="workspace",
                workspace_id=model.workspace_id,
                resource_type="model",
                resource_id=str(model.model_id),
                detail={"version": version},
            )
        )
    await session.commit()
    assert not await is_current_version_approved(session, model), "wrong version or outcome counted"
    session.add(
        AuditEvent(
            action="MODEL_APPROVED",
            outcome="SUCCESS",
            scope="workspace",
            workspace_id=model.workspace_id,
            resource_type="model",
            resource_id=str(model.model_id),
            detail={"version": model.version_number},
        )
    )
    await session.commit()
    assert await is_current_version_approved(session, model)


# --- Lint ------------------------------------------------------------------


async def _check_lint_errors_are_refused(session: AsyncSession, world: dict[str, Any]) -> None:
    """The check, shared by the test and its negative control."""
    async with real_client(session, {get_llm_gateway: lambda: _Gateway(DANGLING)}) as client:
        before = await _version(session, world["model"])
        response = await _transform(client, world)
    assert response.status_code == 422, response.text
    codes = {error["code"] for error in response.json()["detail"]["errors"]}
    assert codes == {"DANGLING_REF"}
    assert await _version(session, world["model"]) == before, "the graph was overwritten"


async def test_a_result_with_lint_errors_does_not_replace_the_graph(session, world) -> None:
    await _check_lint_errors_are_refused(session, world)


async def test_a_clean_result_replaces_the_graph(session, world) -> None:
    """Precondition: the lint guard is not simply refusing everything."""
    async with real_client(session, {get_llm_gateway: lambda: _Gateway(CLEAN)}) as client:
        before = await _version(session, world["model"])
        response = await _transform(client, world)
    assert response.status_code == 200, response.text
    assert await _version(session, world["model"]) == before + 1


# --- Negative controls -----------------------------------------------------


async def test_negative_control_without_the_approval_check_the_check_fails(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def never_approved(_session: AsyncSession, _model: DataModel) -> bool:
        return False

    monkeypatch.setattr(paradigm_translator, "is_current_version_approved", never_approved)
    with pytest.raises(AssertionError, match="409"):
        await _check_approved_is_refused(session, world)


async def test_negative_control_without_the_lint_the_check_fails(
    session, world, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _CleanEngine:
        def validate(self, *args: Any, **kwargs: Any) -> ValidationReport:
            return ValidationReport(is_valid=True, issues=[])

    monkeypatch.setattr(paradigm_translator, "GraphEngine", _CleanEngine)
    with pytest.raises(AssertionError, match="422"):
        await _check_lint_errors_are_refused(session, world)
