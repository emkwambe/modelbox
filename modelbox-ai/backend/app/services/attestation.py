"""Each dictionary field's status and provenance (Sprint 8 Step 4b).

A field that holds a value has one of three statuses:

* **recorded**: nothing records where its value came from (every field of a
  model saved before 0026, and the PII values 0026 mapped across);
* **pending**: its provenance is recorded (from DDL, from a source comment,
  supplied by a named person on a date, or an AI draft) and it awaits review;
* **verified**: set by the application, and only by :func:`verify`, when all
  three conditions hold (owner decision, Sprint 8 Step 4b):

  1. the model is a reconciled import (``reconciliation_status`` is
     ``reconciled``);
  2. the field's definition, the column's or table's description, passes the
     machine-checkable ISO/IEC 11179-4 rules (``definition_rules``);
  3. its provenance is recorded, and is not an AI draft.

A verified field **lapses to pending** when its value changes, as model
approval lapses on edit. Every graph writer goes through
``GraphRepository.replace_graph``, which calls :func:`after_save`, so no path
can change a verified value and leave it verified.

Every status change is an audit event (FIELD_STATUS_CHANGED), written **in the
same transaction** as the change, so the append-only audit log is the review
history and cannot miss a change that happened. (``audit_log.record`` commits
separately so a refused request still leaves its DENIED event; a status change
that rolls back never happened, and neither should its event.) A field's
first status, when its row is created, is not a change.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    VERIFIABLE_PROVENANCE,
    AuditEvent,
    ClassificationLevel,
    ClassificationScale,
    DataModel,
    EntityColumn,
    FieldAttestation,
    ModelEntity,
)
from app.schemas.data_model import SynthesizedModel
from app.services import data_dictionary, definition_rules
from app.services.data_dictionary import FieldKey

#: Who changed the graph, and so what a changed value's provenance is.
SOURCES = ("person", "ddl_import", "introspection", "ai", "transform")


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID | None
    email: str | None


def _provenance(source: str, field_key: str) -> str | None:
    """A changed value's provenance kind, from who changed the graph."""
    if source == "person":
        return "person"
    if source in ("ddl_import", "introspection"):
        # Descriptions come from the source's own comments (COMMENT ON,
        # MS_Description); everything else from its DDL or catalog.
        return "source_comment" if field_key == "description" else "ddl"
    if source == "ai":
        return "ai_draft"
    return None  # a transform wrote it: no one supplied the value


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class _Field:
    key: FieldKey
    value: Any
    definition: str | None
    names: tuple[str | None, ...]


def fields(model: SynthesizedModel) -> dict[FieldKey, _Field]:
    """Every attested field that holds a value, with its definition."""
    out: dict[FieldKey, _Field] = {}
    for entity in model.entities:
        for f in data_dictionary.ATTESTED_TABLE_FIELDS:
            value = f.value(entity)
            if data_dictionary.holds_value(value):
                table_key: FieldKey = (entity.entity_name, None, f.key)
                out[table_key] = _Field(table_key, value, entity.description,
                                        (entity.entity_name, entity.business_name))
        for index, column in enumerate(entity.columns):
            context = data_dictionary.column_context(entity, index, column, model.relationships)
            for cf in data_dictionary.ATTESTED_COLUMN_FIELDS:
                value = cf.raw_value(context)
                if data_dictionary.holds_value(value):
                    key = (entity.entity_name, column.name, cf.key)
                    out[key] = _Field(key, value, column.description, (column.name, column.business_name))
    return out


# -- row addressing ---------------------------------------------------------
_RowKey = tuple[uuid.UUID, uuid.UUID | None, str]


async def _ids(session: AsyncSession, model_id: uuid.UUID) -> dict[tuple[str, str | None], tuple[uuid.UUID,
                                                                                                    uuid.UUID | None]]:
    """(entity name, column name or None) -> (entity id, column id)."""
    rows = (await session.execute(
        select(ModelEntity.entity_id, ModelEntity.entity_name, EntityColumn.column_id, EntityColumn.column_name)
        .outerjoin(EntityColumn, EntityColumn.entity_id == ModelEntity.entity_id)
        .where(ModelEntity.model_id == model_id))).all()
    ids: dict[tuple[str, str | None], tuple[uuid.UUID, uuid.UUID | None]] = {}
    for entity_id, entity_name, column_id, column_name in rows:
        ids[(entity_name, None)] = (entity_id, None)
        if column_id is not None:
            ids[(entity_name, column_name)] = (entity_id, column_id)
    return ids


