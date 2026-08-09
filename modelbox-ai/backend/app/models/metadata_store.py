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
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# Valid enumerations enforced at the database layer (CHECK constraints).
PARADIGMS = ("3NF", "KIMBALL", "DATA_VAULT", "OBT")
CARDINALITIES = ("1:1", "1:N", "N:M")


class Base(DeclarativeBase):
    """Declarative base for all metadata-store models."""


def _uuid_pk() -> Mapped[uuid.UUID]:
    """Return a server-generated UUID primary-key column."""
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
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
        UUID(as_uuid=True),
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
        UUID(as_uuid=True),
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

    column_id: Mapped[uuid.UUID] = _uuid_pk()
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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

    entity: Mapped["ModelEntity"] = relationship(back_populates="columns")


class EntityRelationship(Base):
    """A relationship edge between two entities (and optionally columns)."""

    __tablename__ = "entity_relationships"
    __table_args__ = (
        CheckConstraint(
            "cardinality IN ('1:1', '1:N', 'N:M')",
            name="ck_entity_relationships_cardinality",
        ),
    )

    relationship_id: Mapped[uuid.UUID] = _uuid_pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_models.model_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    from_column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity_columns.column_id"),
        nullable=True,
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_entities.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    to_column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity_columns.column_id"),
        nullable=True,
    )
    cardinality: Mapped[str] = mapped_column(String(16), nullable=False)

    data_model: Mapped["DataModel"] = relationship(back_populates="relationships")


__all__ = [
    "Base",
    "Workspace",
    "DataModel",
    "ModelEntity",
    "EntityColumn",
    "EntityRelationship",
    "PARADIGMS",
    "CARDINALITIES",
]
