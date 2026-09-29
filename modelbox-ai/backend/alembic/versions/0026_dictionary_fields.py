"""Dictionary fields, a classification scale per workspace, per-field attestations.

Sprint 8 Step 4b (owner decisions, 2026-09-29). Additive only: nothing is
renamed or dropped, and every new column is nullable, so every existing model
reads as before.

* `entity_columns`: `business_name`, `permissible_values` (a JSON list),
  `unit`, `critical_data_element` (NULL means not assessed),
  `authoritative_source`, and `classification_level_id`, a level of the
  workspace's scale by id;
* `model_entities`: `business_name`, `business_owner`, `it_steward`,
  `authoritative_source`;
* `classification_scales` (one per workspace) and `classification_levels`,
  ranked. Every existing workspace gets the default scale: Public, Internal,
  Confidential, Restricted. A level in use cannot be deleted (the foreign key
  from `entity_columns` refuses it);
* `field_attestations`: each dictionary field's current status (`recorded`,
  `pending`, `verified`) and provenance. The review history is the audit log
  (`FIELD_STATUS_CHANGED`), not this table. A CHECK refuses a verified row
  without a reviewer, a time and provenance that can support it.

**Existing PII values are mapped across**: every column marked PII gets an
attestation for its `pii` field with status `recorded` and no provenance, since
nothing records where the value came from. PII type stays its own field.

The audit action CHECK gains FIELD_STATUS_CHANGED and CLASSIFICATION_CHANGED.
**The downgrade keeps them in the CHECK**: audit rows are never deleted, and a
row naming one of them would make the narrower CHECK fail. The previous
release never writes them, so the wider CHECK costs it nothing.

Revision ID: 0026_dictionary_fields
Revises: 0025_keys_and_constraints
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0026_dictionary_fields"
down_revision: str | None = "0025_keys_and_constraints"
branch_labels: str | None = None
depends_on: str | None = None

_BEFORE = (
    "AUTH_LOGIN", "AUTH_LOGIN_FAILED", "API_KEY_CREATED", "API_KEY_REVOKED", "MEMBER_ADDED",
    "MODEL_CREATED", "MODEL_UPDATED", "MODEL_DELETED", "MODEL_APPROVED", "USER_PROVISIONED",
    "USER_DEPROVISIONED", "ARTIFACT_GENERATED", "APPLIANCE_OWNER_DESIGNATED",
)
_AFTER = (*_BEFORE, "FIELD_STATUS_CHANGED", "CLASSIFICATION_CHANGED")
DEFAULT_LEVELS = ("Public", "Internal", "Confidential", "Restricted")

def _column_fields() -> list[sa.Column]:
    return [
        sa.Column("business_name", sa.String(255), nullable=True),
        sa.Column("permissible_values", sa.JSON(), nullable=True),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("critical_data_element", sa.Boolean(), nullable=True),
        sa.Column("authoritative_source", sa.String(255), nullable=True),
    ]


_ENTITY_FIELDS = ("business_name", "business_owner", "it_steward", "authoritative_source")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "classification_scales",
        sa.Column("scale_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.Uuid(),
                  sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(),
                  nullable=False),
        sa.UniqueConstraint("workspace_id", name="uq_classification_scale_workspace"),
    )
    op.create_table(
        "classification_levels",
        sa.Column("level_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scale_id", sa.Uuid(),
                  sa.ForeignKey("classification_scales.scale_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.UniqueConstraint("scale_id", "name", name="uq_classification_level_name"),
    )
    op.create_index("ix_classification_levels_scale_id", "classification_levels", ["scale_id"])

    for column in _column_fields():
        op.add_column("entity_columns", column)
    op.add_column("entity_columns", sa.Column(
        "classification_level_id", sa.Uuid(), sa.ForeignKey("classification_levels.level_id"), nullable=True))
    op.create_index("ix_entity_columns_classification_level_id", "entity_columns", ["classification_level_id"])
    for name in _ENTITY_FIELDS:
        op.add_column("model_entities", sa.Column(name, sa.String(255), nullable=True))

    op.create_table(
        "field_attestations",
        sa.Column("attestation_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey("data_models.model_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("entity_id", sa.Uuid(), sa.ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("column_id", sa.Uuid(), sa.ForeignKey("entity_columns.column_id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("field_key", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provenance", sa.String(16), nullable=True),
        sa.Column("provenance_by", sa.String(320), nullable=True),
        sa.Column("provenance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value_digest", sa.String(64), nullable=True),
        sa.Column("verified_by", sa.String(320), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(),
                  nullable=False),
        sa.CheckConstraint("status IN ('recorded', 'pending', 'verified')", name="ck_field_attestations_status"),
        sa.CheckConstraint("provenance IS NULL OR provenance IN ('ddl', 'source_comment', 'person', 'ai_draft')",
                           name="ck_field_attestations_provenance"),
        # `provenance IS NOT NULL`: `NULL IN (...)` is unknown, which a CHECK accepts.
        sa.CheckConstraint(
            "status <> 'verified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL "
            "AND provenance IS NOT NULL AND provenance IN ('ddl', 'source_comment', 'person'))",
            name="ck_field_attestations_verified"),
    )
    op.create_index("ix_field_attestations_model_id", "field_attestations", ["model_id"])
    op.create_index("ix_field_attestations_entity_id", "field_attestations", ["entity_id"])
    op.create_index("uq_field_attestation_column", "field_attestations", ["column_id", "field_key"], unique=True,
                    postgresql_where=sa.text("column_id IS NOT NULL"))
    op.create_index("uq_field_attestation_table", "field_attestations", ["entity_id", "field_key"], unique=True,
                    postgresql_where=sa.text("column_id IS NULL"))

    bind = op.get_bind()
    # The default scale for every workspace that exists.
    bind.execute(sa.text("INSERT INTO classification_scales (workspace_id, name) "
                         "SELECT workspace_id, 'Sensitivity' FROM workspaces"))
    for rank, level in enumerate(DEFAULT_LEVELS, start=1):
        bind.execute(sa.text("INSERT INTO classification_levels (scale_id, name, rank) "
                             "SELECT scale_id, :name, :rank FROM classification_scales"),
                     {"name": level, "rank": rank})
    # Existing PII values, mapped across as recorded: no provenance is known.
    bind.execute(sa.text(
        "INSERT INTO field_attestations (model_id, entity_id, column_id, field_key, status) "
        "SELECT e.model_id, e.entity_id, c.column_id, 'pii', 'recorded' "
        "FROM entity_columns c JOIN model_entities e ON e.entity_id = c.entity_id "
        "WHERE c.is_pii OR c.pii_type IS NOT NULL"))

    op.drop_constraint("ck_audit_event_action", "audit_event", type_="check")
    op.create_check_constraint("ck_audit_event_action", "audit_event", _in("action", _AFTER))


def downgrade() -> None:
    # The action CHECK stays as 0026 left it: see the module docstring.
    op.drop_table("field_attestations")
    for name in reversed(_ENTITY_FIELDS):
        op.drop_column("model_entities", name)
    op.drop_index("ix_entity_columns_classification_level_id", table_name="entity_columns")
    op.drop_column("entity_columns", "classification_level_id")
    for column in reversed(_column_fields()):
        op.drop_column("entity_columns", column.name)
    op.drop_table("classification_levels")
    op.drop_table("classification_scales")
