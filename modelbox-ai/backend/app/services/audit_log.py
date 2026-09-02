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
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.models.metadata_store import AUDIT_ACTIONS, AUDIT_OUTCOMES

logger = logging.getLogger(__name__)


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
    """
    if action not in AUDIT_ACTIONS:
        logger.error("Refusing to record unknown audit action %r", action)
        return
    if outcome not in AUDIT_OUTCOMES:
        logger.error("Refusing to record unknown audit outcome %r", outcome)
        return

    try:
        # Imported here, not at module scope, for the reason the egress ledger
        # defers it: this module is imported by structural tests that must not
        # pull in the async database driver.
        from app.core.database import AsyncSessionLocal
        from app.models.metadata_store import AuditEvent

        async with AsyncSessionLocal() as session:
            session.add(
                AuditEvent(
                    action=action,
                    outcome=outcome,
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    workspace_id=workspace_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    detail=detail,
                )
            )
            await session.commit()
    except Exception:  # pragma: no cover - defensive, asserted by test
        # Deliberately broad, and deliberately not re-raised. See the module
        # docstring: the action already happened.
        logger.exception(
            "Failed to write audit event %s/%s for actor %s",
            action,
            outcome,
            actor_email or actor_user_id,
        )
