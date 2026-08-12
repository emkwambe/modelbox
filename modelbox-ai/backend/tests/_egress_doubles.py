"""Test doubles for the egress ledger.

**Deliberately in `tests/`, not in `app/`.** An in-memory ledger living beside
the real one in the application package is one import away from being wired up
in production, where it would satisfy every structural test in
`test_egress_choke_point.py` while the audit trail evaporated at process exit.
Keeping it here means the only sink the application can reach is the database
one, which is what `test_the_default_gateway_writes_to_the_database` pins down.

Neither double is a no-op. `RecordingLedger` keeps every row so a test can
assert what *was* written rather than that nothing exploded, and `FailingLedger`
fails loudly by design.
"""

from __future__ import annotations

from app.services.egress_ledger import EgressAttempt, EgressLedgerError


class RecordingLedger:
    """Keeps rows in memory, in write order.

    Order matters to more than one assertion here: ATTEMPT preceding its
    outcome is the property that makes the ledger an audit trail rather than a
    success log, and a list preserves it where a dict keyed by attempt would
    quietly discard it.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def _append(self, attempt: EgressAttempt, event: str, **extra: object) -> None:
        self.rows.append(
            {
                "attempt_id": attempt.attempt_id,
                "event": event,
                "task": attempt.task,
                "provider": attempt.provider,
                "egress_class": attempt.egress_class,
                "prompt_sha256": attempt.prompt_sha256,
                "prompt_chars": attempt.prompt_chars,
                **extra,
            }
        )

    async def record_attempt(self, attempt: EgressAttempt) -> None:
        self._append(attempt, "ATTEMPT")

    async def record_outcome(
        self,
        attempt: EgressAttempt,
        *,
        event: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        self._append(
            attempt,
            event,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=error,
        )

    # -- convenience for assertions -----------------------------------------
    def events(self) -> list[str]:
        return [str(row["event"]) for row in self.rows]

    def attempts(self) -> list[dict[str, object]]:
        return [row for row in self.rows if row["event"] == "ATTEMPT"]


class FailingLedger:
    """Cannot record an attempt — stands in for a database that is unreachable.

    Models the situation the fail-closed rule exists for. `record_outcome` is
    intentionally *not* made to raise here: the production ledger swallows
    outcome failures by design, so a double that raised would be asserting a
    behaviour the real sink does not have.
    """

    def __init__(self) -> None:
        self.outcome_calls = 0

    async def record_attempt(self, attempt: EgressAttempt) -> None:
        raise EgressLedgerError(
            f"ledger unavailable, refusing egress for task '{attempt.task}'"
        )

    async def record_outcome(self, attempt: EgressAttempt, **_: object) -> None:
        self.outcome_calls += 1


__all__ = ["FailingLedger", "RecordingLedger"]
