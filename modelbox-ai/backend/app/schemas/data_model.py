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

import datetime
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


class AssetTier(str, enum.Enum):
    """Data-asset criticality tier (governance)."""

    TIER_1_CRITICAL = "TIER_1_CRITICAL"
    TIER_2_IMPORTANT = "TIER_2_IMPORTANT"
    TIER_3_STANDARD = "TIER_3_STANDARD"
    TIER_4_EXPERIMENTAL = "TIER_4_EXPERIMENTAL"


class Cardinality(str, enum.Enum):
    """Relationship cardinalities (direction is from_ref -> to_ref)."""

    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_ONE = "N:1"
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


# ---------------------------------------------------------------------------
# Authentication contracts (Slice 3B)
# ---------------------------------------------------------------------------
class Token(BaseModel):
    """OAuth2 bearer token response."""

    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Local account registration payload."""

    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserOut(BaseModel):
    """Public user representation."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    full_name: str | None = None


# ---------------------------------------------------------------------------
# API keys (programmatic access)
# ---------------------------------------------------------------------------
class ApiKeyCreateRequest(BaseModel):
    """Create a programmatic API key."""

    name: str = Field(..., min_length=1, max_length=120)
    workspace_id: uuid.UUID | None = None
    expires_at: datetime.datetime | None = None


class ApiKeyInfo(BaseModel):
    """A stored API key (never exposes the secret or hash)."""

    model_config = ConfigDict(from_attributes=True)

    api_key_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime.datetime
    expires_at: datetime.datetime | None = None
    last_used_at: datetime.datetime | None = None


class ApiKeyCreatedResponse(ApiKeyInfo):
    """API key creation response — includes the plaintext secret ONCE."""

    api_key: str


class ModelUpdateRequest(BaseModel):
    """PATCH body for model metadata (RBAC — Slice B2)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    target_dialect: str | None = Field(default=None, min_length=1, max_length=64)


class ModelInfo(BaseModel):
    """Lightweight model metadata (no entity graph)."""

    model_config = ConfigDict(
        from_attributes=True, use_enum_values=True, protected_namespaces=()
    )

    model_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    current_paradigm: str | None = None
    target_dialect: str
    version_number: int


class WorkspaceInfo(BaseModel):
    """A workspace the caller belongs to, with their role."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: uuid.UUID
    name: str
    role: str


class JobCreatedResponse(BaseModel):
    """202 response when an async synthesis job is enqueued (FR-1.1)."""

    model_config = ConfigDict(protected_namespaces=())

    job_id: uuid.UUID
    status: str
    poll_url: str


class JobStatusResponse(BaseModel):
    """Async job status for polling (FR-1.1)."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    job_id: uuid.UUID
    status: str
    result_model_id: uuid.UUID | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# ModelBox Trainer (Pillar 3) — isolated teaching/learning contracts
# ---------------------------------------------------------------------------
class AssignmentCreateRequest(BaseModel):
    """Create a trainer assignment (FR-3.2)."""

    model_config = ConfigDict(use_enum_values=True)

    title: str = Field(..., min_length=1, max_length=150)
    description: str = Field(..., min_length=1)
    workspace_id: uuid.UUID | None = None
    # Optional defective seed graph for "Spot the Flaw" mode.
    flawed_graph: "GraphUpdateRequest | None" = None
    # e.g. {"NO_CYCLIC_FK": true, "PK_PRESENT": true, "NO_DANGLING_REF": true}
    expected_invariants: dict[str, bool] = Field(default_factory=dict)


class AssignmentInfo(BaseModel):
    """Assignment as returned to instructors/learners."""

    model_config = ConfigDict(from_attributes=True)

    assignment_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str
    flawed_graph_json: dict | None = None
    expected_graph_invariants: dict


class SocraticStepRequest(BaseModel):
    """One turn of Socratic tutoring (FR-3.1)."""

    assignment_id: uuid.UUID
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    current_graph: "GraphUpdateRequest | None" = None


class SocraticStepResponse(BaseModel):
    """The tutor's next guiding question — never a full solution (FR-3.1)."""

    next_question: str
    hints: list[str] = Field(default_factory=list)


class GradeRequest(BaseModel):
    """Submit a student ERD for auto-grading (FR-3.3)."""

    assignment_id: uuid.UUID
    submitted_graph: "GraphUpdateRequest"


class GradeResponse(BaseModel):
    """Structured rubric result (FR-3.3)."""

    score: float
    passed_invariants: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Brownfield introspection (Phase 2, FR-2.1)
# ---------------------------------------------------------------------------
class ConnectionCreateRequest(BaseModel):
    """Register an external database connection."""

    name: str = Field(..., min_length=1, max_length=100)
    engine: str = Field(..., max_length=30)
    connection_uri: str = Field(..., min_length=1)
    workspace_id: uuid.UUID | None = None


class ConnectionInfo(BaseModel):
    """A stored connection (URI masked — never returned in the clear)."""

    model_config = ConfigDict(from_attributes=True)

    connection_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    engine: str
    uri_masked: str | None = None


class IntrospectRequest(BaseModel):
    """Pull a schema from a saved connection into a model."""

    connection_id: uuid.UUID
    schema_name: str = "public"


