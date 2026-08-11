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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    EntityColumn,
    EntityRelationship,
    ModelEntity,
)
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
)

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
    ) -> None:
        """Make the model's stored graph match the one provided.

        Entities are **upserted** on their natural key ``(model_id,
        entity_name)`` rather than deleted and recreated. That is what allows
        ``stable_id`` to mean anything: the per-entity high-water mark lives on
        the entity row, so deleting it on every save would re-derive column ids
        from scratch and hand out an id that a deployed Protobuf consumer still
        associates with an older field.

        It also stops churning ``EntityRelationship.from_column_id`` /
        ``to_column_id`` on every canvas save, which the previous
        delete-and-recreate did as a side effect.
        """
        await self._persist(model_id, entities, relationships)

    async def _persist(
        self,
        model_id: uuid.UUID,
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> None:
        entity_ids: dict[str, uuid.UUID] = {}
        column_ids: dict[tuple[str, str], uuid.UUID] = {}

        existing_entities = {
            row.entity_name: row
            for row in (
                await self._session.execute(
                    select(ModelEntity).where(ModelEntity.model_id == model_id)
                )
            ).scalars().all()
        }

        # Relationships are rebuilt wholesale — they carry no identity of their
        # own — but must go first, because they reference the column rows a
        # column deletion below would otherwise orphan.
        for rel_row in (
            await self._session.execute(
                select(EntityRelationship).where(
                    EntityRelationship.model_id == model_id
                )
            )
        ).scalars().all():
            await self._session.delete(rel_row)
        await self._session.flush()

        incoming = {entity.entity_name for entity in entities}
        for name, row in existing_entities.items():
            if name not in incoming:
                # A genuinely dropped entity takes its watermark with it. A
                # dropped and recreated table is a new Protobuf message, so
                # restarting its ids at 1 is correct rather than a regression.
                await self._session.delete(row)
        await self._session.flush()

        for entity in entities:
            row = existing_entities.get(entity.entity_name)
            if row is None:
                row = ModelEntity(model_id=model_id, entity_name=entity.entity_name)
                self._session.add(row)
            row.entity_type = str(entity.entity_type)
            row.canvas_position_x = entity.canvas_position_x
            row.canvas_position_y = entity.canvas_position_y
            row.description = entity.description
            row.grain = entity.grain
            row.tier = str(entity.tier) if entity.tier else None
            row.freshness_sla = entity.freshness_sla
            row.agg_time_column = entity.agg_time_column
            if row.next_stable_id is None:
                row.next_stable_id = 1
            await self._session.flush()
            entity_ids[entity.entity_name] = row.entity_id

            await self._persist_columns(row, entity)
            for col_row in await self._entity_columns(row.entity_id):
                column_ids[(entity.entity_name, col_row.column_name)] = (
                    col_row.column_id
                )

        for rel in relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, to_col = self._split_ref(rel.to_ref)
            if from_entity not in entity_ids or to_entity not in entity_ids:
                # A dangling edge is a lint finding (DANGLING_REF), not a write
                # error — the canvas must still be able to save a work in
                # progress. Log it so a silently dropped edge is traceable.
                logger.warning(
                    "Skipping relationship with unknown entity: %s -> %s",
                    rel.from_ref,
                    rel.to_ref,
                )
                continue
            self._session.add(
                EntityRelationship(
                    model_id=model_id,
                    from_entity_id=entity_ids[from_entity],
                    from_column_id=column_ids.get((from_entity, from_col)),
                    to_entity_id=entity_ids[to_entity],
                    to_column_id=column_ids.get((to_entity, to_col)),
                    cardinality=str(rel.cardinality),
                )
            )
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
            row.is_primary_key = col.is_primary_key
            row.is_foreign_key = col.is_foreign_key
            row.is_pii = col.is_pii
            row.pii_type = str(col.pii_type) if col.pii_type else None
            row.description = col.description
            row.is_metric = col.is_metric
            row.aggregation = col.aggregation
            row.min_value = col.min_value
            row.max_value = col.max_value
            row.regex_pattern = col.regex_pattern
            row.is_nullable = col.is_nullable
            row.is_unique = col.is_unique
            row.default_value = col.default_value
            row.check_expression = col.check_expression
            # One concept, three names, and all three are correct:
            #   ColumnSchema.references      the IR — the published contract
            #   entity_columns.reference_target
            #                                storage — REFERENCES is reserved SQL
            #   ODCS v3.1.0 `foreignKey`     the emitted artifact (Sprint 3, C7)
            # This assignment is the only place the IR and storage names are
            # translated. Do not "fix" the mismatch by renaming either side:
            # the column name would break Postgres, and the IR name is a
            # published contract the canvas and every export already use.
            row.reference_target = col.references
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

    @staticmethod
    def _split_ref(ref: str) -> tuple[str, str]:
        parts = ref.split(".", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")
