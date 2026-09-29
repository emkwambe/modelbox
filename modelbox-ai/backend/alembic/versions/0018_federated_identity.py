"""Link an external IdP subject to a local user (G8).

Sprint 6.5. RS256/OIDC token *verification* has existed since Sprint 4, with
audience and issuer pinning made mandatory in D9 — but nothing could resolve the
verified token to a person. `get_current_user` required `sub` to be a UUID
naming an existing row, and an OIDC subject is an opaque provider string, so a
correctly signed and correctly audienced token from Okta or Entra was rejected
with a 401 that looked like a signature failure. SSO was configurable and could
not work.

**Keyed on (issuer, subject), not email.** Matching on email is the obvious
implementation and it is unsafe: addresses are mutable and organisations recycle
them, so an email-keyed link eventually hands a new joiner the previous holder's
account and every workspace it belonged to. `sub` is the only identifier OIDC
promises is stable and unique within an issuer; pairing it with `iss` stops two
providers' subject spaces colliding.

**A table rather than two columns on `users`.** One person can federate from
more than one issuer, and a migration between IdPs is exactly when both are
live — a single pair of columns forces a destructive choice at the moment
continuity matters most.

`ON DELETE CASCADE` to `users`, unlike the audit tables. This is not a record of
something that happened; it is a live credential mapping, and a mapping to a
deleted user is a dangling grant.

Purely additive: a new table, nothing to backfill.

Revision ID: 0018_federated_identity
Revises: 0017_extend_roles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0018_federated_identity"
down_revision: str | None = "0017_extend_roles"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "federated_identities",
        sa.Column(
            "identity_id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.UniqueConstraint("issuer", "subject", name="uq_federated_identity"),
    )
    op.create_index(
        "ix_federated_identities_user", "federated_identities", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_federated_identities_user", table_name="federated_identities")
    op.drop_table("federated_identities")
