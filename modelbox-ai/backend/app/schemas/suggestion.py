"""Suggestions over the API (Sprint 9 Step 4).

A suggestion is shown as what it is: a guess, with the rule, its category's
anchor and the signals read, provenance ``heuristic``. There is no request
body that can set a status: accepting and rejecting are separate routes that
take the decider from the signed-in caller.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class SuggestionView(BaseModel):
    suggestion_id: uuid.UUID
    kind: Literal["pii", "agg_time_column"]
    entity: str
    column: str
    suggested: dict[str, Any]
    category: str
    category_label: str
    anchor: str
    rule_name: str
    rule_source: Literal["builtin", "client"]
    signals: dict[str, Any]
    #: A time-column candidate's rank score from written rules; never on a PII suggestion.
    confidence: float | None
    provenance: Literal["heuristic"]
    status: Literal["pending", "accepted", "rejected", "superseded"]
    #: Why it can no longer be accepted as offered (its column is gone, or no longer temporal).
    stale: str | None
    #: The field got a value by another route: it can no longer be accepted.
    resolved_elsewhere: bool
    decided_by_email: str | None
    decided_at: datetime.datetime | None


class SuggestionCounts(BaseModel):
    pending: int
    accepted: int
    rejected: int
    superseded: int
    #: "N suggestions pending review", shown apart from the dictionary's verified count.
    statement: str


class SuggestionsResponse(BaseModel):
    model_id: uuid.UUID
    counts: SuggestionCounts
    ruleset_digest: str
    suggestions: list[SuggestionView]


class RunResponse(SuggestionsResponse):
    created: int
    superseded_now: int


class DecisionRequest(BaseModel):
    """Empty, and nothing else accepted: the decider is the caller, and the
    decision is the route. A body naming a status or a person is refused."""

    model_config = ConfigDict(extra="forbid")
