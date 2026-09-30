"""Metadata store ORM models (SQLAlchemy 2.0, async-mapped).

A faithful mapping of the PostgreSQL 16 metadata schema defined in TRD §2.3.
Five core tables model platform state:

    Workspace  1─┬─N  DataModel  1─┬─N  ModelEntity  1─┬─N  EntityColumn
                 │                 └─N  EntityRelationship (edges)

All primary keys are server-generated UUIDs (``gen_random_uuid()``); child rows
cascade on parent deletion, mirroring the ``ON DELETE CASCADE`` DDL.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    insert,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# JSONB on PostgreSQL, as migration 0006 created the trainer columns; plain
# JSON elsewhere (the SQLite test schema).
_JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")

# Valid enumerations enforced at the database layer (CHECK constraints).
PARADIGMS = ("3NF", "KIMBALL", "DATA_VAULT", "OBT")
CARDINALITIES = ("1:1", "1:N", "N:1", "N:M")
WORKSPACE_ROLES = ("OWNER", "ADMIN", "APPROVER", "MEMBER", "VIEWER")
JOB_STATUSES = ("PENDING", "PROCESSING", "COMPLETED", "FAILED")
CONNECTION_ENGINES = ("POSTGRESQL", "SNOWFLAKE", "BIGQUERY", "MYSQL", "DUCKDB")


class Base(DeclarativeBase):
    """Declarative base for all metadata-store models."""


def _uuid_pk() -> Mapped[uuid.UUID]:
    """Return a UUID primary-key column.

    Uses the dialect-portable :class:`~sqlalchemy.Uuid` type (native UUID on
    PostgreSQL, CHAR on SQLite) with a Python-side default so PKs populate on
    every backend. The Postgres migration additionally sets a
    ``gen_random_uuid()`` server default for externally-issued INSERTs.
    """
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(Base):
    """An authenticated user (identity from local creds or an OIDC provider)."""

    __tablename__ = "users"
    # As migration 0002 created them: a named unique constraint and a separate
    # plain index. `unique=True, index=True` on the column would instead
    # declare a single unique index, which no migrated database has.
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
    )

    user_id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable: OIDC-provisioned users have no local password.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        default=True, server_default=text("true")
    )
    # The appliance's owner: set only by `python -m app.cli create-owner`. It
    # grants reading appliance-scope audit events (logins, SCIM). Holding the
    # OWNER role in a workspace does not imply it, since every personal
    # workspace makes its creator OWNER (owner decision, Sprint 7 Step 3).
    is_appliance_owner: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    memberships: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Workspace(Base):
    """Workspace / project isolation boundary."""

    __tablename__ = "workspaces"

    workspace_id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    data_models: Mapped[list[DataModel]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WorkspaceMember(Base):
    """Membership linking a user to a workspace with a role (multi-tenancy)."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspace_member"
        ),
        CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'APPROVER', 'MEMBER', 'VIEWER')",
            name="ck_workspace_members_role",
        ),
    )

    membership_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'MEMBER'")
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class FederatedIdentity(Base):
    """A link between an external IdP subject and a local user (G8).

    **Keyed on (issuer, subject), never on email.** An email address is mutable
    and, worse, reassignable: organisations recycle addresses when people leave,
    so matching on it would eventually hand a new joiner the previous holder's
    account and every workspace they belonged to. The OIDC `sub` claim is the
    only identifier a provider promises is stable and unique within its issuer,
    and pairing it with `iss` keeps two providers' subject spaces from colliding.

    **A separate table rather than columns on `users`.** One person can federate
    from more than one issuer — a migration between IdPs is exactly when both
    are live — and a single pair of columns forces a destructive choice at the
    moment continuity matters most.

    The email is still stored on the user for display and for the audit trail,
    and is refreshed from the token; it is simply not the key.
    """

    __tablename__ = "federated_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_federated_identity"),
        Index("ix_federated_identities_user", "user_id"),
    )

    identity_id: Mapped[uuid.UUID] = _uuid_pk()
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class DataModel(Base):
    """A schema instance: a single data model in one paradigm/dialect."""

    __tablename__ = "data_models"
    __table_args__ = (
        CheckConstraint(
            "current_paradigm IN ('3NF', 'KIMBALL', 'DATA_VAULT', 'OBT')",
            name="ck_data_models_current_paradigm",
        ),
        CheckConstraint(
            "reconciliation_status IN ('reconciled', 'unreconciled')",
            name="ck_data_models_reconciliation_status",
        ),
    )

    model_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    current_paradigm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_dialect: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'snowflake'")
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    # Suggested metrics, as a JSON list of {name, formula, description} (M1).
    # Stored on the model rather than decomposed into rows: a metric is an
    # opaque formula string with no foreign keys into the graph, so a table
    # would buy joins nobody performs. Nullable because every row that predates
    # migration 0014 legitimately has none — an empty list and "never persisted"
    # are the same thing here, and inventing a distinction would be worse.
    suggested_metrics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Set only on a model imported from a DDL file (migration 0023): whether
    # the import reconciled against counts taken from the file independently
    # of the parser, and the full report. NULL means not imported.
    reconciliation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    import_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # SynthesizedModel.sequences: the sequences an imported file creates, as a
    # JSON list (migration 0028). NULL for a model with none: none_as_null, so
    # Python None is SQL NULL rather than a JSON null.
    sequences: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="data_models")
    entities: Mapped[list[ModelEntity]] = relationship(
        back_populates="data_model",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    relationships: Mapped[list[EntityRelationship]] = relationship(
        back_populates="data_model",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ModelEntity(Base):
    """An entity node: table / fact / dimension / hub / link / satellite."""

    __tablename__ = "model_entities"
    __table_args__ = (
        UniqueConstraint("model_id", "entity_name", name="uq_model_entity_name"),
    )

    entity_id: Mapped[uuid.UUID] = _uuid_pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_models.model_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # FACT, DIMENSION, HUB, LINK, SATELLITE, TABLE
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canvas_position_x: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.0")
    )
    canvas_position_y: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.0")
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Grain + governance metadata (Sprint U2).
    grain: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    freshness_sla: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Default aggregation time dimension for this entity's measures (Sprint 2).
    # Nullable by design: an entity with no temporal column has no time axis.
    agg_time_column: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # High-water mark for EntityColumn.stable_id (Sprint 2, Q6). Stored, never
    # derived as max(existing) + 1: deleting the highest column must NOT free
    # its id, which is precisely the wire-compatibility break H6 is about.
    # Only ever increases. Survives a save because GraphRepository upserts
    # entities by (model_id, entity_name) rather than deleting them.
    next_stable_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    # The entity's place in the model, so a model reopens in the order it was
    # saved (migration 0025).
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Dictionary fields a person supplies (migration 0026). NULL until someone
    # does; nothing is inferred.
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    it_steward: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authoritative_source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    data_model: Mapped[DataModel] = relationship(back_populates="entities")
    columns: Mapped[list[EntityColumn]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EntityColumn.ordinal_position",
    )
    constraints: Mapped[list[EntityConstraint]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EntityConstraint.position",
    )


class EntityColumn(Base):
    """An attribute column belonging to an entity."""

    __tablename__ = "entity_columns"
    __table_args__ = (
        UniqueConstraint("entity_id", "stable_id", name="uq_entity_column_stable_id"),
    )

    column_id: Mapped[uuid.UUID] = _uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Keys and constraints are not column flags here: they live in
    # entity_constraints and relationship_columns (migration 0025), and the
    # IR derives ColumnSchema's flags from them.
    is_pii: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    pii_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Semantic-layer declaration (FR-2.3 / Semantic Sprint 2).
    is_metric: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    aggregation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Quality rules (Sprint U3) — numeric bounds + text format pattern.
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    regex_pattern: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Stable column identity (Sprint 2, Q6). Allocated once from the entity's
    # high-water mark and immutable thereafter — a reorder moves
    # ordinal_position, never this. Becomes the Protobuf field tag in Sprint 3
    # and lets the diff engine tell a rename from a drop-plus-add in Sprint 4.
    stable_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Physical constraints (Sprint 2, H4).
    is_nullable: Mapped[bool] = mapped_column(
        default=True, server_default=text("true")
    )
    default_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # ColumnSchema.source_data_type: the type as an imported file declared it
    # (migration 0024). NULL for a column that was not imported.
    source_data_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # ColumnSchema.source_default_value: the DEFAULT as an imported file
    # declared it (migration 0025). NULL for a column that was not imported.
    source_default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ColumnSchema.identity: an identity column's generation, seed and
    # increment, or the trigger and sequence that fill it, as JSON (migration
    # 0028). NULL for any other column: none_as_null, so Python None is SQL
    # NULL rather than a JSON null.
    identity: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # ColumnSchema.computed_expression and computed_persisted: a computed
    # column's expression as the imported file declared it, and whether the
    # source stores it (migration 0029). NULL for any other column.
    computed_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_persisted: Mapped[bool | None] = mapped_column(nullable=True)
    # Dictionary fields a person supplies (migration 0026). NULL until someone
    # does. permissible_values is a JSON list of values; critical_data_element
    # NULL means not assessed, which is not the same as False.
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissible_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    critical_data_element: Mapped[bool | None] = mapped_column(nullable=True)
    authoritative_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # A level of the workspace's classification scale, by id: renaming the
    # level renames every use, and a level in use cannot be deleted.
    classification_level_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("classification_levels.level_id"),
        nullable=True,
        index=True,
    )

    entity: Mapped[ModelEntity] = relationship(back_populates="columns")


