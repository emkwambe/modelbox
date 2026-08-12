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
    func,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# Valid enumerations enforced at the database layer (CHECK constraints).
PARADIGMS = ("3NF", "KIMBALL", "DATA_VAULT", "OBT")
CARDINALITIES = ("1:1", "1:N", "N:1", "N:M")
WORKSPACE_ROLES = ("OWNER", "ADMIN", "MEMBER")
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

    user_id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    # Nullable: OIDC-provisioned users have no local password.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        default=True, server_default=text("true")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    memberships: Mapped[list["WorkspaceMember"]] = relationship(
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

    data_models: Mapped[list["DataModel"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    members: Mapped[list["WorkspaceMember"]] = relationship(
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
            "role IN ('OWNER', 'ADMIN', 'MEMBER')",
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

    workspace: Mapped["Workspace"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")


class DataModel(Base):
    """A schema instance: a single data model in one paradigm/dialect."""

    __tablename__ = "data_models"
    __table_args__ = (
        CheckConstraint(
            "current_paradigm IN ('3NF', 'KIMBALL', 'DATA_VAULT', 'OBT')",
            name="ck_data_models_current_paradigm",
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

    workspace: Mapped["Workspace"] = relationship(back_populates="data_models")
    entities: Mapped[list["ModelEntity"]] = relationship(
        back_populates="data_model",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    relationships: Mapped[list["EntityRelationship"]] = relationship(
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

    data_model: Mapped["DataModel"] = relationship(back_populates="entities")
    columns: Mapped[list["EntityColumn"]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EntityColumn.ordinal_position",
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
    is_primary_key: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    is_foreign_key: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
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
    is_unique: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    default_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    check_expression: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # ColumnSchema.references — a qualified 'entity.column' FK target (M6).
    # Named reference_target in the database because REFERENCES is a reserved
    # SQL word; the IR field keeps its name.
    reference_target: Mapped[str | None] = mapped_column(String(257), nullable=True)

    entity: Mapped["ModelEntity"] = relationship(back_populates="columns")


class EntityRelationship(Base):
    """A relationship edge between two entities (and optionally columns)."""

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
    from_column_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("entity_columns.column_id"),
        nullable=True,
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_column_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("entity_columns.column_id"),
        nullable=True,
    )
    cardinality: Mapped[str] = mapped_column(String(16), nullable=False)

    data_model: Mapped["DataModel"] = relationship(back_populates="relationships")


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

    Authenticates as its creating user, so it inherits that user's workspace
    memberships and RBAC. Only the prefix and hash are stored — the plaintext
    secret is shown once at creation and is unrecoverable thereafter.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
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
    flawed_graph_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_graph_invariants: Mapped[dict] = mapped_column(
        JSON, nullable=False
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
    submitted_graph_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    feedback_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )


EGRESS_EVENTS = ("ATTEMPT", "SUCCESS", "FAILURE")


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
        CheckConstraint(
            "event IN ('ATTEMPT', 'SUCCESS', 'FAILURE')",
            name="ck_egress_audit_event",
        ),
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

    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
        index=True,
    )


__all__ = [
    "Base",
    "EgressAudit",
    "EGRESS_EVENTS",
    "User",
    "Workspace",
    "WorkspaceMember",
    "DataModel",
    "ModelEntity",
    "EntityColumn",
    "EntityRelationship",
    "SynthesisJob",
    "DatabaseConnection",
    "ApiKey",
    "TrainerAssignment",
    "TrainerSubmission",
    "PARADIGMS",
    "CARDINALITIES",
    "WORKSPACE_ROLES",
    "JOB_STATUSES",
    "CONNECTION_ENGINES",
]
