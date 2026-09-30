"""Suggestions in the store: inference kept apart, and every decision a person's.

Sprint 9 Step 4 (migration 0031). The rules live in
``app.services.suggestion_rules``; this module reads and writes the rows.

* :func:`run` stores what the rules propose, as ``pending`` with provenance
  ``heuristic``. It never writes to the model.
* :func:`accept` is a person's decision. It writes the suggested value into
  the model through ``GraphRepository.replace_graph`` with source ``person``,
  the same path as a canvas save, so the value's attestation records the
  person as its provenance and starts at ``pending``. Only an APPROVER's
  verify request (Step 4b) can make that field ``verified``. The suggestion
  itself is ``accepted``, never ``verified``.
* :func:`reject` is a person's decision too, and a rejected suggestion is not
  made again for the same column, category and rule.

Each decision writes a ``SUGGESTION_DECIDED`` audit event in the caller's
transaction, and an accept writes ``MODEL_UPDATED`` as a canvas save does. The
decider is always the authenticated caller, passed in as an ``Actor``.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import AuditEvent, DataModel, ModelSuggestion
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    SynthesizedModel,
    _is_temporal_type,
)
from app.services import attestation, suggestion_rules
from app.services.graph_repository import GraphRepository


@dataclass(frozen=True)
class Actor:
    """The person deciding: the authenticated caller, never a body field."""

    user_id: uuid.UUID
    email: str


class NotFound(LookupError):
    """A suggestion this model does not have."""


class Refused(ValueError):
    """A decision the suggestion's state does not allow."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _find(model: SynthesizedModel, entity_name: str, column_name: str) -> tuple[EntitySchema | None,
                                                                                ColumnSchema | None]:
    entity = next((e for e in model.entities if e.entity_name == entity_name), None)
    column = None if entity is None else next((c for c in entity.columns if c.name == column_name), None)
    return entity, column


@dataclass(frozen=True)
class State:
    """A suggestion as it stands against the model now (computed, never stored)."""

    row: ModelSuggestion
    stale: str | None           # why it can no longer be accepted as offered, or None
    resolved_elsewhere: bool    # the field got a value by another route


def state(model: SynthesizedModel, row: ModelSuggestion,
          ruleset: suggestion_rules.Ruleset | None = None) -> State:
    entity, column = _find(model, row.entity_name, row.column_name)
    if entity is None:
        return State(row, f"table {row.entity_name} is no longer in the model", False)
    if column is None:
        return State(row, f"column {row.entity_name}.{row.column_name} is no longer in the model", False)
    if row.column_stable_id is not None and column.stable_id is not None \
            and column.stable_id != row.column_stable_id:
        return State(row, f"{row.entity_name}.{row.column_name} is a different column from the one suggested", False)
    if row.kind == "agg_time_column":
        if not _is_temporal_type(column.data_type):
            return State(row, f"{row.column_name} is no longer a date or time column", False)
        return State(row, None, bool(entity.agg_time_column))
    rules = ruleset or suggestion_rules.active_ruleset()
    rule = next((r for r in rules.rules if r.name == row.rule_name), None)
    if rule is not None and suggestion_rules.type_family(column.data_type) not in rule.types:
        return State(row, f"{row.column_name}'s type {column.data_type} no longer fits rule {row.rule_name}", False)
    return State(row, None, column.is_pii)


async def load(session: AsyncSession, model_id: uuid.UUID) -> tuple[SynthesizedModel, list[ModelSuggestion]]:
    current = await attestation.read_model(session, model_id)
    model = current or SynthesizedModel.model_construct(entities=[], relationships=[])
    rows = (await session.execute(
        select(ModelSuggestion).where(ModelSuggestion.model_id == model_id)
        .order_by(ModelSuggestion.kind, ModelSuggestion.entity_name, ModelSuggestion.confidence.desc(),
                  ModelSuggestion.column_name, ModelSuggestion.category))).scalars().all()
    return model, list(rows)


# ---------------------------------------------------------------------------
# Running the rules
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunResult:
    created: int
    superseded: int


async def run(session: AsyncSession, model_row: DataModel,
              ruleset: suggestion_rules.Ruleset | None = None) -> RunResult:
    """Store what the rules propose; supersede pending ones whose field got a value."""
    rules = ruleset or suggestion_rules.active_ruleset()
    await lock_model(session, model_row)
    model, rows = await load(session, model_row.model_id)
    superseded = 0
    for row in rows:
        if row.status == "pending" and state(model, row).resolved_elsewhere:
            row.status = "superseded"
            superseded += 1
    pending = {(r.kind, r.entity_name, r.column_name, r.category) for r in rows if r.status == "pending"}
    rejected = {(r.kind, r.entity_name, r.column_name, r.category, r.rule_name) for r in rows
                if r.status == "rejected"}
    created = 0
    for c in suggestion_rules.suggest(model, rules):
        if (c.kind, c.entity, c.column, c.category) in pending:
            continue
        if (c.kind, c.entity, c.column, c.category, c.rule_name) in rejected:
            continue  # a person said no: not asked again
        session.add(ModelSuggestion(
            model_id=model_row.model_id, kind=c.kind, entity_name=c.entity, column_name=c.column,
            column_stable_id=c.stable_id, suggested=c.suggested, category=c.category, anchor=c.anchor,
            rule_name=c.rule_name, rule_source=c.rule_source, ruleset_digest=rules.digest, signals=c.signals,
            confidence=c.confidence, provenance="heuristic", status="pending"))
        pending.add((c.kind, c.entity, c.column, c.category))
        created += 1
    await session.flush()
    return RunResult(created, superseded)


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
def _audit(session: AsyncSession, action: str, actor: Actor, model_row: DataModel,
           detail: dict[str, object]) -> None:
    session.add(AuditEvent(action=action, outcome="SUCCESS", scope="workspace", actor_user_id=actor.user_id,
                           actor_email=actor.email, workspace_id=model_row.workspace_id, resource_type="model",
                           resource_id=str(model_row.model_id), detail=detail))