class ClassificationScale(Base):
    """A workspace's classification scale (migration 0026): one per workspace."""

    __tablename__ = "classification_scales"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_classification_scale_workspace"),
    )

    scale_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    levels: Mapped[list[ClassificationLevel]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClassificationLevel.rank",
    )


#: The scale every workspace starts with, least to most sensitive.
DEFAULT_CLASSIFICATION_LEVELS: tuple[str, ...] = ("Public", "Internal", "Confidential", "Restricted")


class ClassificationLevel(Base):
    """One level of a classification scale, ranked least to most sensitive."""

    __tablename__ = "classification_levels"
    __table_args__ = (
        UniqueConstraint("scale_id", "name", name="uq_classification_level_name"),
    )

    level_id: Mapped[uuid.UUID] = _uuid_pk()
    scale_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("classification_scales.scale_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)


@event.listens_for(Workspace, "after_insert")
def _default_classification_scale(_mapper: object, connection: Connection, workspace: Workspace) -> None:
    """Every workspace starts with the default scale, wherever it is created
    (five code paths create workspaces; migration 0026 gave existing ones
    theirs)."""
    scale_id = uuid.uuid4()
    connection.execute(insert(ClassificationScale).values(
        scale_id=scale_id, workspace_id=workspace.workspace_id, name="Sensitivity"))
    connection.execute(insert(ClassificationLevel), [
        {"level_id": uuid.uuid4(), "scale_id": scale_id, "name": name, "rank": rank}
        for rank, name in enumerate(DEFAULT_CLASSIFICATION_LEVELS, start=1)])


ATTESTATION_STATUSES = ("recorded", "pending", "verified")
#: Where a field's value came from. ``ai_draft`` is recorded provenance of a
#: kind that can never support "verified": an AI draft is a first draft a
#: modeller reviews, and "verified" must never describe an unreviewed draft.
PROVENANCE_KINDS = ("ddl", "source_comment", "person", "ai_draft")
VERIFIABLE_PROVENANCE = ("ddl", "source_comment", "person")


class FieldAttestation(Base):
    """One dictionary field's current status and provenance (migration 0026).

    Current state only. Every status change is also an ``audit_event`` row
    (FIELD_STATUS_CHANGED), written in the same transaction, and the
    append-only audit log is the review history; there is no second ledger.

    A table-level field has no ``column_id``. ``verified`` is never written by
    a client: the application sets it only when the three conditions hold
    (``app.services.attestation``), and the CHECK below refuses a verified row
    without a reviewer, a time, and provenance that can support it.
    """

    __tablename__ = "field_attestations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('recorded', 'pending', 'verified')",
            name="ck_field_attestations_status",
        ),
        CheckConstraint(
            "provenance IS NULL OR provenance IN ('ddl', 'source_comment', 'person', 'ai_draft')",
            name="ck_field_attestations_provenance",
        ),
        # `provenance IS NOT NULL` is not redundant: `NULL IN (...)` is
        # unknown, and a CHECK passes on unknown, so without it a verified row
        # with no provenance was accepted (found by its negative control).
        CheckConstraint(
            "status <> 'verified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL "
            "AND provenance IS NOT NULL AND provenance IN ('ddl', 'source_comment', 'person'))",
            name="ck_field_attestations_verified",
        ),
        Index(
            "uq_field_attestation_column", "column_id", "field_key", unique=True,
            postgresql_where=text("column_id IS NOT NULL"),
            sqlite_where=text("column_id IS NOT NULL"),
        ),
        Index(
            "uq_field_attestation_table", "entity_id", "field_key", unique=True,
            postgresql_where=text("column_id IS NULL"),
            sqlite_where=text("column_id IS NULL"),
        ),
    )

    attestation_id: Mapped[uuid.UUID] = _uuid_pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_models.model_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("entity_columns.column_id", ondelete="CASCADE"),
        nullable=True,
    )
    field_key: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provenance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Who supplied the value when provenance is 'person' (the email, copied).
    provenance_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    provenance_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SHA-256 of the value the status refers to: a verified field whose value
    # no longer has this digest has lapsed.
    value_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


