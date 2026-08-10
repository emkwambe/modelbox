"""Synthesis engine — natural language / documents -> persisted data model.

Orchestrates the full NL-to-schema pipeline (Blueprint §4.2):

    1. prompt the routed LLM for a structured :class:`SynthesizedModel`,
    2. validate the resulting graph (cycles / PKs / dangling refs),
    3. persist the model, entities, columns, and relationships,
    4. return the API response DTO.

Business logic lives here; the API handler only calls :meth:`synthesize`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    DataModel,
    EntityColumn,
    EntityRelationship,
    ModelEntity,
    Workspace,
)
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    Paradigm,
    RelationshipSchema,
    SuggestedMetric,
    SynthesizedModel,
    SynthesizeRequest,
    SynthesizeResponse,
    ValidationReport,
)
from app.services.graph_engine import GraphEngine
from app.services.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert enterprise data architect. Given business requirements, "
    "produce a rigorous data model in the requested paradigm. Identify entities, "
    "columns with precise data types, primary/foreign keys, PII flags, and "
    "relationships with cardinality.\n"
    "Cardinality rules (direction is from -> to, where 'from' holds the foreign "
    "key):\n"
    "- Kimball star schema: every Fact -> Dimension relationship MUST be "
    "MANY_TO_ONE (N:1) — the foreign key lives on the Fact and references the "
    "Dimension's surrogate primary key.\n"
    "- 3NF / normalized: use 1:1 or 1:N; model many-to-many via an explicit "
    "associative (bridge) table, not a direct N:M edge.\n"
    "Return ONLY the structured schema."
)


class SynthesisEngine:
    """Synthesizes and persists data models from unstructured input."""

    def __init__(
        self,
        session: AsyncSession,
        gateway: LLMGateway,
        graph_engine: GraphEngine | None = None,
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._graph = graph_engine or GraphEngine()

    async def synthesize(self, request: SynthesizeRequest) -> SynthesizeResponse:
        """Run synthesis end-to-end and persist the result."""
        prompt = self._build_prompt(request)
        synthesized = await self._gateway.structured_completion(
            task="unstructured_doc_parsing",
            prompt=prompt,
            response_model=SynthesizedModel,
            system_prompt=_SYSTEM_PROMPT,
            llm_override=request.llm_override,
        )

        # Deterministically normalize Fact<->Dimension cardinality/direction so
        # the LLM's occasional mislabeling doesn't reach the canvas or DDL.
        synthesized.relationships = self._normalize_relationships(
            synthesized.entities, synthesized.relationships
        )

        # Validate the graph; log issues but do not hard-fail synthesis so the
        # user can fix them interactively on the canvas (FR-2.3).
        report = self._graph.validate(
            synthesized.entities, synthesized.relationships
        )
        if not report.is_valid:
            logger.warning(
                "Synthesized model has %d validation error(s).",
                sum(1 for i in report.issues if i.severity == "error"),
            )

        workspace_id = await self._resolve_workspace(request.workspace_id)
        model = await self._persist(
            workspace_id=workspace_id,
            title=request.title or "Untitled Model",
            dialect=request.dialect,
            synthesized=synthesized,
        )

        return SynthesizeResponse(
            model_id=model.model_id,
            paradigm=synthesized.paradigm,
            entities=synthesized.entities,
            relationships=synthesized.relationships,
            suggested_metrics=synthesized.suggested_metrics,
            validation=report,
        )

    async def get_model(self, model_id: uuid.UUID) -> SynthesizeResponse | None:
        """Reconstruct a persisted model into its API response DTO."""
        model = await self._session.get(DataModel, model_id)
        if model is None:
            return None

        entities = (
            await self._session.execute(
                select(ModelEntity).where(ModelEntity.model_id == model_id)
            )
        ).scalars().all()

        entity_by_id = {e.entity_id: e for e in entities}
        column_ref: dict[uuid.UUID, str] = {}
        entity_schemas: list[EntitySchema] = []

        for entity in entities:
            columns = (
                await self._session.execute(
                    select(EntityColumn)
                    .where(EntityColumn.entity_id == entity.entity_id)
                    .order_by(EntityColumn.ordinal_position)
                )
            ).scalars().all()
            for col in columns:
                column_ref[col.column_id] = f"{entity.entity_name}.{col.column_name}"
            entity_schemas.append(
                EntitySchema(
                    entity_name=entity.entity_name,
                    entity_type=entity.entity_type,  # type: ignore[arg-type]
                    description=entity.description,
                    canvas_position_x=entity.canvas_position_x,
                    canvas_position_y=entity.canvas_position_y,
                    columns=[self._column_to_schema(c) for c in columns],
                )
            )

        rels = (
            await self._session.execute(
                select(EntityRelationship).where(
                    EntityRelationship.model_id == model_id
                )
            )
        ).scalars().all()

        rel_schemas: list[RelationshipSchema] = []
        for rel in rels:
            from_ref = column_ref.get(
                rel.from_column_id,  # type: ignore[arg-type]
                entity_by_id[rel.from_entity_id].entity_name,
            )
            to_ref = column_ref.get(
                rel.to_column_id,  # type: ignore[arg-type]
                entity_by_id[rel.to_entity_id].entity_name,
            )
            rel_schemas.append(
                RelationshipSchema.model_validate(
                    {"from": from_ref, "to": to_ref, "cardinality": rel.cardinality}
                )
            )

        report = self._graph.validate(entity_schemas, rel_schemas)
        return SynthesizeResponse(
            model_id=model.model_id,
            paradigm=model.current_paradigm or Paradigm.THREE_NF,  # type: ignore[arg-type]
            entities=entity_schemas,
            relationships=rel_schemas,
            suggested_metrics=[],
            validation=report,
        )

    async def validate_model(
        self, model_id: uuid.UUID
    ) -> ValidationReport | None:
        """Re-run graph validation on a persisted model (FR-2.3).

        Returns ``None`` if the model does not exist. Used by the canvas to
        re-check after manual edits.
        """
        response = await self.get_model(model_id)
        if response is None:
            return None
        return response.validation

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _build_prompt(request: SynthesizeRequest) -> str:
        return (
            f"Source type: {request.source_type}\n"
            f"Target paradigm: {request.target_paradigm}\n"
            f"Target SQL dialect: {request.dialect}\n\n"
            f"Business requirements:\n{request.content}"
        )

    async def _resolve_workspace(
        self, workspace_id: uuid.UUID | None
    ) -> uuid.UUID:
        """Return the given workspace, or create/find a default one."""
        if workspace_id is not None:
            return workspace_id
        existing = (
            await self._session.execute(
                select(Workspace).where(Workspace.name == "Default").limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.workspace_id
        workspace = Workspace(name="Default")
        self._session.add(workspace)
        await self._session.flush()
        return workspace.workspace_id

    async def _persist(
        self,
        *,
        workspace_id: uuid.UUID,
        title: str,
        dialect: str,
        synthesized: SynthesizedModel,
    ) -> DataModel:
        """Persist a synthesized model graph and return the DataModel row."""
        model = DataModel(
            workspace_id=workspace_id,
            title=title,
            current_paradigm=str(synthesized.paradigm),
            target_dialect=dialect,
        )
        self._session.add(model)
        await self._session.flush()

        await self._persist_graph(model.model_id, synthesized)
        return model

    async def _persist_graph(
        self, model_id: uuid.UUID, synthesized: SynthesizedModel
    ) -> None:
        """Persist entities, columns, and relationships for a model."""
        entity_ids: dict[str, uuid.UUID] = {}
        column_ids: dict[tuple[str, str], uuid.UUID] = {}

        for entity in synthesized.entities:
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

        for rel in synthesized.relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, to_col = self._split_ref(rel.to_ref)
            if from_entity not in entity_ids or to_entity not in entity_ids:
                logger.warning("Skipping relationship with unknown entity: %s", rel)
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

    @staticmethod
    def _normalize_relationships(
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> list[RelationshipSchema]:
        """Enforce Kimball Fact->Dimension relationships as N:1.

        The foreign key belongs on the Fact and points at the Dimension's
        surrogate key, so the edge direction is Fact (from) -> Dimension (to)
        with cardinality N:1. A Dimension->Fact edge is flipped to keep the
        FK path deterministic. Non Fact/Dimension pairs are left untouched.
        """
        type_by_name = {e.entity_name: str(e.entity_type) for e in entities}
        normalized: list[RelationshipSchema] = []

        for rel in relationships:
            from_entity, _ = SynthesisEngine._split_ref(rel.from_ref)
            to_entity, _ = SynthesisEngine._split_ref(rel.to_ref)
            from_type = type_by_name.get(from_entity)
            to_type = type_by_name.get(to_entity)

            if from_type == "FACT" and to_type == "DIMENSION":
                normalized.append(
                    RelationshipSchema.model_validate(
                        {
                            "from": rel.from_ref,
                            "to": rel.to_ref,
                            "cardinality": "N:1",
                        }
                    )
                )
            elif from_type == "DIMENSION" and to_type == "FACT":
                # Flip so the Fact (FK holder) is the source.
                normalized.append(
                    RelationshipSchema.model_validate(
                        {
                            "from": rel.to_ref,
                            "to": rel.from_ref,
                            "cardinality": "N:1",
                        }
                    )
                )
            else:
                normalized.append(rel)

        return normalized

    @staticmethod
    def _column_to_schema(col: EntityColumn) -> ColumnSchema:
        return ColumnSchema(
            name=col.column_name,
            data_type=col.data_type,
            is_primary_key=col.is_primary_key,
            is_foreign_key=col.is_foreign_key,
            is_pii=col.is_pii,
            pii_type=col.pii_type,  # type: ignore[arg-type]
            description=col.description,
            is_metric=col.is_metric,
            aggregation=col.aggregation,
            ordinal_position=col.ordinal_position,
        )
