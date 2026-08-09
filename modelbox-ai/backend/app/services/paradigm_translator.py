"""Paradigm translator — transforms a model between architectural paradigms.

Implements FR-3: one-click transformation between 3NF, Kimball Dimensional,
Data Vault 2.0, and OBT. The current model graph is read from the metadata
store, handed to the routed LLM with paradigm-specific synthesis strategy, and
the resulting graph is persisted as a new version of the model (FR-3.2 —
descriptions/semantics preserved across the switch).
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    DataModel,
    EntityColumn,
    EntityRelationship,
    ModelEntity,
)
from app.schemas.data_model import (
    Paradigm,
    SynthesizedModel,
    TransformParadigmRequest,
    TransformParadigmResponse,
)
from app.services.llm_gateway import LLMGateway
from app.services.synthesis_engine import SynthesisEngine

logger = logging.getLogger(__name__)

# Per-paradigm synthesis strategy injected into the transform prompt (Blueprint §4.1).
_PARADIGM_STRATEGY: dict[str, str] = {
    "3NF": (
        "Normalize entities up to 3NF/BCNF. Eliminate redundancy and derive "
        "explicit foreign-key relationships."
    ),
    "KIMBALL": (
        "Identify business processes, declare grain, then separate additive "
        "FACT tables from DIMENSION tables (model SCD Type 2 where relevant)."
    ),
    "DATA_VAULT": (
        "Decompose into HUBs (business keys), LINKs (relationships), and "
        "SATELLITEs (descriptive context). Add hash keys, load_datetime, and "
        "record_source columns to every entity."
    ),
    "OBT": (
        "Denormalize dimensions and facts into flattened, columnar-optimized "
        "One Big Table structures with nested JSON where appropriate."
    ),
}


class ParadigmTranslator:
    """Transforms a persisted model into a different modeling paradigm."""

    def __init__(self, session: AsyncSession, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway
        self._synthesis = SynthesisEngine(session, gateway)

    async def transform(
        self, model_id: uuid.UUID, request: TransformParadigmRequest
    ) -> TransformParadigmResponse | None:
        """Transform ``model_id`` into ``request.target_paradigm``."""
        started = time.perf_counter()

        model = await self._session.get(DataModel, model_id)
        if model is None:
            return None
        previous_paradigm = model.current_paradigm

        current = await self._synthesis.get_model(model_id)
        if current is None:
            return None

        prompt = self._build_prompt(current, request)
        transformed = await self._gateway.structured_completion(
            task="schema_reasoning_and_erd",
            prompt=prompt,
            response_model=SynthesizedModel,
            system_prompt=(
                "You are an expert data modeler performing a paradigm "
                "transformation. Preserve all column descriptions and semantic "
                "tags across the switch."
            ),
        )

        # Replace the model's graph with the transformed one and bump version.
        await self._replace_graph(model_id, transformed)
        model.current_paradigm = str(request.target_paradigm)
        model.version_number += 1
        await self._session.flush()

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return TransformParadigmResponse(
            model_id=model_id,
            previous_paradigm=Paradigm(previous_paradigm)
            if previous_paradigm
            else None,
            new_paradigm=request.target_paradigm,
            generated_entities_count=len(transformed.entities),
            entities=transformed.entities,
            transformation_execution_time_ms=elapsed_ms,
        )

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _build_prompt(current, request: TransformParadigmRequest) -> str:
        strategy = _PARADIGM_STRATEGY.get(str(request.target_paradigm), "")
        entity_summaries = "\n".join(
            f"- {e.entity_name} ({e.entity_type}): "
            f"{', '.join(c.name for c in e.columns)}"
            for e in current.entities
        )
        return (
            f"Transform the following model into {request.target_paradigm}.\n"
            f"Strategy: {strategy}\n"
            f"Preserve descriptions: {request.preserve_descriptions}\n"
            f"Options: {request.options.model_dump()}\n\n"
            f"Current entities:\n{entity_summaries}"
        )

    async def _replace_graph(
        self, model_id: uuid.UUID, transformed: SynthesizedModel
    ) -> None:
        """Delete the existing graph and persist the transformed one."""
        existing = (
            await self._session.execute(
                select(ModelEntity).where(ModelEntity.model_id == model_id)
            )
        ).scalars().all()
        for entity in existing:
            await self._session.delete(entity)  # cascades to columns
        rels = (
            await self._session.execute(
                select(EntityRelationship).where(
                    EntityRelationship.model_id == model_id
                )
            )
        ).scalars().all()
        for rel in rels:
            await self._session.delete(rel)
        await self._session.flush()

        # Reuse the synthesis engine's persistence for the new graph.
        await self._synthesis._persist_graph(model_id, transformed)  # noqa: SLF001