CONSTRAINT_KINDS = ("PRIMARY KEY", "UNIQUE", "CHECK")


class EntityConstraint(Base):
    """An entity's primary key, a UNIQUE constraint, or a CHECK constraint (0025).

    Members are stored by column name in ``entity_constraint_columns``; the IR
    checks every member against the entity's columns on each write.
    """

    __tablename__ = "entity_constraints"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('PRIMARY KEY', 'UNIQUE', 'CHECK')",
            name="ck_entity_constraints_kind",
        ),
        CheckConstraint(
            "(kind = 'CHECK') = (expression IS NOT NULL)",
            name="ck_entity_constraints_expression",
        ),
    )

    constraint_id: Mapped[uuid.UUID] = _uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    entity: Mapped[ModelEntity] = relationship(back_populates="constraints")
    columns: Mapped[list[EntityConstraintColumn]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EntityConstraintColumn.position",
    )


class EntityConstraintColumn(Base):
    """One column of an entity constraint, in key order."""

    __tablename__ = "entity_constraint_columns"

    constraint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entity_constraints.constraint_id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    column_name: Mapped[str] = mapped_column(String(128), nullable=False)


class EntityRelationship(Base):
    """A relationship edge between two entities; its column pairs are rows of
    ``relationship_columns`` (migration 0025). None means unresolved."""

    __tablename__ = "entity_relationships"
    __table_args__ = (
        CheckConstraint(
            "cardinality IN ('1:1', '1:N', 'N:1', 'N:M')",
            name="ck_entity_relationships_cardinality",
        ),
    )

    relationship_id: Mapped[uuid.UUID] = _uuid_pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_models.model_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cardinality: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    data_model: Mapped[DataModel] = relationship(back_populates="relationships")
    columns: Mapped[list[RelationshipColumn]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RelationshipColumn.position",
    )


