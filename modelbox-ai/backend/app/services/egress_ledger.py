"""The egress ledger sink (D3, D4).

Every outbound provider request is recorded here, from inside the gateway choke
point. The import scan in ``tests/test_egress_choke_point.py`` proves the choke
point is the only path to a provider, so ledger completeness is a structural
property rather than a claim about call sites someone has to keep checking.

Three rulings are encoded in this module, and each has a plausible-looking
opposite that would quietly break the audit trail.

**The attempt is written before the call, and a failed attempt-write blocks the
call.** "Every outbound request is recorded" is only a property if the record
cannot be missing. Writing after the call would lose every request that left
and then crashed; writing best-effort would make the ledger a success log with
an unknown number of gaps and no way to tell. So the ordering is
record-then-call, and a sink that cannot write refuses the egress. That is the
same fail-closed shape as ``allow_provider_calls``: no record, no request.

**A failed *outcome* write does not block anything, and must not.** By then the
request has already left the network — raising would neither un-send it nor
improve the record, and would convert a logging fault into a user-visible
failure of work that actually succeeded. The lone ATTEMPT row is left standing,
which states exactly what is known: we tried, and we cannot say what happened.
That is why the outcome is a separate row rather than an UPDATE.

**The write commits in its own transaction, unconnected to the caller's.**
Egress is not undone by a rollback, so the record of it must not be either. A
ledger enlisted in the caller's session would erase precisely the requests made
during work that later failed — the ones an auditor most wants to see.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# The event vocabulary, imported rather than restated. `metadata_store` imports
# only sqlalchemy, so this costs nothing that would break the deferral of
# `app.core.database` below — which is about the async driver, not the models.
from app.models.metadata_store import (
    EGRESS_ATTEMPT,
    EGRESS_EVENTS,
    EGRESS_FAILURE,
    EGRESS_SUCCESS,
)

logger = logging.getLogger(__name__)


class EgressLedgerError(RuntimeError):
    """Raised when the ledger cannot record an attempt, so it must not proceed.

    Deliberately not a subclass of ``LLMRouterError``: this is not a provider
    failing, and it must not be swallowed by the gateway's failover loop and
    retried against the next provider. An unrecordable request is unrecordable
    on every provider.
    """


def prompt_digest(prompt: str) -> str:
    """SHA-256 of the prompt text, so the ledger is not a second copy of it.

    The ledger answers *what left, when, to whom* and lets an operator prove a
    specific text was or was not sent, without becoming another store of the
    data the governance story exists to protect.

    Hashes the *user* prompt — the variable payload. The system prompt is a
    template chosen by the task, already recorded by ``task``, and identical
    across every call for that task, so including it would change every digest
    on a wording edit while proving nothing about what data was sent.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EgressAttempt:
    """What is known *before* a request leaves — all of it, and nothing later.

    Frozen because an audit record must not be revised between construction and
    write. The outcome fields are deliberately absent rather than None: they
    belong to a different row.
    """

    attempt_id: uuid.UUID
    task: str
    provider: str
    egress_class: str
    prompt_sha256: str
    prompt_chars: int
    model_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None


@runtime_checkable
class EgressLedger(Protocol):
    """The sink the choke point writes to.

    A protocol so the gateway can be exercised without a database, not so the
    ledger can be turned off. There is no null implementation and there must
    never be one: ``test_the_default_gateway_writes_to_the_database`` asserts an
    unconfigured gateway gets :class:`DatabaseEgressLedger`, which is what stops
    a test double reaching production as a silent no-op.
    """

    async def record_attempt(self, attempt: EgressAttempt) -> None:
        """Persist the ATTEMPT row. Raises :class:`EgressLedgerError` on failure."""
        ...

    async def record_outcome(
        self,
        attempt: EgressAttempt,
        *,
        event: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        """Persist the SUCCESS or FAILURE row. Never raises."""
        ...


class DatabaseEgressLedger:
    """Writes to ``egress_audit`` in a session of its own (migration 0015)."""

    async def _insert(self, **columns: Any) -> None:
        # Imported here, not at module scope: this module is imported by the
        # gateway, which must stay importable without a database driver
        # present — the same reason the engine itself is built lazily.
        from app.core.database import get_sessionmaker
        from app.models.metadata_store import EgressAudit

        if columns.get("event") not in EGRESS_EVENTS:
            # Caught here rather than at the database. The CHECK constraint
            # would reject it too, but only after the request had been made in
            # the ATTEMPT case — and the error would name a constraint rather
            # than the vocabulary.
            raise ValueError(
                f"unknown egress event {columns.get('event')!r}; "
                f"expected one of {EGRESS_EVENTS}"
            )
        async with get_sessionmaker()() as session:
            session.add(EgressAudit(**columns))
            await session.commit()

    @staticmethod
    def _columns(attempt: EgressAttempt) -> dict[str, Any]:
        return {
            "attempt_id": attempt.attempt_id,
            "task": attempt.task,
            "provider": attempt.provider,
            "egress_class": attempt.egress_class,
            "prompt_sha256": attempt.prompt_sha256,
            "prompt_chars": attempt.prompt_chars,
            "model_id": attempt.model_id,
            "user_id": attempt.user_id,
            "workspace_id": attempt.workspace_id,
        }

    async def record_attempt(self, attempt: EgressAttempt) -> None:
        try:
            await self._insert(event=EGRESS_ATTEMPT, **self._columns(attempt))
        except Exception as exc:
            # Any failure must stop the call, whatever its cause.
            # Fail closed. Letting the request proceed here is the one thing
            # that would make D3 false while every test still passed: the call
            # would succeed, the user would see nothing wrong, and the ledger
            # would be silently incomplete.
            raise EgressLedgerError(
                f"could not record an egress attempt for task '{attempt.task}' "
                f"to provider '{attempt.provider}', so the request was not "
                f"made: {exc}"
            ) from exc

    async def record_outcome(
        self,
        attempt: EgressAttempt,
        *,
        event: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        try:
            await self._insert(
                event=event,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                # The column is String(512); a provider traceback can be far
                # longer, and an oversized value would fail the insert and lose
                # the outcome row entirely.
                error=error[:512] if error else None,
                **self._columns(attempt),
            )
        except Exception:
            # The request already left. Not raised, on purpose — see the
            # module docstring: the ATTEMPT row
            # already records that this left the network, and failing the
            # caller's work over a logging fault would be a worse trade.
            logger.exception(
                "egress ledger could not record the %s outcome for attempt %s; "
                "the ATTEMPT row stands alone and the outcome is unknown",
                event,
                attempt.attempt_id,
            )


def usage_tokens(result: Any) -> tuple[int | None, int | None]:
    """Best-effort ``(prompt_tokens, completion_tokens)`` off an Instructor result.

    Returns ``(None, None)`` rather than raising when the shape is unfamiliar.
    The columns are nullable by design: recording "unknown" honestly beats
    inventing a count, and beats letting an attribute error on a usage field
    destroy a completion the user was waiting for.
    """
    try:
        usage = getattr(getattr(result, "_raw_response", None), "usage", None)
        if usage is None:
            return None, None
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        return (
            int(prompt) if prompt is not None else None,
            int(completion) if completion is not None else None,
        )
    except Exception:  # noqa: BLE001 - never let accounting break the call
        return None, None


__all__ = [
    "EGRESS_ATTEMPT",
    "EGRESS_EVENTS",
    "EGRESS_FAILURE",
    "EGRESS_SUCCESS",
    "DatabaseEgressLedger",
    "EgressAttempt",
    "EgressLedger",
    "EgressLedgerError",
    "prompt_digest",
    "usage_tokens",
]
