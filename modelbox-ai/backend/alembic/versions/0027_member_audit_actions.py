"""MEMBER_ROLE_CHANGED and MEMBER_REMOVED return to the audit vocabulary.

Sprint 8 Step 6 (owner decision). 0021 removed both because no code path
emitted them; the workspace members API now does, beside MEMBER_ADDED, and
the coverage test drives all three through their real paths.

Additive: the action CHECK is widened, nothing else changes. The downgrade
keeps the wider CHECK, as 0026's does and for its reason: audit rows are never
deleted, and a row naming one of these actions would make the narrower CHECK
fail. The previous release never writes them.

Revision ID: 0027_member_audit_actions
Revises: 0026_dictionary_fields
"""

from __future__ import annotations

from alembic import op

revision: str = "0027_member_audit_actions"
down_revision: str | None = "0026_dictionary_fields"
branch_labels: str | None = None
depends_on: str | None = None

_BEFORE = (
    "AUTH_LOGIN", "AUTH_LOGIN_FAILED", "API_KEY_CREATED", "API_KEY_REVOKED", "MEMBER_ADDED",
    "MODEL_CREATED", "MODEL_UPDATED", "MODEL_DELETED", "MODEL_APPROVED", "USER_PROVISIONED",
    "USER_DEPROVISIONED", "ARTIFACT_GENERATED", "APPLIANCE_OWNER_DESIGNATED", "FIELD_STATUS_CHANGED",
    "CLASSIFICATION_CHANGED",
)
_AFTER = (*_BEFORE, "MEMBER_ROLE_CHANGED", "MEMBER_REMOVED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint("ck_audit_event_action", "audit_event", _in("action", _AFTER))


def downgrade() -> None:
    # The action CHECK stays as 0027 left it: see the module docstring.
    pass