class RelationshipColumn(Base):
    """One column pair of a relationship, by column name (migration 0025).

    Stored by name so an unresolved or partly resolved pair, or one naming a
    column that does not exist, is kept exactly as written and reported by the
    linter, rather than lost to a NULL id.
    """

    __tablename__ = "relationship_columns"

    relationship_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entity_relationships.relationship_id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ModelConversionFinding(Base):
    """Something a migration could not convert exactly, listed by model.

    Written by migration 0025 when keys and constraints moved from column
    flags to their own tables. The model keeps what it can; this says what
    changed shape and why.
    """

    __tablename__ = "model_conversion_findings"

    finding_id: Mapped[uuid.UUID] = _uuid_pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_models.model_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


class SynthesisJob(Base):
    """Async synthesis job tracking (FR-1.1)."""

    __tablename__ = "synthesis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_synthesis_jobs_status",
        ),
        CheckConstraint(
            "paradigm IN ('3NF', 'KIMBALL', 'DATA_VAULT', 'OBT')",
            name="ck_synthesis_jobs_paradigm",
        ),
    )

    job_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    paradigm: Mapped[str] = mapped_column(String(32), nullable=False)
    dialect: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'snowflake'")
    )
    result_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("data_models.model_id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class DatabaseConnection(Base):
    """An external database connection for brownfield introspection (FR-2.1).

    The connection URI is stored encrypted at rest (AES-256-GCM).
    """

    __tablename__ = "database_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "name", name="uq_database_connections_workspace_name"
        ),
        CheckConstraint(
            "engine IN ('POSTGRESQL', 'SNOWFLAKE', 'BIGQUERY', 'MYSQL', 'DUCKDB')",
            name="ck_database_connections_engine",
        ),
    )

    connection_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    engine: Mapped[str] = mapped_column(String(30), nullable=False)
    connection_uri_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class ApiKey(Base):
    """A programmatic API key (workspace-scoped, SHA-256 hashed at rest).

    Authenticates as its creating user, but only in its own workspace and only
    up to the lower of ``role_cap`` and the creator's current role there, which
    is re-read on every request. Only the prefix and hash are stored — the
    plaintext secret is shown once at creation and is unrecoverable thereafter.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
        CheckConstraint(
            "role_cap IN (" + ", ".join(f"'{r}'" for r in WORKSPACE_ROLES) + ")",
            name="ck_api_keys_role_cap",
        ),
    )

    api_key_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role_cap: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="VIEWER", default="VIEWER"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TrainerAssignment(Base):
    """A data-modeling assignment (ModelBox Trainer — isolated tables)."""

    __tablename__ = "trainer_assignments"

    assignment_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.workspace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional defective seed graph for "Spot the Flaw" mode.
    flawed_graph_json: Mapped[dict | None] = mapped_column(_JSON_DOCUMENT, nullable=True)
    expected_graph_invariants: Mapped[dict] = mapped_column(
        _JSON_DOCUMENT, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


class TrainerSubmission(Base):
    """A graded student submission (ModelBox Trainer)."""

    __tablename__ = "trainer_submissions"

    submission_id: Mapped[uuid.UUID] = _uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("trainer_assignments.assignment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_graph_json: Mapped[dict] = mapped_column(_JSON_DOCUMENT, nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    feedback_json: Mapped[dict | None] = mapped_column(_JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


EGRESS_ATTEMPT = "ATTEMPT"
EGRESS_SUCCESS = "SUCCESS"
EGRESS_FAILURE = "FAILURE"

# The one place this vocabulary is written down. It previously existed three
# times — here, as string literals in the sink, and again in the migration's
# CHECK constraint — with nothing enforcing agreement between them. That is the
# shape that drifts: the same class as the three private `_is_temporal_type`
# predicates whose disagreement was the Cube bug.
#
# The constraint below is generated from this tuple, the sink imports these
# names, and `test_the_migration_check_matches_the_declared_vocabulary` holds
# the migration's frozen literal against it.
EGRESS_EVENTS = (EGRESS_ATTEMPT, EGRESS_SUCCESS, EGRESS_FAILURE)


def _egress_event_check() -> str:
    """Render the CHECK expression from the declared vocabulary."""
    values = ", ".join(f"'{event}'" for event in EGRESS_EVENTS)
    return f"event IN ({values})"


class EgressAudit(Base):
    """Append-only record of every outbound provider request (D3, D4).

    **Append-only, and one row per event rather than one per request.** The
    attempt is written *before* the call and never updated; the outcome is a
    second row correlated by ``attempt_id``. An UPDATE would have been simpler
    and wrong — it lets a later write revise the record of what already left,
    which is the one thing an audit trail must not permit.

    **Written before the call, deliberately.** A request that leaves the
    network and then fails is still a request that left, so a ledger recording
    only successes is not an audit trail — it is a success log. If the process
    dies mid-flight the ATTEMPT row survives alone, which states precisely what
    is known: we tried, and we cannot say what happened.

    **Committed in its own transaction**, independent of the caller's. Egress
    is not undone by a rollback, so the record of it must not be either. A
    ledger enlisted in the caller's transaction would quietly erase exactly the
    requests made during work that later failed.

    ``prompt_sha256`` rather than the prompt. The ledger answers what left,
    when, to whom, and lets an operator prove a specific text was or was not
    sent — without becoming a second copy of the data the governance story
    exists to protect.
    """

    __tablename__ = "egress_audit"
    __table_args__ = (
        CheckConstraint(_egress_event_check(), name="ck_egress_audit_event"),
        Index("ix_egress_audit_attempt", "attempt_id"),
        Index("ix_egress_audit_occurred", "occurred_at"),
    )

    egress_id: Mapped[uuid.UUID] = _uuid_pk()
    # Correlates the ATTEMPT with its SUCCESS or FAILURE. Not a foreign key:
    # the rows are peers, and a constraint would make the outcome row's write
    # depend on the attempt row still existing.
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event: Mapped[str] = mapped_column(String(16), nullable=False)

    task: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    egress_class: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False)

    # Nullable throughout: the gateway is a process-wide singleton and does not
    # always know who is asking. Recording "unknown" honestly beats inventing
    # an attribution the ledger cannot support.
    model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    # Known only on the outcome row.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Indexed by the named Index in __table_args__; `index=True` here would
    # declare a second index that no migration creates.
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


#: Audit actions. Vocabulary rather than free text, so an export can be
#: filtered and a reviewer can be told what the complete set is.
#:
#: Every member is emitted by a code path, and `test_audit_actions.py` drives
#: each one. An action with no path is removed, not left declared: a declared
#: action nothing emits tells a reviewer to look for events that cannot exist
#: (Sprint 7 Step 3 removed AUTH_LOGOUT, MEMBER_ROLE_CHANGED and MEMBER_REMOVED;
#: the last two came back in Sprint 8 Step 6 with an emitter each).
AUDIT_ACTIONS: tuple[str, ...] = (
    "AUTH_LOGIN",
    "AUTH_LOGIN_FAILED",
    "API_KEY_CREATED",
    "API_KEY_REVOKED",
    "MEMBER_ADDED",
    "MODEL_CREATED",
    "MODEL_UPDATED",
    "MODEL_DELETED",
    "MODEL_APPROVED",
    "USER_PROVISIONED",
    "USER_DEPROVISIONED",
    "ARTIFACT_GENERATED",
    "APPLIANCE_OWNER_DESIGNATED",
    "FIELD_STATUS_CHANGED",
    "CLASSIFICATION_CHANGED",
    # Removed in Sprint 7 (nothing emitted them); back in Sprint 8 Step 6 with
    # the members API as their emitter (migration 0027).
    "MEMBER_ROLE_CHANGED",
    "MEMBER_REMOVED",
    # Source-to-target mapping (Sprint 9 Step 3, migration 0030).
    "MAPPING_DOCUMENT_CREATED",
    "MAPPING_DOCUMENT_DELETED",
    "MAPPING_DECIDED",
)

#: Outcomes. `DENIED` is separate from `FAILURE` on purpose: a refused
#: authorisation and a crashed handler are different events to a reviewer, and
#: collapsing them hides the one they came to look for.
AUDIT_OUTCOMES: tuple[str, ...] = ("SUCCESS", "DENIED", "FAILURE")

#: Where an event belongs. A workspace event names its workspace; an appliance
#: event (a login, a SCIM change) has none, and says so rather than leaving a
#: NULL to be read as "unknown".
AUDIT_SCOPES: tuple[str, ...] = ("workspace", "appliance")


class AuditEvent(Base):
    """Append-only record of who did what inside the appliance (G11).

    **Distinct from `EgressAudit`, and the distinction is the point.** That
    ledger answers *what left the network*. This answers *who did what here*.
    A supervisor asks both, and a single table answering neither cleanly is
    worse than two answering one each.

    **The actor's email is denormalised on purpose.** ``actor_user_id`` is not a
    foreign key and the email is copied at write time, because the audit trail
    has to survive the user being deleted — which is precisely the moment
    somebody wants to read it. A join that returns NULL for a departed employee
    is an audit log that forgets the people most worth remembering.

    **Append-only in the same sense as the egress ledger**: rows are inserted
    and never updated. There is no ``updated_at`` because there is no update.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        CheckConstraint(
            "action IN (" + ", ".join(f"'{a}'" for a in AUDIT_ACTIONS) + ")",
            name="ck_audit_event_action",
        ),
        CheckConstraint(
            "outcome IN (" + ", ".join(f"'{o}'" for o in AUDIT_OUTCOMES) + ")",
            name="ck_audit_event_outcome",
        ),
        CheckConstraint(
            "(scope = 'workspace' AND workspace_id IS NOT NULL) OR "
            "(scope = 'appliance' AND workspace_id IS NULL)",
            name="ck_audit_event_scope",
        ),
        Index("ix_audit_event_workspace", "workspace_id"),
        Index("ix_audit_event_actor", "actor_user_id"),
        Index("ix_audit_event_occurred", "occurred_at"),
    )

    audit_id: Mapped[uuid.UUID] = _uuid_pk()

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    # Derived by `audit_log.record` from `workspace_id`; the CHECK above keeps
    # the two consistent for any writer.
    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    # Nullable: an unauthenticated failed login has no user, and recording
    # "unknown" honestly beats attributing it to somebody.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Structured, and never the resource's contents. The audit log records that
    # a model was exported, not the model — the same rule that keeps the egress
    # ledger a digest rather than a second copy of the prompt.
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Indexed by the named Index in __table_args__; `index=True` here would
    # declare a second index that no migration creates.
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Source-to-target mapping (Sprint 9 Step 3, migration 0030; owner, H3)
#
# Columns are referenced by name with their stable_id beside it, never by a
# foreign key to entity_columns: saving a model deletes the row of a column it
# no longer has, and a key would cascade the mapping away. Drift is computed on
# read (app.services.mapping), so a mapping whose column is gone is flagged and
# kept. Proposals (inference) and entries (human decisions) are separate
# tables, so a proposal can never be counted as a mapping.
# ---------------------------------------------------------------------------
class MappingDocument(Base):
    """One mapping from a source model to a target model of the same workspace."""

    __tablename__ = "mapping_documents"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'approved')", name="ck_mapping_documents_status"),
        # Approval stays unused in Sprint 9 (owner, H3): it arrives with the
        # decision ledger. The columns exist, and an approved row is complete.
        CheckConstraint(
            "status <> 'approved' OR (approved_by_user_id IS NOT NULL AND approved_by_email IS NOT NULL "
            "AND approved_at IS NOT NULL)",
            name="ck_mapping_documents_approved",
        ),
    )

    document_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False, index=True)
    target_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("data_models.model_id", ondelete="CASCADE"), nullable=False, index=True)
    source_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("data_models.model_id", ondelete="SET NULL"), nullable=True, index=True)
    source_model_title: Mapped[str] = mapped_column(String(255), nullable=False)
    target_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default=text("'draft'"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # High-water mark for entry keys (M-0001...): never reused, like next_stable_id.
    next_mapping_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp(),
        nullable=False)

    entries: Mapped[list[MappingEntry]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="MappingEntry.mapping_key")
    proposals: Mapped[list[MappingProposal]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="MappingProposal.created_at")


