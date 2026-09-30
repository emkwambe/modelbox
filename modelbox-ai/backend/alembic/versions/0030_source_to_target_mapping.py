"""Source-to-target mapping: documents, entries, proposals, and a decisions ledger.

Sprint 9 Step 3 (owner decisions, H3, 2026-09-30). Additive: five new tables
and three audit actions; no existing table changes.

* ``mapping_documents``: one mapping from a source model to a target model.
* ``mapping_entries`` and ``mapping_entry_sources``: accepted human decisions
  only, one per target column, in R2's STTM column order.
* ``mapping_proposals``: ModelBox's candidates with their scores, counted as
  nothing until a person decides.
* ``mapping_decisions``: every human decision, append-only, as ``audit_event``
  and ``egress_audit`` are: the application role gets SELECT and INSERT only
  (``app.db_roles.LATER_LEDGERS``), and triggers refuse UPDATE, DELETE and TRUNCATE
  for every role.

Columns are referenced by name and stable_id, never by a foreign key to
``entity_columns``, so a model save that removes a column cannot cascade a
mapping away: drift is computed on read.

**Downgrade** (owner, H3): drops the four mapping tables, so every mapping is
lost, and **keeps ``mapping_decisions``** with its triggers, so the record of
who decided what survives a rollback. The previous release never reads it. A
re-upgrade adopts the existing table after checking its columns, rather than
failing on it or creating a second one. The wider audit CHECK is kept too, as
0026 and 0027 keep theirs: audit rows are never deleted.

Revision ID: 0030_source_to_target_mapping
Revises: 0029_computed_columns
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from app.db_roles import APP_ROLE

revision: str = "0030_source_to_target_mapping"
down_revision: str | None = "0029_computed_columns"
branch_labels: str | None = None
depends_on: str | None = None

_BEFORE = (
    "AUTH_LOGIN", "AUTH_LOGIN_FAILED", "API_KEY_CREATED", "API_KEY_REVOKED", "MEMBER_ADDED",
    "MODEL_CREATED", "MODEL_UPDATED", "MODEL_DELETED", "MODEL_APPROVED", "USER_PROVISIONED",
    "USER_DEPROVISIONED", "ARTIFACT_GENERATED", "APPLIANCE_OWNER_DESIGNATED", "FIELD_STATUS_CHANGED",
    "CLASSIFICATION_CHANGED", "MEMBER_ROLE_CHANGED", "MEMBER_REMOVED",
)
_AFTER = (*_BEFORE, "MAPPING_DOCUMENT_CREATED", "MAPPING_DOCUMENT_DELETED", "MAPPING_DECIDED")

_LEDGER = "mapping_decisions"
_LEDGER_COLUMNS = {
    "decision_id", "workspace_id", "document_id", "entry_id", "proposal_id", "mapping_key", "decision",
    "decided_by_user_id", "decided_by_email", "decided_at", "evidence", "entry_digest_before",
    "entry_digest_after",
}
# This ledger's own trigger function, not 0022's: the table and its triggers
# outlive a downgrade of this revision, and 0022's downgrade drops its function
# without CASCADE, which a dependent trigger would refuse.
_APPEND_ONLY = "modelbox_mapping_ledger_append_only"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _uuid_pk(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False)


def _create_ledger() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(_LEDGER):
        # Kept by a downgrade: adopt it, but only if it is the table this
        # revision defines.
        found = {c["name"] for c in sa.inspect(bind).get_columns(_LEDGER)}
        if found != _LEDGER_COLUMNS:
            raise RuntimeError(f"{_LEDGER} exists with columns {sorted(found)}, not the ones this revision "
                               f"defines {sorted(_LEDGER_COLUMNS)}; refusing to adopt it")
    else:
        op.create_table(
            _LEDGER,
            _uuid_pk("decision_id"),
            sa.Column("workspace_id", sa.Uuid(), nullable=False),
            sa.Column("document_id", sa.Uuid(), nullable=False),
            sa.Column("entry_id", sa.Uuid(), nullable=True),
            sa.Column("proposal_id", sa.Uuid(), nullable=True),
            sa.Column("mapping_key", sa.String(16), nullable=True),
            sa.Column("decision", sa.String(24), nullable=False),
            sa.Column("decided_by_user_id", sa.Uuid(), nullable=False),
            sa.Column("decided_by_email", sa.String(320), nullable=False),
            _now("decided_at"),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("entry_digest_before", sa.String(64), nullable=True),
            sa.Column("entry_digest_after", sa.String(64), nullable=True),
            sa.CheckConstraint(
                "decision IN ('accepted', 'edited', 'rejected', 'authored', 'declared_unmapped', 'changed', "
                "'removed', 'document_approved')",
                name="ck_mapping_decisions_decision"),
        )
        op.create_index("ix_mapping_decisions_document", _LEDGER, ["document_id"])
    # Append-only, whether created or adopted: the grants, then the triggers.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {_LEDGER} FROM {APP_ROLE}, PUBLIC")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_APPEND_ONLY}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$;
        """
    )
    op.execute(f"CREATE OR REPLACE TRIGGER {_LEDGER}_append_only BEFORE UPDATE OR DELETE ON {_LEDGER} "
               f"FOR EACH ROW EXECUTE FUNCTION {_APPEND_ONLY}()")
    op.execute(f"CREATE OR REPLACE TRIGGER {_LEDGER}_no_truncate BEFORE TRUNCATE ON {_LEDGER} "
               f"FOR EACH STATEMENT EXECUTE FUNCTION {_APPEND_ONLY}()")


