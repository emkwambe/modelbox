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
    ValidationIssue,
    ValidationReport,
)
from app.services.graph_engine import GraphEngine
from app.services.graph_repository import GraphRepository
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
    "\n"
    "Physical constraints. Set these where the requirements state or clearly "
    "imply them, and omit them otherwise. Every one is optional and has a safe "
    "default, so an omission costs nothing — but a guess is exported into a "
    "data contract as fact, which is worse than saying nothing:\n"
    "- is_nullable: false only when a value is genuinely mandatory. Primary "
    "keys are handled for you.\n"
    "- is_unique: true only for a natural or business key that must not "
    "repeat.\n"
    "- default_value, check_expression: only when the requirements state one.\n"
    # S5-2. These three were absent from this list while the IR accepted them,
    # so a model inventing a 0-120 age range or an email regex was obeying the
    # prompt — the instruction simply did not cover them. They are also the
    # fields that become ODCS quality terms, which makes them the worst place
    # for a silent guess: an invented rule ships as a contract the customer's
    # data is tested against.
    "- min_value, max_value: only for a range the requirements actually give. "
    "Do not infer one from the column's name or from what is physically "
    "plausible — an age is not automatically 0-120.\n"
    "- regex_pattern: only for a format the requirements state. Do not supply a "
    "conventional pattern for a name like 'email' or 'phone'; a wrong pattern "
    "rejects the customer's own valid data.\n"
    "- references: the qualified 'entity.column' that a foreign key points at.\n"
    # S5-2 again, at entity level, found by the first conformance run. The
    # gold graphs declare no tier at all, yet MISSING_SLA fired on all 5 of the
    # candidate graphs that run scored — the gold set was five at the time, and
    # this number is that run's, not a current count — which it can only do when
    # a candidate entity claims a critical
    # or important tier and gives no SLA. The model was inventing the tier. A
    # tier is a governance classification that reaches the ODCS contract and
    # the linter, so it is exactly the kind of term the omission rule exists
    # for; the instruction simply did not cover it.
    "- tier, freshness_sla (on the entity): only when the requirements state "
    "how critical the asset is or how fresh it must be. Do not infer criticality "
    "from a table's importance to the model — a tier is a governance commitment "
    "the business makes, not a property you can read off a schema, and claiming "
    "one obliges an SLA nobody agreed to.\n"
    "- agg_time_column (on the entity, not the column): the name of the date "
    "or time column this entity's measures are aggregated over. It must be one "
    "of that entity's own columns and must be a date or time type. Omit it "
    "when the entity has none — that is normal for a dimension.\n"
    "Never set stable_id; the server assigns it.\n"
    "Return ONLY the structured schema."
)


_REPAIRABLE_CODES: frozenset[str] = frozenset(
    {
        "CYCLIC_FK",
        "DANGLING_REF",
        "MISSING_PK",
        "INVALID_RANGE",
        "INVALID_REGEX",
        "PATTERN_EXCEEDS_LENGTH",
    }
)
"""The lint codes a model is asked to fix, and nothing else.

**Not "errors only", though that was the intention.** The obvious rule — feed
back `severity == "error"` — does not survive contact with the linter: exactly
two of the thirteen codes are errors, `CYCLIC_FK` and `DANGLING_REF`. Missing
primary keys and the whole invented-constraint family are *warnings*, so
severity would have excluded the most mechanically fixable defects there are
while including nothing else.

So the partition is drawn where it actually lies: **a code is repairable when a
correct answer is objectively checkable from the graph alone.** A cycle either
exists or does not. A reference either resolves or does not. A regex either fits
inside the column's length or does not.

Everything excluded is excluded because it invites invention rather than
correction:

- `MISSING_SLA` and `NAMING_CONVENTION` are the S5-2 defect's own venue. The
  first fires when an entity claims a tier and gives no SLA, so "fix it" reads
  as "supply an SLA" — a governance term the requirements never stated, going
  into a data contract as fact. That is the exact failure the system prompt
  above was rewritten to suppress; re-introducing it through a repair loop would
  be the same bug arriving by the back door.
- `MISSING_DESCRIPTION`, `MISSING_GRAIN` and `FAN_OUT_RISK` ask for prose or a
  modelling judgement, neither of which the graph can check afterwards.
- `PII_EXPOSURE` is arguably objective and is deliberately still out: asking a
  model to classify what is personal data is a governance decision a user should
  make, and a silently auto-classified column is worse than a flagged one.
- `ORPHAN_ENTITY` is frequently correct — a legitimately standalone table.

The three constraint codes are here for a reason worth stating: an invented
`0-120` age range or a wrong email pattern is repaired by *removing* it. Those
are the one family where the fix direction is subtraction, which is the safest
thing a repair pass can be asked to do.
"""