# ---------------------------------------------------------------------------
# Schema diffing & migration (Phase 2, FR-2.2)
# ---------------------------------------------------------------------------
class DiffRequest(BaseModel):
    """Diff two persisted models (V1 source -> V2 target)."""

    model_config = ConfigDict(protected_namespaces=())

    source_model_id: uuid.UUID
    target_model_id: uuid.UUID
    dialect: str = Field(default="postgres", max_length=64)


class DiffResponse(BaseModel):
    """Migration DDL + breaking-change report for a model diff (FR-2.2)."""

    model_config = ConfigDict(protected_namespaces=())

    source_model_id: uuid.UUID
    target_model_id: uuid.UUID
    dialect: str
    alter_statements: list[str] = Field(default_factory=list)
    breaking_changes: list[str] = Field(default_factory=list)
    # In-model semantic-layer impact (declared measures / metric formulas).
    semantic_breaks: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Synthetic seed data (Phase 2, FR-2.4)
# ---------------------------------------------------------------------------
class SeedFormat(str, enum.Enum):
    """Emission formats for synthetic seed data (FR-2.4)."""

    SQL_INSERT = "sql_insert"
    CSV = "csv"


class SyntheticSeedRequest(BaseModel):
    """POST /model/{id}/export/synthetic-data request body (FR-2.4)."""

    model_config = ConfigDict(use_enum_values=True)

    row_count_per_entity: int = Field(default=50, ge=1, le=1000)
    format: SeedFormat = SeedFormat.SQL_INSERT
    dialect: str = Field(default="postgres", max_length=64)


class SyntheticSeedResponse(BaseModel):
    """Generated seed script / CSV bundle (FR-2.4)."""

    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())

    model_id: uuid.UUID
    format: SeedFormat
    dialect: str
    row_count_per_entity: int
    # FK-safe order in which entities were populated (parents first).
    generation_order: list[str] = Field(default_factory=list)
    # Map of artifact file path -> file contents.
    files: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Data contracts & semantic layers (Phase 3, FR-2.3)
# ---------------------------------------------------------------------------
class ContractFormat(str, enum.Enum):
    """Governance data-contract formats (FR-2.3)."""

    OPENDATACONTRACT = "opendatacontract"
    AVRO = "avro"
    PROTOBUF = "protobuf"


class SemanticEngine(str, enum.Enum):
    """Semantic-layer target engines (FR-2.3)."""

    CUBE = "cube"
    LOOKML = "lookml"
    METRICFLOW = "metricflow"


class ContractExportResponse(BaseModel):
    """A generated data contract (FR-2.3)."""

    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())

    model_id: uuid.UUID
    format: ContractFormat
    files: dict[str, str] = Field(default_factory=dict)


class SemanticExportResponse(BaseModel):
    """A generated semantic-layer definition (FR-2.3)."""

    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())

    model_id: uuid.UUID
    engine: SemanticEngine
    files: dict[str, str] = Field(default_factory=dict)


class DictionaryFormat(str, enum.Enum):
    """Data-dictionary output formats (Pick 2)."""

    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


class DictionaryExportResponse(BaseModel):
    """A generated data dictionary + business glossary (Pick 2)."""

    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())

    model_id: uuid.UUID
    format: DictionaryFormat
    files: dict[str, str] = Field(default_factory=dict)


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
    # Governance metadata (Sprint U2): asset criticality + freshness SLA.
    tier: AssetTier | None = None
    freshness_sla: str | None = Field(
        default=None, description="Freshness SLA, e.g. '< 1h'.", max_length=64
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
class GraphUpdateRequest(BaseModel):
    """PUT /api/v1/model/{id}/graph — full replacement of a model's graph.

    Carries the canvas's current entities + relationships (FR-1.2).
    """

    model_config = ConfigDict(use_enum_values=True)

    entities: list["EntitySchema"] = Field(default_factory=list)
    relationships: list["RelationshipSchema"] = Field(default_factory=list)


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
    "AssetTier",
    "Cardinality",
    "SourceType",
    "PIIType",
    "ExportFormat",
    "ExportResponse",
    "Token",
    "RegisterRequest",
    "UserOut",
    "ModelUpdateRequest",
    "ModelInfo",
    "WorkspaceInfo",
    "ApiKeyCreateRequest",
    "ApiKeyInfo",
    "ApiKeyCreatedResponse",
    "JobCreatedResponse",
    "JobStatusResponse",
    "AssignmentCreateRequest",
    "AssignmentInfo",
    "SocraticStepRequest",
    "SocraticStepResponse",
    "GradeRequest",
    "GradeResponse",
    "ColumnSchema",
    "EntitySchema",
    "RelationshipSchema",
    "SuggestedMetric",
    "SynthesizedModel",
    "SynthesizeRequest",
    "SynthesizeResponse",
    "GraphUpdateRequest",
    "TransformOptions",
    "TransformParadigmRequest",
    "TransformParadigmResponse",
    "ValidationIssue",
    "ValidationReport",
    "ConnectionCreateRequest",
    "ConnectionInfo",
    "IntrospectRequest",
    "DiffRequest",
    "DiffResponse",
    "SeedFormat",
    "SyntheticSeedRequest",
    "SyntheticSeedResponse",
    "ContractFormat",
    "SemanticEngine",
    "ContractExportResponse",
    "SemanticExportResponse",
    "DictionaryFormat",
    "DictionaryExportResponse",
]