class MappingEntry(Base):
    """An accepted human decision about one target column: R2's STTM row.

    Nothing here is ever an unreviewed proposal. Target type, nullability and
    key, and the source columns' classification and CDE, are read live from
    the models, not stored; each decision's evidence keeps a snapshot.
    """

    __tablename__ = "mapping_entries"
    __table_args__ = (
        UniqueConstraint("document_id", "mapping_key", name="uq_mapping_entry_key"),
        UniqueConstraint("document_id", "target_entity", "target_column", name="uq_mapping_entry_target"),
        CheckConstraint("kind IN ('mapped', 'constant', 'derived', 'not_yet_mapped')",
                        name="ck_mapping_entries_kind"),
        CheckConstraint(
            "transformation_type IS NULL OR transformation_type IN ('IDENTITY', 'TRANSFORMATION', "
            "'AGGREGATION', 'JOIN', 'GROUP_BY', 'FILTER', 'SORT', 'WINDOW', 'CONDITIONAL')",
            name="ck_mapping_entries_transformation_type"),
        CheckConstraint("scd_type IS NULL OR (scd_type >= 0 AND scd_type <= 6)", name="ck_mapping_entries_scd_type"),
        CheckConstraint("step_kind IS NULL OR step_kind IN ('manual', 'automated')",
                        name="ck_mapping_entries_step_kind"),
        CheckConstraint("provenance IN ('person', 'proposal_accepted')", name="ck_mapping_entries_provenance"),
    )

    entry_id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("mapping_documents.document_id", ondelete="CASCADE"), nullable=False, index=True)
    mapping_key: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    target_entity: Mapped[str] = mapped_column(String(128), nullable=False)
    target_column: Mapped[str] = mapped_column(String(128), nullable=False)
    target_stable_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    transformation_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rule_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logic: Mapped[str | None] = mapped_column(Text, nullable=True)
    join_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    lookup: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_null_handling: Mapped[str | None] = mapped_column(Text, nullable=True)
    scd_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    control_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciliation_control_total: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciliation_compared_with: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciliation_differences: Mapped[str | None] = mapped_column(Text, nullable=True)
    masking: Mapped[bool | None] = mapped_column(nullable=True)
    # Who supplied the entry, per entry (owner, H3): each decision in the
    # ledger holds the content before and after.
    provenance: Mapped[str] = mapped_column(String(24), nullable=False)
    provenance_by: Mapped[str] = mapped_column(String(320), nullable=False)
    provenance_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    value_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp(),
        nullable=False)

    sources: Mapped[list[MappingEntrySource]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="MappingEntrySource.position")