async def _rows(session: AsyncSession, model_id: uuid.UUID) -> dict[_RowKey, FieldAttestation]:
    rows = (await session.execute(
        select(FieldAttestation).where(FieldAttestation.model_id == model_id))).scalars().all()
    return {(r.entity_id, r.column_id, r.field_key): r for r in rows}


def _event(session: AsyncSession, model: DataModel, actor: Actor | None, key: FieldKey, before: str | None,
           after: str | None, reason: str) -> None:
    """One status change, in the caller's transaction (see the module docstring).

    The detail names the field, never its value: the audit log records that
    a field changed status, not what it holds."""
    entity, column, field_key = key
    session.add(AuditEvent(
        action="FIELD_STATUS_CHANGED", outcome="SUCCESS", scope="workspace",
        actor_user_id=actor.user_id if actor else None, actor_email=actor.email if actor else None,
        workspace_id=model.workspace_id, resource_type="model", resource_id=str(model.model_id),
        detail={"entity": entity, "column": column, "field": field_key, "from": before, "to": after,
                "reason": reason},
    ))


# -- the save path ----------------------------------------------------------
@dataclass
class Snapshot:
    """What the graph held before a save: its fields, and their rows by field."""

    fields: dict[FieldKey, _Field]
    rows: dict[FieldKey, FieldAttestation]


async def read_model(session: AsyncSession, model_id: uuid.UUID) -> SynthesizedModel | None:
    """The saved graph as a SynthesizedModel (also the drift report's design side)."""
    return await _read(session, model_id)


async def _read(session: AsyncSession, model_id: uuid.UUID) -> SynthesizedModel | None:
    from app.services.synthesis_engine import SynthesisEngine

    # get_model reads the store only; the gateway is never touched.
    response = await SynthesisEngine(session, None).get_model(model_id)  # type: ignore[arg-type]
    if response is None:
        return None
    # Constructed, not validated: a model about to receive its first graph
    # has no entities, which SynthesizedModel refuses; its parts were
    # validated as they were read.
    return SynthesizedModel.model_construct(paradigm=response.paradigm, entities=response.entities,
                                            relationships=response.relationships)


async def before_save(session: AsyncSession, model_id: uuid.UUID) -> Snapshot:
    before = await _read(session, model_id)
    ids = await _ids(session, model_id)
    by_ids = {(entity_id, column_id): name for name, (entity_id, column_id) in ids.items()}
    rows: dict[FieldKey, FieldAttestation] = {}
    for (entity_id, column_id, field_key), row in (await _rows(session, model_id)).items():
        name = by_ids.get((entity_id, column_id))
        if name is not None:
            rows[(name[0], name[1], field_key)] = row
    return Snapshot(fields(before) if before else {}, rows)


async def after_save(session: AsyncSession, model_id: uuid.UUID, snapshot: Snapshot, source: str,
                     actor: Actor | None) -> None:
    """Record provenance for every value this save changed, and lapse what it changed."""
    if source not in SOURCES:
        raise ValueError(f"unknown graph source {source!r}")
    model = await session.get(DataModel, model_id)
    after = await _read(session, model_id)
    if model is None or after is None:
        return
    now = datetime.datetime.now(datetime.UTC)
    new_fields = fields(after)
    ids = await _ids(session, model_id)
    current_rows = await _rows(session, model_id)

    # Fields that no longer hold a value, or whose column or table is gone.
    for key, gone in snapshot.rows.items():
        if key in new_fields:
            continue
        _event(session, model, actor, key, gone.status, None, "the field no longer holds a value")
        if (gone.entity_id, gone.column_id, gone.field_key) in current_rows:
            await session.delete(gone)

    for key, new in new_fields.items():
        old = snapshot.fields.get(key)
        if old is not None and digest(old.value) == digest(new.value):
            continue  # unchanged: its status stands
        kind = _provenance(source, key[2])
        status = "pending" if kind else "recorded"
        found = snapshot.rows.get(key)
        before_status = found.status if found is not None else ("recorded" if old is not None else None)
        entity_id, column_id = ids[(key[0], key[1])]
        # The row as the database now holds it: a row whose column was
        # replaced went with the column.
        row = current_rows.get((entity_id, column_id, key[2]))
        if row is None:
            row = FieldAttestation(model_id=model_id, entity_id=entity_id, column_id=column_id, field_key=key[2])
            session.add(row)
        row.status = status
        row.provenance = kind
        row.provenance_by = actor.email if kind == "person" and actor else None
        row.provenance_at = now if kind else None
        row.value_digest = digest(new.value)
        row.verified_by = None
        row.verified_at = None
        row.updated_at = now
        if before_status is not None and before_status != status:
            _event(session, model, actor, key, before_status, status,
                   "the value changed" if before_status == "verified" else "a new value was supplied")
    await session.flush()


