"""Pydantic v2 API & LLM schemas for ModelBox AI.

These models serve three roles:

1. **API contracts** — request/response bodies for the synthesis and
   paradigm-transformation endpoints (Blueprint §6, TRD §2.4).
2. **Structured LLM output** — the ``SynthesizedModel`` family is passed to
   Instructor as the ``response_model`` so the gateway enforces rigid JSON
   adherence on raw LLM output.
3. **Serialization** — ``from_attributes`` variants read directly off the
   SQLAlchemy ORM rows.

All models use Pydantic v2 idioms (``model_config``, ``field_validator``).
"""

from __future__ import annotations

import enum
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class Paradigm(str, enum.Enum):
    """Supported data-modeling paradigms (FR-3.1)."""

    THREE_NF = "3NF"
    KIMBALL = "KIMBALL"
    DATA_VAULT = "DATA_VAULT"
    OBT = "OBT"


class EntityType(str, enum.Enum):
    """Entity node classifications across paradigms."""

    TABLE = "TABLE"
    FACT = "FACT"
    DIMENSION = "DIMENSION"
    HUB = "HUB"
    LINK = "LINK"
    SATELLITE = "SATELLITE"


class Cardinality(str, enum.Enum):
    """Relationship cardinalities."""

    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"


class SourceType(str, enum.Enum):
    """Accepted synthesis input types (FR-1.1)."""

    NATURAL_LANGUAGE = "natural_language"
    PRD = "prd"
    JIRA_STORY = "jira_story"
    RAW_DDL = "raw_ddl"


class ExportFormat(str, enum.Enum):
    """Supported artifact export formats (FR-4)."""

    DDL = "ddl"
    DBT = "dbt"
    CUBE = "cube"


class PIIType(str, enum.Enum):
    """Privacy classification flags (FR-6.1)."""

    EMAIL = "EMAIL"
    SSN = "SSN"
    PHONE = "PHONE"
    CREDIT_CARD = "CREDIT_CARD"
    IBAN = "IBAN"
    NAME = "NAME"
    ADDRESS = "ADDRESS"


# ---------------------------------------------------------------------------
# Core representations (shared by API + LLM output)
# ---------------------------------------------------------------------------
class ColumnSchema(BaseModel):
    """A single attribute column within an entity."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    name: str = Field(..., description="Column name.", max_length=128)
    data_type: str = Field(..., description="Physical data type.", max_length=64)
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_pii: bool = False
    pii_type: PIIType | None = None
    description: str | None = None
    ordinal_position: int | None = Field(
        default=None, ge=0, description="Column order within the entity."
    )
    # Optional dimensional/vault hints preserved across paradigm switches.
    references: str | None = Field(
        default=None, description="Qualified target, e.g. 'dim_customer.customer_hk'."
    )
    is_metric: bool = False
    aggregation: str | None = None

    @field_validator("pii_type", mode="after")
    @classmethod
    def _pii_type_requires_flag(
        cls, value: PIIType | None, info
    ) -> PIIType | None:
        """A ``pii_type`` is only meaningful when ``is_pii`` is set."""
        if value is not None and not info.data.get("is_pii", False):
            # Auto-correct rather than reject: a typed column is PII by definition.
            info.data["is_pii"] = True
        return value


class EntitySchema(BaseModel):
    """An entity node (table / fact / dimension / hub / link / satellite)."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    entity_name: str = Field(..., max_length=128)
    entity_type: EntityType = EntityType.TABLE
    description: str | None = None
    grain: str | None = Field(
        default=None, description="Grain statement for FACT entities."
    )
    canvas_position_x: float = 0.0
    canvas_position_y: float = 0.0
    columns: list[ColumnSchema] = Field(default_factory=list)

    @field_validator("columns")
    @classmethod
    def _at_least_one_column(
        cls, value: list[ColumnSchema]
    ) -> list[ColumnSchema]:
        """Reject entities with no columns — topologically invalid."""
        if not value:
            raise ValueError("Entity must declare at least one column.")
        return value