class MappingEntrySource(Base):
    """One source column of an entry, in order: one for one-to-one, several for many-to-one."""

    __tablename__ = "mapping_entry_sources"

    source_row_id: Mapped[uuid.UUID] = _uuid_pk()
    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("mapping_entries.entry_id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_entity: Mapped[str] = mapped_column(String(128), nullable=False)
    source_column: Mapped[str] = mapped_column(String(128), nullable=False)
    source_stable_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_schema: Mapped[str | None] = mapped_column(String(128), nullable=True)


class MappingProposal(Base):
    """A candidate mapping from ModelBox's proposer: inference, counted as nothing."""

    __tablename__ = "mapping_proposals"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'edited', 'rejected', 'superseded')",
                        name="ck_mapping_proposals_status"),
        CheckConstraint(
            "name_similarity >= 0 AND name_similarity <= 1 AND type_compatibility >= 0 "
            "AND type_compatibility <= 1 AND confidence >= 0 AND confidence <= 1",
            name="ck_mapping_proposals_scores"),
    )

    proposal_id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("mapping_documents.document_id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity: Mapped[str] = mapped_column(String(128), nullable=False)
    target_column: Mapped[str] = mapped_column(String(128), nullable=False)
    target_stable_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sources: Mapped[list] = mapped_column(JSON, nullable=False)
    name_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    type_compatibility: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    method_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending",
                                        server_default=text("'pending'"))
    resolved_decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)