_REPAIR_PROMPT = (
    "You produced a data model that violates rules the target warehouse will "
    "enforce. Return the SAME model with ONLY those violations fixed.\n"
    "\n"
    "Rules for the repair:\n"
    "- Do not rename entities or columns that are not named below.\n"
    "- Do not add entities, columns, constraints or descriptions that the "
    "listed violations do not require. In particular, do not supply a tier, an "
    "SLA, a description, or a grain — their absence is not what you are fixing.\n"
    "- INVALID_RANGE, INVALID_REGEX and PATTERN_EXCEEDS_LENGTH are fixed by "
    "*removing* the offending constraint unless the requirements state a "
    "correct one. A constraint you cannot justify from the requirements is "
    "worse than no constraint: it is exported into a data contract as fact.\n"
    "- MISSING_PK is fixed by marking an existing identifying column as the "
    "primary key where one exists, and by adding a surrogate key only where "
    "none does.\n"
    "- DANGLING_REF is fixed either by pointing the reference at the entity "
    "that was meant, or by removing the foreign key if no such entity belongs "
    "in the model.\n"
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

    @staticmethod
    def _described_columns(model: SynthesizedModel) -> int:
        return sum(1 for e in model.entities for c in e.columns if c.description)

    async def build_graph(
        self,
        request: SynthesizeRequest,
        *,
        user_id: uuid.UUID | None = None,
        telemetry: dict[str, object] | None = None,
    ) -> tuple[SynthesizedModel, ValidationReport]:
        """Everything that produces the graph, and nothing that stores it.

        **Extracted so a harness can measure the product rather than a piece of
        it.** `run_provider_conformance` called `structured_completion` directly
        and therefore scored step one of four: no cardinality normalisation, no
        linter, no repair pass. Two shipped mechanisms aimed squarely at the
        axes that failed had never been evaluated on provider output, and the
        published numbers described a bare model with a good prompt.

        The reason it was bypassed is visible in `synthesize`'s signature: the
        rest of that method resolves a workspace and persists, so calling it
        needs a database, and a batch experiment does not want one. Splitting
        the graph-producing half out removes the excuse — these four steps need
        no session, and they are the product.

        Persistence is deliberately *not* here. It assigns ids and writes rows;
        it does not change the graph, so a measurement that stops at this
        boundary is measuring everything that could affect a score.
        """
        prompt = self._build_prompt(request)
        synthesized = await self._gateway.structured_completion(
            task="unstructured_doc_parsing",
            prompt=prompt,
            response_model=SynthesizedModel,
            system_prompt=_SYSTEM_PROMPT,
            llm_override=request.llm_override,
            user_id=user_id,
            workspace_id=request.workspace_id,
        )

        # Deterministically normalize Fact<->Dimension cardinality/direction so
        # the LLM's occasional mislabeling doesn't reach the canvas or DDL.
        synthesized.relationships = self._normalize_relationships(
            synthesized.entities, synthesized.relationships
        )

        # Validate the graph; issues do not hard-fail synthesis, because the
        # user can fix them interactively on the canvas (FR-2.3).
        report = self._graph.validate(
            synthesized.entities, synthesized.relationships
        )

        # One repair round, if the linter found something objectively wrong.
        #
        # The report used to be computed, counted into a log line, and dropped.
        # It reached the canvas for a human to fix by hand and never reached the
        # model that produced it — which is the whole of this pass: the linter
        # is *external* deterministic feedback, and that is the only kind of
        # feedback self-correction is documented to benefit from. A model asked
        # to critique itself gets worse.
        before_model, before_report = synthesized, report
        synthesized, report = await self._repair_once(
            synthesized, report, request, user_id=user_id
        )

        if telemetry is not None:
            # **Derived here rather than returned by `_repair_once`**, so its
            # signature and its twelve tests are untouched. Everything below is
            # already in scope: the pre-repair pair, and the post-repair pair
            # that is *identically* the pre-repair pair when the gate rejected —
            # which is what `repair_accepted` reads, the same identity the
            # existing tests assert on.
            #
            # This exists because the first run of the size x domain experiment
            # could not answer the question it was built for. One AML draw came
            # back with 17 findings against a typical 3 and 79 of 158 columns
            # missing descriptions, and there was no way to tell whether the
            # repair pass had done it or the draw was simply bad. Bare and
            # pipeline are independent samples, so the comparison cannot settle
            # it and no amount of re-reading the output would have.
            #
            # `described_columns` is here for that specific hypothesis. The gate
            # counts *repairable* codes only, and `MISSING_DESCRIPTION` is not
            # one — so a repair can strip half the descriptions in the model,
            # reduce a repairable code by one, and be accepted. The surface
            # check added alongside refuses lost entities and columns; it says
            # nothing about what those columns still carry.
            repairable_before = self._repairable(before_report)
            telemetry.update(
                {
                    "repair_fired": bool(repairable_before),
                    "repair_accepted": synthesized is not before_model,
                    "repairable_before": len(repairable_before),
                    "repairable_after": len(self._repairable(report)),
                    "findings_before": len(before_report.issues),
                    "findings_after": len(report.issues),
                    "codes_before": sorted(i.code for i in before_report.issues),
                    "codes_after": sorted(i.code for i in report.issues),
                    "entities_before": len(before_model.entities),
                    "entities_after": len(synthesized.entities),
                    "columns_before": sum(len(e.columns) for e in before_model.entities),
                    "columns_after": sum(len(e.columns) for e in synthesized.entities),
                    "described_columns_before": self._described_columns(before_model),
                    "described_columns_after": self._described_columns(synthesized),
                }
            )

        return synthesized, report

    async def synthesize(
        self,
        request: SynthesizeRequest,
        *,
        user_id: uuid.UUID | None = None,
    ) -> SynthesizeResponse:
        """Run synthesis end-to-end and persist the result.

        ``user_id`` is threaded to the egress ledger (D4). The ledger has
        recorded *what* left and *when* since Task 1; without an actor it
        cannot answer *who*, which is half of the question the criterion asks
        an operator to answer from the UI.

        No ``model_id`` is passed, and that is not an omission: synthesis is
        the call that brings the model into existence, so at the moment the
        request leaves there is nothing to name. Recording the id assigned
        afterwards would date the row to a model that did not exist when the
        prompt was sent.
        """
        synthesized, report = await self.build_graph(request, user_id=user_id)

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
                    grain=entity.grain,
                    tier=entity.tier,  # type: ignore[arg-type]
                    freshness_sla=entity.freshness_sla,
                    agg_time_column=entity.agg_time_column,
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
            # M1. This was `[]`, unconditionally, which is what made the
            # persisted column pointless before it existed: metrics were
            # discarded on the way out even when they had been stored.
            suggested_metrics=[
                SuggestedMetric.model_validate(m)
                for m in (model.suggested_metrics or [])
            ],
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
    def _repairable(report: ValidationReport) -> list[ValidationIssue]:
        return [i for i in report.issues if i.code in _REPAIRABLE_CODES]

    # **A severity-ordered gate was written here and backed out.** Counting
    # repairable issues treats one error as interchangeable with one warning, so
    # trading a `DANGLING_REF` for two `MISSING_PK`s scores as a regression.
    # Ordering on `(errors, warnings)` instead would accept that trade — which
    # is arguably right, since a dangling reference does not build and a missing
    # primary key does.
    #
    # It is not, however, *hardening*: it makes the gate strictly more
    # permissive, and `test_a_repair_that_trades_one_defect_for_two_is_discarded`
    # exists because someone decided the opposite on purpose. Loosening an
    # acceptance test as a side effect of closing an unrelated hole in it is the
    # move this file's own history argues against. Left as a decision, recorded
    # in `docs/BUILD_EVIDENCE_REVIEW.md`.

    @staticmethod
    def _surface(model: SynthesizedModel) -> tuple[set[str], set[tuple[str, str]]]:
        """The entity and (entity, column) names a model declares.

        Used to refuse a repair that deletes rather than repairs.
        """
        entities = {e.entity_name for e in model.entities}
        columns = {(e.entity_name, c.name) for e in model.entities for c in e.columns}
        return entities, columns

    async def _repair_once(
        self,
        synthesized: SynthesizedModel,
        report: ValidationReport,
        request: SynthesizeRequest,
        *,
        user_id: uuid.UUID | None,
    ) -> tuple[SynthesizedModel, ValidationReport]:
        """One repair attempt, kept only if it strictly improves the graph.

        **The gate is the point, not the prompt.** A repair pass with no
        acceptance test is a second chance to make the model worse, and there is
        no reason to assume a provider's second answer beats its first — the
        published result for *un*gated self-correction is that quality falls.
        So the repaired graph replaces the original only when it carries
        strictly fewer repairable issues, and the original is returned
        unchanged in every other case, including an exception.

        **One round, not a loop.** A loop needs a termination argument this has
        no evidence for, and each turn is a real provider call recorded in the
        egress ledger. Twice the egress for an unbounded gain is not a trade a
        governance product should make silently.
        """
        before = self._repairable(report)
        if not before:
            return synthesized, report

        listing = "\n".join(
            f"- [{i.code}] {i.message}"
            + (f" (entity: {i.entity_name})" if i.entity_name else "")
            + (f" (column: {i.column_name})" if i.column_name else "")
            for i in before
        )
        prompt = (
            f"{self._build_prompt(request)}\n\n"
            f"The model you produced:\n{synthesized.model_dump_json()}\n\n"
            f"Violations to fix:\n{listing}"
        )

        try:
            repaired = await self._gateway.structured_completion(
                task="unstructured_doc_parsing",
                prompt=prompt,
                response_model=SynthesizedModel,
                system_prompt=_REPAIR_PROMPT,
                llm_override=request.llm_override,
                user_id=user_id,
                workspace_id=request.workspace_id,
            )
        except Exception:
            # A failed repair is not a failed synthesis. The user still gets the
            # model they asked for, with the issues shown on the canvas exactly
            # as before this pass existed.
            logger.warning("Repair pass failed; keeping the original model.", exc_info=True)
            return synthesized, report

        repaired.relationships = self._normalize_relationships(
            repaired.entities, repaired.relationships
        )
        repaired_report = self._graph.validate(
            repaired.entities, repaired.relationships
        )
        # **Deleting the table is not repairing it.**
        #
        # `ORPHAN_ENTITY`, `CYCLIC_FK` and `MISSING_PK` are all satisfiable by
        # removing the entity that carries them, and the old gate — a count of
        # repairable issues, strictly fewer than before — accepted that. It
        # counted findings without looking at what the findings were attached
        # to, so the cheapest way to pass it was to delete the evidence. Nothing
        # here suggests a provider does that on purpose; the point is that the
        # gate could not have told us if it did, and the conformance instrument
        # has the same hole (`GraphScore.lint_delta_per_entity`).
        #
        # Additions are fine — a repair for `MISSING_PK` adds a key column. Only
        # losses are refused, so this is a subset check, not equality.
        before_entities, before_columns = self._surface(synthesized)
        after_entities, after_columns = self._surface(repaired)
        lost_entities = before_entities - after_entities
        lost_columns = before_columns - after_columns
        if lost_entities or lost_columns:
            logger.info(
                "Repair pass dropped %d entities and %d columns; keeping the "
                "original. Lost entities: %s",
                len(lost_entities),
                len(lost_columns),
                sorted(lost_entities) or "none",
            )
            return synthesized, report

        after = self._repairable(repaired_report)

        if len(after) >= len(before):
            logger.info(
                "Repair pass did not improve the graph (%d -> %d repairable "
                "issues); keeping the original.",
                len(before),
                len(after),
            )
            return synthesized, report

        logger.info(
            "Repair pass fixed %d of %d repairable issues.",
            len(before) - len(after),
            len(before),
        )
        return repaired, repaired_report

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
            # M1. Without this the metrics reached the canvas and vanished on
            # save, and `DiffEngine._semantic_breaks`' formula branch could
            # never fire through the API.
            suggested_metrics=[
                m.model_dump() for m in synthesized.suggested_metrics
            ]
            or None,
        )
        self._session.add(model)
        await self._session.flush()

        # One persistence path (Q8). The model is new, so `replace_graph` has
        # nothing to delete and reduces to a write.
        await GraphRepository(self._session).replace_graph(
            model.model_id, synthesized.entities, synthesized.relationships
        )
        return model

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
            min_value=col.min_value,
            max_value=col.max_value,
            regex_pattern=col.regex_pattern,
            ordinal_position=col.ordinal_position,
            stable_id=col.stable_id,
            is_nullable=col.is_nullable,
            is_unique=col.is_unique,
            default_value=col.default_value,
            check_expression=col.check_expression,
            references=col.reference_target,
        )
