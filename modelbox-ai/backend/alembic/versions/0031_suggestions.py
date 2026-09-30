"""PII and aggregation-time suggestions, beside the model.

Sprint 9 Step 4 (owner decisions, H3, 2026-09-30). Additive: one new table and
one audit action; no existing column changes.

* ``model_suggestions``: ModelBox's guesses about a model's columns, each with
  the rule that made it, the rule's category and anchor, the signals it read,
  provenance fixed to ``heuristic``, and a status that has no ``verified``. A
  time-column candidate carries a confidence (a ranking from written rules); a
  PII suggestion carries none. Columns are referenced by name and stable id,
  never by a foreign key to ``entity_columns``, as a mapping's are.
* ``SUGGESTION_DECIDED`` joins the audit vocabulary.

``PIIType`` gains categories in the application, not here: ``pii_type`` is a
plain VARCHAR(64) with no CHECK, so no DDL changes for it.

**Downgrade** (owner, H3): drops ``model_suggestions``, so every suggestion is
lost; what a person accepted stays, as ordinary field values. The release
before this one reads ``pii_type`` against seven types and would fail to load
a model holding another, so each column holding a newer type has it cleared
(``is_pii`` kept), a verified ``pii`` field on it returns to pending, because
its value changed, with a FIELD_STATUS_CHANGED audit event, and each is listed
in ``model_conversion_findings``. The
wider audit CHECK is kept, as 0026, 0027 and 0030 keep theirs: audit rows are
never deleted.

Revision ID: 0031_suggestions
Revises: 0030_source_to_target_mapping
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0031_suggestions"
down_revision: str | None = "0030_source_to_target_mapping"
branch_labels: str | None = None
depends_on: str | None = None

_BEFORE = (
    "AUTH_LOGIN", "AUTH_LOGIN_FAILED", "API_KEY_CREATED", "API_KEY_REVOKED", "MEMBER_ADDED",
    "MODEL_CREATED", "MODEL_UPDATED", "MODEL_DELETED", "MODEL_APPROVED", "USER_PROVISIONED",
    "USER_DEPROVISIONED", "ARTIFACT_GENERATED", "APPLIANCE_OWNER_DESIGNATED", "FIELD_STATUS_CHANGED",
    "CLASSIFICATION_CHANGED", "MEMBER_ROLE_CHANGED", "MEMBER_REMOVED", "MAPPING_DOCUMENT_CREATED",
    "MAPPING_DOCUMENT_DELETED", "MAPPING_DECIDED",
)
_AFTER = (*_BEFORE, "SUGGESTION_DECIDED")

#: The PII types the release before this revision reads. Frozen here, not
#: imported: this migration must keep meaning what it meant.
PII_TYPES_BEFORE = ("EMAIL", "SSN", "PHONE", "CREDIT_CARD", "IBAN", "NAME", "ADDRESS")
FINDING_KIND = "pii_type_cleared"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "model_suggestions",
        sa.Column("suggestion_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey("data_models.model_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("entity_name", sa.String(128), nullable=False),
        sa.Column("column_name", sa.String(128), nullable=False),
        sa.Column("column_stable_id", sa.Integer(), nullable=True),
        sa.Column("suggested", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("anchor", sa.String(160), nullable=False),
        sa.Column("rule_name", sa.String(64), nullable=False),
        sa.Column("rule_source", sa.String(16), nullable=False),
        sa.Column("ruleset_digest", sa.String(64), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provenance", sa.String(16), server_default=sa.text("'heuristic'"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_email", sa.String(320), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(),
                  nullable=False),
        sa.CheckConstraint("kind IN ('pii', 'agg_time_column')", name="ck_model_suggestions_kind"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'superseded')",
                           name="ck_model_suggestions_status"),
        sa.CheckConstraint("provenance = 'heuristic'", name="ck_model_suggestions_provenance"),
        sa.CheckConstraint("rule_source IN ('builtin', 'client')", name="ck_model_suggestions_rule_source"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="ck_model_suggestions_confidence"),
        sa.CheckConstraint(
            "(kind = 'pii' AND confidence IS NULL) OR (kind = 'agg_time_column' AND confidence IS NOT NULL)",
            name="ck_model_suggestions_confidence_kind"),
        sa.CheckConstraint(
            "(status IN ('accepted', 'rejected')) = (decided_by_user_id IS NOT NULL AND decided_by_email IS NOT NULL "
            "AND decided_at IS NOT NULL)",
            name="ck_model_suggestions_decided"),
    )
    op.create_index("ix_model_suggestions_model_id", "model_suggestions", ["model_id"])
    op.create_index("uq_model_suggestions_pending", "model_suggestions",
                    ["model_id", "kind", "entity_name", "column_name", "category"], unique=True,
                    postgresql_where=sa.text("status = 'pending'"))

    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint("ck_audit_event_action", "audit_event", _in("action", _AFTER))


def downgrade() -> None:
    bind = op.get_bind()
    newer = bind.execute(sa.text(
        "SELECT c.column_id, c.column_name, c.pii_type, e.entity_name, e.model_id, m.workspace_id "
        "FROM entity_columns c JOIN model_entities e ON e.entity_id = c.entity_id "
        "JOIN data_models m ON m.model_id = e.model_id "
        f"WHERE c.pii_type IS NOT NULL AND NOT (c.{_in('pii_type', PII_TYPES_BEFORE)}) "
        "ORDER BY e.model_id, e.entity_name, c.column_name")).all()
    for row in newer:
        bind.execute(sa.text(
            "INSERT INTO model_conversion_findings (finding_id, model_id, revision, kind, entity_name, detail) "
            "VALUES (:f, :m, :r, :k, :e, :d)"),
            {"f": uuid.uuid4(), "m": row.model_id, "r": revision, "k": FINDING_KIND, "e": row.entity_name,
             "d": f"column {row.column_name}: PII type {row.pii_type} is not one the earlier release reads; "
                  "the type was cleared and the column is still marked PII"})
        bind.execute(sa.text("UPDATE entity_columns SET pii_type = NULL WHERE column_id = :c"), {"c": row.column_id})
        # Its value changed under it, so a verified 'pii' field is verified no
        # longer; and every status change is an audit event (as the application
        # writes them: no actor here, since a migration made the change).
        lapsed = bind.execute(sa.text(
            "UPDATE field_attestations SET status = 'pending', verified_by = NULL, verified_at = NULL "
            "WHERE column_id = :c AND field_key = 'pii' AND status = 'verified' RETURNING attestation_id"),
            {"c": row.column_id}).all()
        if lapsed:
            bind.execute(sa.text(
                "INSERT INTO audit_event (audit_id, action, outcome, scope, workspace_id, resource_type, "
                "resource_id, detail) VALUES (:a, 'FIELD_STATUS_CHANGED', 'SUCCESS', 'workspace', :w, 'model', "
                ":m, CAST(:d AS JSON))"),
                {"a": uuid.uuid4(), "w": row.workspace_id, "m": str(row.model_id),
                 "d": json.dumps({"entity": row.entity_name, "column": row.column_name, "field": "pii",
                                  "from": "verified", "to": "pending",
                                  "reason": f"downgrade below {revision} cleared a PII type the earlier release "
                                            "cannot read"})})

    op.drop_index("uq_model_suggestions_pending", table_name="model_suggestions")
    op.drop_index("ix_model_suggestions_model_id", table_name="model_suggestions")
    op.drop_table("model_suggestions")
    # The audit CHECK stays wide: see the module docstring.