class MappingDecision(Base):
    """Every human decision about a mapping entry or proposal: append-only.

    One of ``app.db_roles.ALL_LEDGERS``: the application role may only SELECT and
    INSERT, and migration 0030's triggers refuse UPDATE, DELETE and TRUNCATE
    for every role. It references what it is about by id without a foreign
    key, as ``audit_event`` does, so the record outlives the entry, the
    document, and a downgrade (owner, H3). Its fields are those of the future
    decision ledger's Decision: the elements it governs, the evidence shown,
    the decision, the decider and the time, and the resulting change.
    """

    __tablename__ = "mapping_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('accepted', 'edited', 'rejected', 'authored', 'declared_unmapped', 'changed', "
            "'removed', 'document_approved')",
            name="ck_mapping_decisions_decision"),
        Index("ix_mapping_decisions_document", "document_id"),
    )

    decision_id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    mapping_key: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    # NOT NULL: the database refuses a decision without a person. The API
    # takes the decider from the authenticated caller, never from a body.
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    decided_by_email: Mapped[str] = mapped_column(String(320), nullable=False)
    decided_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    entry_digest_before: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_digest_after: Mapped[str | None] = mapped_column(String(64), nullable=True)


__all__ = [
    "ATTESTATION_STATUSES",
    "AUDIT_ACTIONS",
    "AUDIT_OUTCOMES",
    "CARDINALITIES",
    "CONNECTION_ENGINES",
    "DEFAULT_CLASSIFICATION_LEVELS",
    "EGRESS_ATTEMPT",
    "EGRESS_EVENTS",
    "EGRESS_FAILURE",
    "EGRESS_SUCCESS",
    "JOB_STATUSES",
    "PARADIGMS",
    "PROVENANCE_KINDS",
    "VERIFIABLE_PROVENANCE",
    "WORKSPACE_ROLES",
    "ApiKey",
    "AuditEvent",
    "Base",
    "ClassificationLevel",
    "ClassificationScale",
    "DataModel",
    "DatabaseConnection",
    "EgressAudit",
    "EntityColumn",
    "EntityRelationship",
    "FederatedIdentity",
    "FieldAttestation",
    "MappingDecision",
    "MappingDocument",
    "MappingEntry",
    "MappingEntrySource",
    "MappingProposal",
    "ModelEntity",
    "SynthesisJob",
    "TrainerAssignment",
    "TrainerSubmission",
    "User",
    "Workspace",
    "WorkspaceMember",
]