def upgrade() -> None:
    op.create_table(
        "mapping_documents",
        _uuid_pk("document_id"),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_model_id", sa.Uuid(), sa.ForeignKey("data_models.model_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("source_model_id", sa.Uuid(), sa.ForeignKey("data_models.model_id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("source_model_title", sa.String(255), nullable=False),
        sa.Column("target_system", sa.String(255), nullable=True),
        sa.Column("source_system", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_email", sa.String(320), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_mapping_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_email", sa.String(320), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_mapping_documents_status"),
        sa.CheckConstraint(
            "status <> 'approved' OR (approved_by_user_id IS NOT NULL AND approved_by_email IS NOT NULL "
            "AND approved_at IS NOT NULL)",
            name="ck_mapping_documents_approved"),
    )
    op.create_index("ix_mapping_documents_workspace_id", "mapping_documents", ["workspace_id"])
    op.create_index("ix_mapping_documents_target_model_id", "mapping_documents", ["target_model_id"])
    op.create_index("ix_mapping_documents_source_model_id", "mapping_documents", ["source_model_id"])

    op.create_table(
        "mapping_entries",
        _uuid_pk("entry_id"),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("mapping_documents.document_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("mapping_key", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("target_entity", sa.String(128), nullable=False),
        sa.Column("target_column", sa.String(128), nullable=False),
        sa.Column("target_stable_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("transformation_type", sa.String(16), nullable=True),
        sa.Column("rule_description", sa.Text(), nullable=True),
        sa.Column("logic", sa.Text(), nullable=True),
        sa.Column("join_filter", sa.Text(), nullable=True),
        sa.Column("lookup", sa.Text(), nullable=True),
        sa.Column("default_null_handling", sa.Text(), nullable=True),
        sa.Column("scd_type", sa.Integer(), nullable=True),
        sa.Column("step_kind", sa.String(16), nullable=True),
        sa.Column("control_rule", sa.Text(), nullable=True),
        sa.Column("reconciliation_control_total", sa.Text(), nullable=True),
        sa.Column("reconciliation_compared_with", sa.Text(), nullable=True),
        sa.Column("reconciliation_differences", sa.Text(), nullable=True),
        sa.Column("masking", sa.Boolean(), nullable=True),
        sa.Column("provenance", sa.String(24), nullable=False),
        sa.Column("provenance_by", sa.String(320), nullable=False),
        sa.Column("provenance_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("value_digest", sa.String(64), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.UniqueConstraint("document_id", "mapping_key", name="uq_mapping_entry_key"),
        sa.UniqueConstraint("document_id", "target_entity", "target_column", name="uq_mapping_entry_target"),
        sa.CheckConstraint("kind IN ('mapped', 'constant', 'derived', 'not_yet_mapped')",
                           name="ck_mapping_entries_kind"),
        sa.CheckConstraint(
            "transformation_type IS NULL OR transformation_type IN ('IDENTITY', 'TRANSFORMATION', "
            "'AGGREGATION', 'JOIN', 'GROUP_BY', 'FILTER', 'SORT', 'WINDOW', 'CONDITIONAL')",
            name="ck_mapping_entries_transformation_type"),
        sa.CheckConstraint("scd_type IS NULL OR (scd_type >= 0 AND scd_type <= 6)",
                           name="ck_mapping_entries_scd_type"),
        sa.CheckConstraint("step_kind IS NULL OR step_kind IN ('manual', 'automated')",
                           name="ck_mapping_entries_step_kind"),
        sa.CheckConstraint("provenance IN ('person', 'proposal_accepted')", name="ck_mapping_entries_provenance"),
    )
    op.create_index("ix_mapping_entries_document_id", "mapping_entries", ["document_id"])

    op.create_table(
        "mapping_entry_sources",
        _uuid_pk("source_row_id"),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("mapping_entries.entry_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_entity", sa.String(128), nullable=False),
        sa.Column("source_column", sa.String(128), nullable=False),
        sa.Column("source_stable_id", sa.Integer(), nullable=True),
        sa.Column("source_schema", sa.String(128), nullable=True),
    )
    op.create_index("ix_mapping_entry_sources_entry_id", "mapping_entry_sources", ["entry_id"])

    op.create_table(
        "mapping_proposals",
        _uuid_pk("proposal_id"),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("mapping_documents.document_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_entity", sa.String(128), nullable=False),
        sa.Column("target_column", sa.String(128), nullable=False),
        sa.Column("target_stable_id", sa.Integer(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("name_similarity", sa.Float(), nullable=False),
        sa.Column("type_compatibility", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("method_version", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("resolved_decision_id", sa.Uuid(), nullable=True),
        _now("created_at"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'edited', 'rejected', 'superseded')",
                           name="ck_mapping_proposals_status"),
        sa.CheckConstraint(
            "name_similarity >= 0 AND name_similarity <= 1 AND type_compatibility >= 0 "
            "AND type_compatibility <= 1 AND confidence >= 0 AND confidence <= 1",
            name="ck_mapping_proposals_scores"),
    )
    op.create_index("ix_mapping_proposals_document_id", "mapping_proposals", ["document_id"])

    _create_ledger()

    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint("ck_audit_event_action", "audit_event", _in("action", _AFTER))


def downgrade() -> None:
    # Every mapping is lost; mapping_decisions and its triggers are kept, and
    # the audit CHECK stays wide: see the module docstring.
    op.drop_table("mapping_proposals")
    op.drop_table("mapping_entry_sources")
    op.drop_table("mapping_entries")
    op.drop_table("mapping_documents")