class RelationshipSchema(BaseModel):
    """A directed relationship edge between two entities.

    Accepts the LLM's ``from``/``to`` JSON keys (reserved words) via aliases,
    while still allowing construction by field name in Python.
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True,
    )

    from_ref: str = Field(
        ..., alias="from", description="Source, e.g. 'fact_orders.customer_hk'."
    )
    to_ref: str = Field(
        ..., alias="to", description="Target, e.g. 'dim_customer.customer_hk'."
    )
    cardinality: Cardinality


class SuggestedMetric(BaseModel):
    """A semantic-layer metric suggested during synthesis."""

    model_config = ConfigDict(use_enum_values=True)

    name: str
    formula: str
    group_by: str | None = None


# ---------------------------------------------------------------------------
# Structured LLM output (Instructor response_model)
# ---------------------------------------------------------------------------
class SynthesizedModel(BaseModel):
    """Rigid structured output returned by the LLM via Instructor.

    Used directly as the Instructor ``response_model`` so malformed LLM output
    triggers automatic re-prompting rather than silent corruption.
    """

    model_config = ConfigDict(use_enum_values=True)

    paradigm: Paradigm
    entities: list[EntitySchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    suggested_metrics: list[SuggestedMetric] = Field(default_factory=list)

    @field_validator("entities")
    @classmethod
    def _non_empty(cls, value: list[EntitySchema]) -> list[EntitySchema]:
        if not value:
            raise ValueError("Synthesized model must contain at least one entity.")
        return value


# ---------------------------------------------------------------------------
# Validation report (graph engine output — see services.graph_engine)
# ---------------------------------------------------------------------------
class ValidationIssue(BaseModel):
    """A single topological/lint issue detected on the model graph."""

    model_config = ConfigDict(use_enum_values=True)

    severity: str = Field(..., description="'error' | 'warning'.")
    code: str = Field(..., description="Machine code, e.g. 'CYCLIC_FK'.")
    message: str
    entities: list[str] = Field(default_factory=list)
    # Precise source location (populated for DANGLING_REF): the existing entity
    # and column that hold the invalid reference, so the canvas can mark the row.
    entity_name: str | None = None
    column_name: str | None = None


class ValidationReport(BaseModel):
    """Aggregated validation result for a model graph (FR-2.3)."""

    model_config = ConfigDict(use_enum_values=True)

    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response contracts
# ---------------------------------------------------------------------------
class SynthesizeRequest(BaseModel):
    """POST /api/v1/model/synthesize request body (Blueprint §6)."""

    model_config = ConfigDict(use_enum_values=True)

    source_type: SourceType = SourceType.NATURAL_LANGUAGE
    content: str = Field(..., min_length=1, description="Raw source text/PRD/DDL.")
    target_paradigm: Paradigm = Paradigm.KIMBALL
    dialect: str = Field(default="snowflake", max_length=64)
    workspace_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    # Named provider from model_router.yaml, e.g. 'anthropic_cloud'.
    llm_override: str | None = None


class SynthesizeResponse(BaseModel):
    """POST /api/v1/model/synthesize response body."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    model_id: uuid.UUID
    paradigm: Paradigm
    entities: list[EntitySchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)
    suggested_metrics: list[SuggestedMetric] = Field(default_factory=list)
    # Topological/structural lint report for the graph (FR-2.3).
    validation: ValidationReport | None = None


class TransformOptions(BaseModel):
    """Optional knobs for paradigm transformation (TRD §2.4)."""

    model_config = ConfigDict(extra="allow")

    hash_key_algorithm: str = "SHA256"
    satellite_split_strategy: str = "BY_UPDATE_FREQUENCY"


class TransformParadigmRequest(BaseModel):
    """POST /api/v1/model/{model_id}/transform-paradigm request body."""

    model_config = ConfigDict(use_enum_values=True)

    target_paradigm: Paradigm
    preserve_descriptions: bool = True
    options: TransformOptions = Field(default_factory=TransformOptions)


class TransformParadigmResponse(BaseModel):
    """POST /api/v1/model/{model_id}/transform-paradigm response body."""

    model_config = ConfigDict(use_enum_values=True)

    model_id: uuid.UUID
    previous_paradigm: Paradigm | None
    new_paradigm: Paradigm
    generated_entities_count: int = Field(..., ge=0)
    entities: list[EntitySchema] = Field(default_factory=list)
    transformation_execution_time_ms: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# Artifact export contract
# ---------------------------------------------------------------------------
class ExportResponse(BaseModel):
    """GET /api/v1/model/{model_id}/export response body (FR-4)."""

    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())

    model_id: uuid.UUID
    format: ExportFormat
    # Only meaningful for SQL DDL exports; null for dbt/cube.
    dialect: str | None = None
    # Map of artifact file path -> file contents.
    files: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "Paradigm",
    "EntityType",
    "Cardinality",
    "SourceType",
    "PIIType",
    "ExportFormat",
    "ExportResponse",
    "ColumnSchema",
    "EntitySchema",
    "RelationshipSchema",
    "SuggestedMetric",
    "SynthesizedModel",
    "SynthesizeRequest",
    "SynthesizeResponse",
    "TransformOptions",
    "TransformParadigmRequest",
    "TransformParadigmResponse",
    "ValidationIssue",
    "ValidationReport",
]
