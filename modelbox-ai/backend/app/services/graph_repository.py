"""Graph persistence repository (FR-1.2).

**The** home for writing an entity/relationship graph to the metadata store.
Every writer goes through :meth:`GraphRepository.replace_graph`:

* ``PUT /model/{id}/graph`` — canvas edits
* ``POST /connectors/introspect`` — brownfield import
* :class:`~app.services.synthesis_engine.SynthesisEngine` — new models
* :class:`~app.services.paradigm_translator.ParadigmTranslator` — transforms

Until v1.7.0 there were three near-identical implementations of this — this one,
``SynthesisEngine._persist_graph`` and ``ParadigmTranslator._replace_graph`` —
maintained column-by-column in parallel, with nothing enforcing that they
agreed (finding Q8, register C6). They were collapsed here before the IR gained
new fields, so that each field is written in exactly one place.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    EntityColumn,
    EntityConstraint,
    EntityConstraintColumn,
    EntityRelationship,
    ModelEntity,
    RelationshipColumn,
)
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    unify_foreign_keys,
)
from app.services import attestation
from app.services.attestation import Actor

logger = logging.getLogger(__name__)

# protoc reserves 19000-19999 for its own use; a field tag in that range is
# rejected outright. Skipped at allocation so Sprint 3's emitter can use
# stable_id directly as a tag.
_PROTO_RESERVED_LO = 19000
_PROTO_RESERVED_HI = 19999


class GraphRepository:
    """Persists / replaces a model's entity-relationship graph."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_graph(
        self,
        model_id: uuid.UUID,
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
        *,
        source: str = "transform",
        actor: Actor | None = None,
    ) -> None:
        """Make the model's stored graph match the one provided.

        ``source`` says who supplied the values this save changes (a person,
        a DDL import, introspection, an AI draft, or a transform), and so what
        provenance each changed field records; ``actor`` is the person, when
        there is one. The default, a transform, records no provenance: a value
        nobody is known to have supplied is only "recorded". Every changed
        value that was verified lapses to pending (``app.services.attestation``).

        Entities are **upserted** on their natural key ``(model_id,
        entity_name)`` rather than deleted and recreated. That is what allows
        ``stable_id`` to mean anything: the per-entity high-water mark lives on
        the entity row, so deleting it on every save would re-derive column ids
        from scratch and hand out an id that a deployed Protobuf consumer still
        associates with an older field.

        Entities and relationships keep the order they are given in, so a
        model reopens as it was saved.
        """
        snapshot = await attestation.before_save(self._session, model_id)
        # Every writer's graph gets the same reading: an older-form reference
        # becomes the relationship it describes before anything is stored.
        await self._persist(model_id, entities, unify_foreign_keys(entities, relationships))
        await attestation.after_save(self._session, model_id, snapshot, source, actor)

    async def _persist(
        self,
        model_id: uuid.UUID,
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> None:
        entity_ids: dict[str, uuid.UUID] = {}

        existing_entities = {
            row.entity_name: row
            for row in (
                await self._session.execute(
                    select(ModelEntity).where(ModelEntity.model_id == model_id)
                )
            ).scalars().all()
        }

        # Relationships and constraints are rebuilt wholesale — they carry no
        # identity of their own. Child rows are deleted explicitly rather than
        # left to a database cascade the test schema may not enforce.
        relationship_ids = select(EntityRelationship.relationship_id).where(
            EntityRelationship.model_id == model_id)
        await self._session.execute(
            delete(RelationshipColumn).where(RelationshipColumn.relationship_id.in_(relationship_ids)))
        await self._session.execute(delete(EntityRelationship).where(EntityRelationship.model_id == model_id))
        constraint_ids = select(EntityConstraint.constraint_id).join(
            ModelEntity, ModelEntity.entity_id == EntityConstraint.entity_id).where(ModelEntity.model_id == model_id)
        await self._session.execute(
            delete(EntityConstraintColumn).where(EntityConstraintColumn.constraint_id.in_(constraint_ids)))
        await self._session.execute(
            delete(EntityConstraint).where(EntityConstraint.entity_id.in_(
                select(ModelEntity.entity_id).where(ModelEntity.model_id == model_id))))
        await self._session.flush()

        incoming = {entity.entity_name for entity in entities}
        for name, row in existing_entities.items():
            if name not in incoming:
                # A genuinely dropped entity takes its watermark with it. A
                # dropped and recreated table is a new Protobuf message, so
                # restarting its ids at 1 is correct rather than a regression.
                await self._session.delete(row)
        await self._session.flush()

        for entity_position, entity in enumerate(entities):
            found = existing_entities.get(entity.entity_name)
            if found is None:
                row = ModelEntity(model_id=model_id, entity_name=entity.entity_name)
                self._session.add(row)
            else:
                row = found
            row.position = entity_position
            # Values, not str(): an enum member that skipped validation would
            # store its name ('EntityType.TABLE'), which reloads as invalid.
            row.entity_type = str(getattr(entity.entity_type, "value", entity.entity_type))
            row.canvas_position_x = entity.canvas_position_x
            row.canvas_position_y = entity.canvas_position_y
            row.description = entity.description
            row.grain = entity.grain
            row.tier = str(getattr(entity.tier, "value", entity.tier)) if entity.tier else None
            row.freshness_sla = entity.freshness_sla
            row.agg_time_column = entity.agg_time_column
            row.business_name = entity.business_name
            row.business_owner = entity.business_owner
            row.it_steward = entity.it_steward
            row.authoritative_source = entity.authoritative_source
            if row.next_stable_id is None:
                row.next_stable_id = 1
            await self._session.flush()
            entity_ids[entity.entity_name] = row.entity_id

            await self._persist_columns(row, entity)
            await self._persist_constraints(row, entity)

        for rel_position, rel in enumerate(relationships):
            if rel.from_ref not in entity_ids or rel.to_ref not in entity_ids:
                # A dangling edge is a lint finding (DANGLING_REF), not a write
                # error — the canvas must still be able to save a work in
                # progress. Log it so a silently dropped edge is traceable.
                logger.warning(
                    "Skipping relationship with unknown entity: %s -> %s",
                    rel.from_ref,
                    rel.to_ref,
                )
                continue
            rel_row = EntityRelationship(
                model_id=model_id,
                from_entity_id=entity_ids[rel.from_ref],
                to_entity_id=entity_ids[rel.to_ref],
                # The value, not str(): an enum that skipped validation would
                # store its name, which the cardinality CHECK refuses.
                cardinality=str(getattr(rel.cardinality, "value", rel.cardinality)),
                name=rel.name,
                position=rel_position,
            )
            self._session.add(rel_row)
            await self._session.flush()
            self._persist_pairs(rel_row, rel)
        await self._session.flush()

    def _persist_pairs(self, rel_row: EntityRelationship, rel: RelationshipSchema) -> None:
        """A relationship's column pairs, in key order; none for an unresolved one."""
        for pair in range(max(len(rel.from_columns), len(rel.to_columns))):
            self._session.add(RelationshipColumn(
                relationship_id=rel_row.relationship_id,
                position=pair,
                from_column_name=rel.from_columns[pair] if pair < len(rel.from_columns) else None,
                to_column_name=rel.to_columns[pair] if pair < len(rel.to_columns) else None,
            ))

    async def _persist_constraints(self, entity_row: ModelEntity, entity: EntitySchema) -> None:
        """Write the entity's primary key, UNIQUE and CHECK constraints, in order."""
        rows: list[tuple[str, str | None, str | None, list[str]]] = []
        if entity.primary_key:
            rows.append(("PRIMARY KEY", None, None, entity.primary_key))
        rows += [("UNIQUE", u.name, None, u.columns) for u in entity.unique_constraints]
        rows += [("CHECK", k.name, k.expression, k.columns) for k in entity.check_constraints]
        for position, (kind, name, expression, columns) in enumerate(rows):
            constraint = EntityConstraint(entity_id=entity_row.entity_id, kind=kind, name=name,
                                          expression=expression, position=position)
            self._session.add(constraint)
            await self._session.flush()
            for member, column in enumerate(columns):
                self._session.add(EntityConstraintColumn(
                    constraint_id=constraint.constraint_id, position=member, column_name=column))
        await self._session.flush()

    # -- columns & stable identity ------------------------------------------
    async def _entity_columns(self, entity_id: uuid.UUID) -> list[EntityColumn]:
        return list(
            (
                await self._session.execute(
                    select(EntityColumn).where(EntityColumn.entity_id == entity_id)
                )
            ).scalars().all()
        )

    @staticmethod
    def _next_free_id(watermark: int) -> int:
        """Advance past the Protobuf reserved range at allocation time.

        19000–19999 are reserved by protoc, so skipping them here means the
        Sprint 3 emitter can use ``stable_id`` as a field tag with no special
        case of its own.
        """
        if _PROTO_RESERVED_LO <= watermark <= _PROTO_RESERVED_HI:
            return _PROTO_RESERVED_HI + 1
        return watermark

    async def _persist_columns(
        self, entity_row: ModelEntity, entity: EntitySchema
    ) -> None:
        """Upsert an entity's columns, allocating stable ids as needed."""
        existing = await self._entity_columns(entity_row.entity_id)
        by_name = {row.column_name: row for row in existing}
        by_stable_id = {row.stable_id: row for row in existing}
        claimed: set[int] = set()

        keep: set[uuid.UUID] = set()
        for position, col in enumerate(entity.columns):
            row = self._match_existing(col, by_name, by_stable_id, claimed)
            if row is None:
                stable_id = self._next_free_id(entity_row.next_stable_id)
                entity_row.next_stable_id = stable_id + 1
                row = EntityColumn(
                    entity_id=entity_row.entity_id, stable_id=stable_id
                )
                self._session.add(row)
            claimed.add(row.stable_id)

            row.column_name = col.name
            row.data_type = col.data_type
            row.is_pii = col.is_pii
            row.pii_type = str(getattr(col.pii_type, "value", col.pii_type)) if col.pii_type else None
            row.description = col.description
            row.is_metric = col.is_metric
            row.aggregation = col.aggregation
            row.min_value = col.min_value
            row.max_value = col.max_value
            row.regex_pattern = col.regex_pattern
            row.is_nullable = col.is_nullable
            row.default_value = col.default_value
            row.source_data_type = col.source_data_type
            row.source_default_value = col.source_default_value
            row.identity = col.identity.model_dump() if col.identity is not None else None
            row.computed_expression = col.computed_expression
            row.computed_persisted = col.computed_persisted
            row.business_name = col.business_name
            row.permissible_values = col.permissible_values
            row.unit = col.unit
            row.critical_data_element = col.critical_data_element
            row.authoritative_source = col.authoritative_source
            row.classification_level_id = col.classification_level_id
            # is_primary_key, is_unique, check_expression, is_foreign_key and
            # references are derived from the entity's constraints and the
            # model's relationships, and stored there (migration 0025).
            row.ordinal_position = (
                col.ordinal_position if col.ordinal_position is not None else position
            )
            await self._session.flush()
            keep.add(row.column_id)

        for row in existing:
            if row.column_id not in keep:
                await self._session.delete(row)
        await self._session.flush()

    @staticmethod
    def _match_existing(
        col: ColumnSchema,
        by_name: dict[str, EntityColumn],
        by_stable_id: dict[int, EntityColumn],
        claimed: set[int],
    ) -> EntityColumn | None:
        """Find the stored row this incoming column continues, if any.

        The server is authoritative: a client may echo back an id it was given,
        but may not invent one. Order matters —

        1. a live id wins, which is what makes a **rename** a rename rather
           than a drop-plus-add;
        2. then an id below the watermark that no live column holds, so
           deleting a column and undoing recovers its original tag;
        3. then the column name, for a client that never saw an id;
        4. otherwise ``None`` and the caller allocates.
        """
        supplied = col.stable_id
        if supplied is not None and supplied not in claimed:
            row = by_stable_id.get(supplied)
            if row is not None:
                return row
        match = by_name.get(col.name)
        if match is not None and match.stable_id not in claimed:
            return match
        return None
