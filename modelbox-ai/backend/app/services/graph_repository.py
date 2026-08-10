"""Graph persistence repository (FR-1.2).

Single home for writing an entity/relationship graph to the metadata store.
Backs ``PUT /model/{id}/graph`` (canvas edits) and is the canonical place to
persist a graph; synthesis/transform currently keep their own copies and can
delegate here in a later refactor.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    EntityColumn,
    EntityRelationship,
    ModelEntity,
)
from app.schemas.data_model import EntitySchema, RelationshipSchema


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
        """Delete the model's existing graph and persist the provided one."""
        await self._delete_existing(model_id)
        await self._persist(model_id, entities, relationships)

    async def _delete_existing(self, model_id: uuid.UUID) -> None:
        existing_entities = (
            await self._session.execute(
                select(ModelEntity).where(ModelEntity.model_id == model_id)
            )
        ).scalars().all()
        for entity in existing_entities:
            await self._session.delete(entity)  # cascades to columns
        existing_rels = (
            await self._session.execute(
                select(EntityRelationship).where(
                    EntityRelationship.model_id == model_id
                )
            )
        ).scalars().all()
        for rel in existing_rels:
            await self._session.delete(rel)
        await self._session.flush()

    async def _persist(
        self,
        model_id: uuid.UUID,
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> None:
        entity_ids: dict[str, uuid.UUID] = {}
        column_ids: dict[tuple[str, str], uuid.UUID] = {}

        for entity in entities:
            row = ModelEntity(
                model_id=model_id,
                entity_name=entity.entity_name,
                entity_type=str(entity.entity_type),
                canvas_position_x=entity.canvas_position_x,
                canvas_position_y=entity.canvas_position_y,
                description=entity.description,
            )
            self._session.add(row)
            await self._session.flush()
            entity_ids[entity.entity_name] = row.entity_id

            for position, col in enumerate(entity.columns):
                col_row = EntityColumn(
                    entity_id=row.entity_id,
                    column_name=col.name,
                    data_type=col.data_type,
                    is_primary_key=col.is_primary_key,
                    is_foreign_key=col.is_foreign_key,
                    is_pii=col.is_pii,
                    pii_type=str(col.pii_type) if col.pii_type else None,
                    description=col.description,
                    is_metric=col.is_metric,
                    aggregation=col.aggregation,
                    ordinal_position=col.ordinal_position
                    if col.ordinal_position is not None
                    else position,
                )
                self._session.add(col_row)
                await self._session.flush()
                column_ids[(entity.entity_name, col.name)] = col_row.column_id

        for rel in relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, to_col = self._split_ref(rel.to_ref)
            if from_entity not in entity_ids or to_entity not in entity_ids:
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

    @staticmethod
    def _split_ref(ref: str) -> tuple[str, str]:
        parts = ref.split(".", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")