# -- reading ----------------------------------------------------------------
async def statuses(session: AsyncSession, model_id: uuid.UUID) -> dict[FieldKey, FieldAttestation]:
    """The attestation row of every field that has one, by field."""
    ids = await _ids(session, model_id)
    by_ids = {v: k for k, v in ids.items()}
    out: dict[FieldKey, FieldAttestation] = {}
    for (entity_id, column_id, field_key), row in (await _rows(session, model_id)).items():
        name = by_ids.get((entity_id, column_id))
        if name is not None:
            out[(name[0], name[1], field_key)] = row
    return out


async def levels(session: AsyncSession, workspace_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (await session.execute(
        select(ClassificationLevel.level_id, ClassificationLevel.name)
        .join(ClassificationScale, ClassificationScale.scale_id == ClassificationLevel.scale_id)
        .where(ClassificationScale.workspace_id == workspace_id))).all()
    return {level_id: name for level_id, name in rows}


def summary(counted: int, verified: int) -> dict[str, Any]:
    return {"verified": verified, "fields": counted, "pending_review": counted - verified,
            "statement": data_dictionary.verification_statement(verified, counted)}


@dataclass(frozen=True)
class Evaluation:
    key: FieldKey
    reconciled_import: bool
    definition_failures: list[str]
    provenance: str | None

    @property
    def holds(self) -> bool:
        return (self.reconciled_import and not self.definition_failures
                and self.provenance in VERIFIABLE_PROVENANCE)


def evaluate(model: DataModel, field: _Field, row: FieldAttestation | None) -> Evaluation:
    """The three conditions for one field."""
    return Evaluation(
        key=field.key,
        reconciled_import=model.reconciliation_status == "reconciled",
        definition_failures=definition_rules.check(field.definition, *field.names),
        provenance=row.provenance if row is not None else None,
    )


class UnknownField(ValueError):
    """A requested field does not exist or holds no value."""


async def verify(session: AsyncSession, model: DataModel, requested: Iterable[FieldKey] | None,
                 actor: Actor) -> list[tuple[Evaluation, FieldAttestation | None]]:
    """Set "verified" on each requested field whose three conditions hold.

    The only code that writes "verified". A field that fails a condition
    keeps its status; the result says which conditions failed.
    """
    current = await _read(session, model.model_id)
    all_fields = fields(current) if current else {}
    keys = list(requested) if requested is not None else list(all_fields)
    unknown = [k for k in keys if k not in all_fields]
    if unknown:
        raise UnknownField(f"no such field holding a value: {unknown[:5]}")
    rows = await statuses(session, model.model_id)
    now = datetime.datetime.now(datetime.UTC)
    results = []
    for key in keys:
        row = rows.get(key)
        evaluation = evaluate(model, all_fields[key], row)
        if evaluation.holds and row is not None and row.status != "verified":
            before = row.status
            row.status = "verified"
            row.verified_by = actor.email or str(actor.user_id)
            row.verified_at = now
            row.value_digest = digest(all_fields[key].value)
            row.updated_at = now
            _event(session, model, actor, key, before, "verified", "the three conditions hold")
        results.append((evaluation, row))
    await session.flush()
    return results


async def field_list(session: AsyncSession, model: DataModel) -> tuple[list[tuple[FieldKey,
                                                                                   FieldAttestation | None]],
                                                                        dict[str, Any]]:
    """Every field holding a value, with its row if it has one, and the count."""
    current = await _read(session, model.model_id)
    all_fields = fields(current) if current else {}
    rows = await statuses(session, model.model_id)
    listed = [(key, rows.get(key)) for key in all_fields]
    verified = sum(1 for _, row in listed if row is not None and row.status == "verified")
    return listed, summary(len(listed), verified)


def status_map(rows: Mapping[FieldKey, FieldAttestation]) -> dict[FieldKey, str]:
    return {key: row.status for key, row in rows.items()}


async def delete_for_model(session: AsyncSession, model_id: uuid.UUID) -> None:
    """Explicitly, for a schema (the SQLite tests) that may not cascade."""
    await session.execute(delete(FieldAttestation).where(FieldAttestation.model_id == model_id))