def _decided(row: ModelSuggestion, status: str, actor: Actor) -> None:
    row.status = status
    row.decided_by_user_id = actor.user_id
    row.decided_by_email = actor.email
    row.decided_at = datetime.datetime.now(datetime.UTC)


def _event(session: AsyncSession, actor: Actor, model_row: DataModel, row: ModelSuggestion, decision: str) -> None:
    """Names the suggestion, its rule and what it would set; never a data value."""
    _audit(session, "SUGGESTION_DECIDED", actor, model_row, {
        "decision": decision, "suggestion_id": str(row.suggestion_id), "kind": row.kind,
        "entity": row.entity_name, "column": row.column_name, "category": row.category, "rule": row.rule_name,
        "suggested": row.suggested})


async def lock_model(session: AsyncSession, model_row: DataModel) -> None:
    """Serialise every run and decision on one model, and re-read it under the lock.

    Without it, two requests could both read a suggestion as pending (an
    accept and a reject), and the record would end up contradicting the model;
    or two runs could insert the same pending suggestion and one fail on the
    unique index. ``FOR UPDATE`` holds the model's row to the end of the
    transaction (PostgreSQL; SQLite, which serialises writers anyway, renders
    no lock), and ``populate_existing`` replaces what the session held with
    what the database holds now.
    """
    await session.execute(select(DataModel).where(DataModel.model_id == model_row.model_id)
                          .with_for_update().execution_options(populate_existing=True))


async def _pending_row(session: AsyncSession, model_row: DataModel, suggestion_id: uuid.UUID) -> ModelSuggestion:
    await lock_model(session, model_row)
    row = (await session.execute(select(ModelSuggestion).where(ModelSuggestion.suggestion_id == suggestion_id)
                                 .execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None or row.model_id != model_row.model_id:
        raise NotFound(f"suggestion {suggestion_id} not found on this model")
    if row.status != "pending":
        raise Refused(f"suggestion {suggestion_id} is {row.status}; only a pending suggestion can be decided")
    return row


def _applied(entity: EntitySchema, row: ModelSuggestion) -> EntitySchema:
    """The entity with the suggestion's value written in."""
    if row.kind == "agg_time_column":
        return entity.model_copy(update={"agg_time_column": row.column_name})
    columns = [c.model_copy(update={"is_pii": True, "pii_type": row.suggested.get("pii_type")})
               if c.name == row.column_name else c for c in entity.columns]
    return entity.model_copy(update={"columns": columns})


async def accept(session: AsyncSession, model_row: DataModel, suggestion_id: uuid.UUID, actor: Actor) -> None:
    row = await _pending_row(session, model_row, suggestion_id)
    model, rows = await load(session, model_row.model_id)
    now = state(model, row)
    if now.stale:
        raise Refused(f"suggestion {suggestion_id} cannot be accepted: {now.stale}")
    if now.resolved_elsewhere:
        raise Refused(f"suggestion {suggestion_id} cannot be accepted: the field already holds a value")
    entities = [_applied(e, row) if e.entity_name == row.entity_name else e for e in model.entities]
    await GraphRepository(session).replace_graph(
        model_row.model_id, entities, list(model.relationships), source="person",
        actor=attestation.Actor(actor.user_id, actor.email))
    model_row.version_number += 1
    _decided(row, "accepted", actor)
    # One time column per entity, one PII type per column: the others offered
    # for the same field are no longer open.
    for other in rows:
        if other.suggestion_id != row.suggestion_id and other.status == "pending" and other.kind == row.kind \
                and other.entity_name == row.entity_name \
                and (row.kind == "agg_time_column" or other.column_name == row.column_name):
            other.status = "superseded"
    _event(session, actor, model_row, row, "accepted")
    _audit(session, "MODEL_UPDATED", actor, model_row,
           {"fields": ["graph"], "version": model_row.version_number, "suggestion_id": str(row.suggestion_id)})
    await session.flush()


async def reject(session: AsyncSession, model_row: DataModel, suggestion_id: uuid.UUID, actor: Actor) -> None:
    row = await _pending_row(session, model_row, suggestion_id)
    _decided(row, "rejected", actor)
    _event(session, actor, model_row, row, "rejected")
    await session.flush()
