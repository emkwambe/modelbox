"""ModelBox Trainer service (Pillar 3) — teaching & learning engine.

Strictly isolated from core synthesis (isolation matrix): its own system
prompts, its own tables, and deterministic grading via ``GraphEngine`` — no
cross-pollination with the synthesis routes.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    TrainerAssignment,
    TrainerSubmission,
    User,
)
from app.schemas.data_model import (
    AssignmentCreateRequest,
    GradeResponse,
    GraphUpdateRequest,
    SocraticStepRequest,
    SocraticStepResponse,
)
from app.services.graph_engine import GraphEngine
from app.services.llm_gateway import LLMGateway

# Dedicated Socratic system prompt — isolated from the synthesis prompt.
_SOCRATIC_SYSTEM_PROMPT = (
    "You are a Socratic data-modeling tutor. You NEVER produce a complete "
    "schema or write the answer for the learner. Given their current graph and "
    "the conversation so far, ask exactly ONE focused question that moves them "
    "one concrete step forward (e.g. about grain, keys, cardinality, or "
    "normalization), and offer up to three short hints. Encourage reasoning; "
    "do not reveal the full solution."
)

# Maps a required invariant name to the ValidationReport code whose ABSENCE
# satisfies it.
_INVARIANT_TO_CODE: dict[str, str] = {
    "NO_CYCLIC_FK": "CYCLIC_FK",
    "PK_PRESENT": "MISSING_PK",
    "NO_DANGLING_REF": "DANGLING_REF",
}


class TrainerService:
    """Assignment CRUD, Socratic tutoring, and deterministic grading."""

    def __init__(
        self, session: AsyncSession, gateway: LLMGateway | None = None
    ) -> None:
        self._session = session
        self._gateway = gateway

    async def create_assignment(
        self,
        user: User,
        request: AssignmentCreateRequest,
        workspace_id: uuid.UUID,
    ) -> TrainerAssignment:
        """Persist a new assignment (optionally with a flawed seed graph)."""
        assignment = TrainerAssignment(
            workspace_id=workspace_id,
            title=request.title,
            description=request.description,
            flawed_graph_json=(
                request.flawed_graph.model_dump(mode="json", by_alias=True)
                if request.flawed_graph is not None
                else None
            ),
            expected_graph_invariants=request.expected_invariants,
        )
        self._session.add(assignment)
        await self._session.flush()
        return assignment

    async def socratic_step(
        self, request: SocraticStepRequest
    ) -> SocraticStepResponse:
        """Return the tutor's next guiding question (never a full solution)."""
        if self._gateway is None:  # pragma: no cover - wired at the route
            raise RuntimeError("TrainerService.socratic_step requires a gateway")

        history = "\n".join(
            f"{turn.get('role', 'user')}: {turn.get('content', '')}"
            for turn in request.conversation_history
        )
        graph_summary = "(empty canvas)"
        if request.current_graph is not None:
            graph_summary = ", ".join(
                e.entity_name for e in request.current_graph.entities
            ) or "(no entities yet)"

        prompt = (
            f"Current entities: {graph_summary}\n"
            f"Conversation so far:\n{history or '(none)'}\n\n"
            "Ask the next single Socratic question."
        )
        return await self._gateway.structured_completion(
            task="socratic_tutoring",
            prompt=prompt,
            response_model=SocraticStepResponse,
            system_prompt=_SOCRATIC_SYSTEM_PROMPT,
        )

    async def grade(
        self,
        assignment: TrainerAssignment,
        submitted: GraphUpdateRequest,
        student: User,
    ) -> GradeResponse:
        """Grade a submission against expected invariants (FR-3.3)."""
        result = self.grade_graph(
            assignment.expected_graph_invariants or {},
            submitted,
        )
        self._session.add(
            TrainerSubmission(
                assignment_id=assignment.assignment_id,
                student_id=student.user_id,
                submitted_graph_json=submitted.model_dump(
                    mode="json", by_alias=True
                ),
                score=result.score,
                feedback_json={
                    "passed_invariants": result.passed_invariants,
                    "violations": result.violations,
                },
            )
        )
        await self._session.flush()
        return result

    @staticmethod
    def grade_graph(
        expected_invariants: dict[str, bool],
        submitted: GraphUpdateRequest,
    ) -> GradeResponse:
        """Pure scoring against deterministic GraphEngine invariants."""
        report = GraphEngine().validate(
            submitted.entities, submitted.relationships
        )
        present = {issue.code for issue in report.issues}

        required = [name for name, want in expected_invariants.items() if want]
        # Default rubric: all three structural invariants.
        known_required = [n for n in required if n in _INVARIANT_TO_CODE]
        if not known_required:
            known_required = list(_INVARIANT_TO_CODE)

        passed: list[str] = []
        violations: list[str] = []
        for invariant in known_required:
            code = _INVARIANT_TO_CODE[invariant]
            if code in present:
                violations.extend(
                    f"{issue.code}: {issue.message}"
                    for issue in report.issues
                    if issue.code == code
                )
            else:
                passed.append(invariant)

        score = round(len(passed) / len(known_required) * 100, 2)
        return GradeResponse(
            score=score, passed_invariants=passed, violations=violations
        )
