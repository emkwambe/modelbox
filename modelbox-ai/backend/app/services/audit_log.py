"""The internal audit trail (G11) — who did what inside the appliance.

`egress_ledger` answers *what left the network*. This answers *who did what
here*, and a supervisor reviewing a remediation programme asks both. Keeping
them as two sinks rather than one table with a `kind` column is deliberate: the
egress ledger's central property is that a request cannot leave without a row,
which forces record-then-call and a fail-closed write. An audit event has no
equivalent ordering constraint — the thing being recorded has already happened
by the time we know its outcome — and merging the two would impose the stricter
discipline on events that do not need it while diluting the claim for the ones
that do.

**Three rulings, each with a plausible-looking opposite.**

*A failed audit write does not fail the action.* The action already happened;
raising would not un-happen it, and would convert a logging fault into a
user-visible failure of work that succeeded. This is the opposite of the egress
ledger's rule, and the difference is ordering: there, the write precedes the
thing and can still prevent it; here it follows and cannot. Losing a row is bad,
so the failure is logged loudly — but it is strictly better than the alternative,
which is an appliance that stops working when its audit table is full.

*The write commits in its own transaction.* A denied authorisation is usually
recorded on a request that then raises 403 and rolls back. Enlisting in the
caller's session would erase exactly the DENIED events an auditor came to read —
the audit log would record every permitted action and no refused one, which is
precisely backwards.

*The actor's email is copied, not joined.* `actor_user_id` is not a foreign key.
An audit trail has to survive the user being deleted, which is the moment
somebody most wants to read it.

**A write that fails is not silent.** It is logged at ERROR and counted, and
the count is on `/health` (`write_failure_status`), which reports `degraded`
while it is non-zero. The count is per process: the API and the worker each
report their own.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from app.models.metadata_store import AUDIT_ACTIONS, AUDIT_OUTCOMES

logger = logging.getLogger(__name__)


class _WriteFailures:
    """Audit events this process failed to write, since it started."""

    def __init__(self) -> None:
        self.count = 0
        self.last_at: datetime.datetime | None = None

    def note(self) -> None:
        self.count += 1
        self.last_at = datetime.datetime.now(datetime.UTC)


_failures = _WriteFailures()


def note_write_failure() -> None:
    """Count one failed audit write. Separate so `/health`'s test can disable it."""
    _failures.note()


def write_failure_status() -> dict[str, Any]:
    """What `/health` reports about this process's audit writes."""
    return {
        "write_failures": _failures.count,
        "last_write_failure": _failures.last_at.isoformat() if _failures.last_at else None,
    }


async def record(
    *,
    action: str,
    outcome: str = "SUCCESS",
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    workspace_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append one audit event, in its own transaction, never raising.

    ``action`` and ``outcome`` are validated against the declared vocabularies
    rather than trusted. A typo would otherwise reach the CHECK constraint,
    raise inside the write, get swallowed by the guard below, and silently drop
    the event — a caller believing it had recorded something that was never
    stored. Validating here turns that into a loud programming error in
    development while still never breaking the caller's request in production.

    ``scope`` is derived, not passed: an event with a workspace is a workspace
    event, and one without is an appliance event (a login, a SCIM change). A
    caller cannot record a workspace event that forgot its workspace.
    """
    if action not in AUDIT_ACTIONS:
        logger.error("Refusing to record unknown audit action %r", action)
        note_write_failure()
        return
    if outcome not in AUDIT_OUTCOMES:
        logger.error("Refusing to record unknown audit outcome %r", outcome)
        note_write_failure()
        return

    try:
        # Imported here, not at module scope, for the reason the egress ledger
        # defers it: this module is imported by structural tests that must not
        # pull in the async database driver. `test_audit_sink_unpatched` writes
        # a row through this path with nothing patched.
        from app.core.database import get_sessionmaker
        from app.models.metadata_store import AuditEvent

        async with get_sessionmaker()() as session:
            session.add(
                AuditEvent(
                    action=action,
                    outcome=outcome,
                    scope="appliance" if workspace_id is None else "workspace",
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    workspace_id=workspace_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    detail=detail,
                )
            )
            await session.commit()
    except Exception:
        # Deliberately broad, and deliberately not re-raised. See the module
        # docstring: the action already happened. Logged at ERROR and counted
        # for `/health`, so a sink that cannot write is visible.
        note_write_failure()
        logger.exception(
            "Failed to write audit event %s/%s for actor %s",
            action,
            outcome,
            actor_email or actor_user_id,
        )
