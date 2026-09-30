"""PII and aggregation-time suggestions (Sprint 9 Step 4).

Reading is VIEWER; running the rules and deciding is MEMBER. **A decision
needs a person**: accept and reject take the decider from the signed-in
caller and refuse an API key, which acts for an automation rather than a
person deciding, as the mapping routes do. No body can name a decider or a
status. Verifying the value an accepted suggestion wrote is a separate
request, to ``/attestations/verify``, which needs an APPROVER.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.dependencies import CurrentUserDep, SessionDep, require_model_role
from app.models.metadata_store import DataModel, User
from app.schemas.suggestion import (
    DecisionRequest,
    RunResponse,
    SuggestionCounts,
    SuggestionsResponse,
    SuggestionView,
)
from app.services import suggestion_rules
from app.services import suggestion_store as store

router = APIRouter(tags=["suggestions"])

ModelViewerDep = Annotated[DataModel, Depends(require_model_role("VIEWER"))]
ModelMemberDep = Annotated[DataModel, Depends(require_model_role("MEMBER"))]


def _person(request: Request, user: User) -> store.Actor:
    """The decider: the signed-in caller, and a person, not an API key."""
    principal = getattr(request.state, "principal", None)
    if principal is not None and principal.is_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="A suggestion is decided by a person signed in; an API key cannot decide one.")
    return store.Actor(user.user_id, user.email)


def _refused(exc: Exception) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, store.NotFound) else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


def statement(pending: int) -> str:
    return f"{pending} suggestion{'' if pending == 1 else 's'} pending review"


async def _response(session: SessionDep, model: DataModel) -> SuggestionsResponse:
    current, rows = await store.load(session, model.model_id)
    ruleset = suggestion_rules.active_ruleset()
    counts = Counter(r.status for r in rows)
    views = []
    for row in rows:
        now = store.state(current, row)
        category = ruleset.categories.get(row.category)
        views.append(SuggestionView(
            suggestion_id=row.suggestion_id, kind=row.kind, entity=row.entity_name,  # type: ignore[arg-type]
            column=row.column_name, suggested=row.suggested, category=row.category,
            category_label=("aggregation time column" if row.kind == "agg_time_column"
                            else category.label if category else row.category),
            anchor=row.anchor, rule_name=row.rule_name, rule_source=row.rule_source,  # type: ignore[arg-type]
            signals=row.signals, confidence=row.confidence, provenance="heuristic",
            status=row.status, stale=now.stale, resolved_elsewhere=now.resolved_elsewhere,  # type: ignore[arg-type]
            decided_by_email=row.decided_by_email, decided_at=row.decided_at))
    return SuggestionsResponse(
        model_id=model.model_id, ruleset_digest=ruleset.digest, suggestions=views,
        counts=SuggestionCounts(pending=counts["pending"], accepted=counts["accepted"],
                                rejected=counts["rejected"], superseded=counts["superseded"],
                                statement=statement(counts["pending"])))


@router.get("/model/{model_id}/suggestions", response_model=SuggestionsResponse,
            summary="PII and aggregation-time suggestions for this model, and what became of each")
async def list_suggestions(session: SessionDep, model: ModelViewerDep) -> SuggestionsResponse:
    return await _response(session, model)


@router.post("/model/{model_id}/suggestions", response_model=RunResponse,
             summary="Run the suggestion rules (pending until a person decides; never changes the model)")
async def run_suggestions(session: SessionDep, model: ModelMemberDep) -> RunResponse:
    result = await store.run(session, model)
    body = await _response(session, model)
    return RunResponse(**body.model_dump(), created=result.created, superseded_now=result.superseded)


@router.post("/model/{model_id}/suggestions/{suggestion_id}/accept", response_model=SuggestionsResponse,
             summary="Accept a suggestion: its value is written into the model as a person's (not verified)")
async def accept_suggestion(suggestion_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUserDep,
                            model: ModelMemberDep, payload: DecisionRequest | None = None) -> SuggestionsResponse:
    actor = _person(request, user)
    try:
        await store.accept(session, model, suggestion_id, actor)
    except (store.NotFound, store.Refused) as exc:
        raise _refused(exc) from exc
    return await _response(session, model)


@router.post("/model/{model_id}/suggestions/{suggestion_id}/reject", response_model=SuggestionsResponse,
             summary="Reject a suggestion (it is not made again for the same column and rule)")
async def reject_suggestion(suggestion_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUserDep,
                            model: ModelMemberDep, payload: DecisionRequest | None = None) -> SuggestionsResponse:
    actor = _person(request, user)
    try:
        await store.reject(session, model, suggestion_id, actor)
    except (store.NotFound, store.Refused) as exc:
        raise _refused(exc) from exc
    return await _response(session, model)
