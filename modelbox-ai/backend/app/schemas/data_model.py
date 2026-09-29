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
import logging
import re
import uuid
from collections.abc import Mapping
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)


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
    # The most the key may do. Never above the creator's current role, and the
    # key's effective role is always the lower of the two on each request.
    role_cap: Literal["VIEWER", "MEMBER", "APPROVER", "ADMIN", "OWNER"] = "VIEWER"


class ApiKeyInfo(BaseModel):
    """A stored API key (never exposes the secret or hash)."""

    model_config = ConfigDict(from_attributes=True)

    api_key_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    key_prefix: str
    role_cap: str
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


class ArtifactStatusOut(BaseModel):
    """What the appliance has verified about one exportable artifact (F5).

    Served so the export surface can show a status it did not invent. The UI
    previously carried its own copy of which dialects were certified, and a test
    scraped the TSX to check the copy still matched — the label reached the user
    by being retyped.
    """

    variant: str
    family: str
    status: str
    reason: str


class AuditEventOut(BaseModel):
    """One internal audit event, as a reviewer reads it (G11).

    Deliberately not a mirror of the row: `detail` is included because it
    carries the *shape* of a change — which role replaced which, which dialect
    was exported — and deliberately never the resource's contents. The audit
    log records that a model was exported, not the model, which is the same
    rule that keeps the egress ledger a digest rather than a second copy of the
    prompt.
    """

    model_config = ConfigDict(from_attributes=True)

    audit_id: uuid.UUID
    action: str
    outcome: str
    scope: str
    actor_user_id: uuid.UUID | None = None
    actor_email: str | None = None
    workspace_id: uuid.UUID | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    detail: dict | None = None
    occurred_at: datetime.datetime


class AuditEventPage(BaseModel):
    """A page of audit events, with the total so an export can be paged."""

    events: list[AuditEventOut]
    total: int


class EgressEventOut(BaseModel):
    """One row of the egress ledger, as an operator reads it (D4).

    The prompt itself is deliberately absent. The ledger stores a SHA-256 and a
    character count, never the text, so this view can be opened by anyone who
    can see the workspace without re-exposing the content that left. The digest
    still answers "was this the same prompt" across the rows of a failover
    chain, which is the question an operator actually asks.
    """

    model_config = ConfigDict(from_attributes=True)

    egress_id: uuid.UUID
    attempt_id: uuid.UUID
    event: str
    task: str
    provider: str
    egress_class: str
    prompt_sha256: str
    prompt_chars: int
    model_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None
    occurred_at: datetime.datetime


class EgressLedgerPage(BaseModel):
    """A page of ledger rows, plus what the page could not show.

    ``unattributed`` is the count of rows carrying no workspace, which
    workspace scoping cannot return to anybody. Reporting it is the difference
    between "nothing else left the network" and "nothing else that we can
    attribute left the network" — and a governance view that quietly rounds the
    second into the first is worse than no view, because it is believed.
    """

    events: list[EgressEventOut] = Field(default_factory=list)
    total: int
    unattributed: int


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
    flawed_graph: GraphUpdateRequest | None = None
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
    current_graph: GraphUpdateRequest | None = None


class SocraticStepResponse(BaseModel):
    """The tutor's next guiding question — never a full solution (FR-3.1)."""

    next_question: str
    hints: list[str] = Field(default_factory=list)


class GradeRequest(BaseModel):
    """Submit a student ERD for auto-grading (FR-3.3)."""

    assignment_id: uuid.UUID
    submitted_graph: GraphUpdateRequest


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
# Temporal type tokens, matched case-insensitively against a declared physical
# type. Kept in one place because the exporters each carry their own copy of
# this test today (exporter_service._is_temporal, _cube_type, _lookml_type);
# Sprint 3 should collapse them onto this one.
_TEMPORAL_TOKENS = ("TIMESTAMP", "DATETIME", "DATE", "TIME")


def _is_temporal_type(data_type: str) -> bool:
    """Whether a declared physical type denotes a date or time."""
    upper = data_type.upper()
    return any(token in upper for token in _TEMPORAL_TOKENS)


class ColumnSchema(BaseModel):
    """A single attribute column within an entity."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    name: str = Field(..., description="Column name.", max_length=128)
    data_type: str = Field(..., description="Physical data type.", max_length=64)
    # Stable per-entity column identity (Sprint 2, Q6). Allocated once at first
    # persist from a high-water mark on the entity and never reused, so it is
    # safe as a Protobuf field tag and lets the diff engine tell a rename from a
    # drop-plus-add. Server-assigned: absent on a new column, echoed back by the
    # canvas on every subsequent save. Never editable by a client — see
    # GraphRepository for the allocation rules.
    stable_id: int | None = Field(
        default=None,
        ge=1,
        description="Server-assigned stable column identity. Read-only.",
    )
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
    # Quality rules (Sprint U3) — numeric bounds + text format pattern.
    # These declare the data contract's *assertions* and export to dbt tests /
    # ODCS quality blocks; the linter flags contradictory or uncompilable rules.
    min_value: float | None = Field(
        default=None, description="Inclusive lower bound for numeric values."
    )
    max_value: float | None = Field(
        default=None, description="Inclusive upper bound for numeric values."
    )
    regex_pattern: str | None = Field(
        default=None,
        description="Regex the column's values must match.",
        max_length=512,
    )
    # Physical constraints (Sprint 2, H4). Until now the IR could not express
    # any of these, so four exporters guessed and guessed differently: Avro
    # declared every non-key column nullable, Protobuf declared nothing
    # nullable, ODCS restated the primary-key flag, and DDL emitted no
    # constraint at all. Consumed by the emitters in Sprint 3, not here.
    is_nullable: bool = Field(
        default=True,
        description=(
            "Whether the column admits NULL. Defaults to True — the SQL "
            "default, and what the current DDL already implies by emitting no "
            "NOT NULL — so existing models keep their present meaning. Forced "
            "False on primary keys."
        ),
    )
    is_unique: bool = Field(
        default=False,
        description="A UNIQUE constraint applies (independently of the PK).",
    )
    default_value: str | None = Field(
        default=None,
        max_length=512,
        description="Literal or expression used as the column DEFAULT.",
    )
    check_expression: str | None = Field(
        default=None,
        max_length=4000,
        description="Boolean SQL expression the column's values must satisfy.",
    )
    # The type exactly as an imported DDL file declared it (Sprint 8, owner
    # decision): `VARCHAR2(10 BYTE)`, `[nvarchar](60)`, `integer`. `data_type`
    # holds the normalized form, which is what comparisons use; this is what a
    # data dictionary shows. None for a column that was not imported.
    source_data_type: str | None = Field(
        default=None,
        max_length=128,
        description="The column's type exactly as the imported file declared it.",
    )
    # The DEFAULT exactly as an imported file declared it (Sprint 8 Step 3):
    # `nextval('public.actor_actor_id_seq'::regclass)`, `(getdate())`.
    # `default_value` holds the normalized form, which comparisons use.
    source_default_value: str | None = Field(
        default=None,
        max_length=4000,
        description="The column's DEFAULT exactly as the imported file declared it.",
    )

    @model_validator(mode="after")
    def _primary_keys_are_never_nullable(self) -> ColumnSchema:
        """A primary key cannot be NULL, whatever the payload claims.

        Enforced in the IR rather than left to each emitter, because the four
        emitters previously disagreed about exactly this, and Databricks
        rejects a primary key on a nullable column outright.

        A ``model_validator`` rather than a ``field_validator``: Pydantic does
        not validate a field that was never supplied, so as a field validator
        this silently did nothing in the common case — an LLM response or a
        gold graph that simply omits ``is_nullable``. A round-trip through the
        database masked it, because reloading passes every field explicitly and
        the rule fired on the way back; but ``POST /model/synthesize`` returns
        the model directly, so a freshly synthesised primary key stayed
        nullable and Sprint 3 would have emitted no NOT NULL for it.
        """
        if self.is_primary_key and self.is_nullable:
            self.is_nullable = False
        return self

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


class UniqueConstraintSchema(BaseModel):
    """A UNIQUE constraint over one or more of an entity's columns, in order."""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, max_length=128)
    columns: list[str] = Field(..., min_length=1)


class CheckConstraintSchema(BaseModel):
    """A CHECK constraint: a boolean expression over the entity's columns.

    ``columns`` names the columns the expression reads. A constraint over
    exactly one column is also that column's ``check_expression``.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, max_length=128)
    expression: str = Field(..., min_length=1, max_length=4000)
    columns: list[str] = Field(default_factory=list)


_IDENTIFIER = re.compile(r'"([^"]+)"|\[([^\]]+)\]|`([^`]+)`|([A-Za-z_][\w$#]*)')


def columns_read_by(expression: str, names: list[str]) -> list[str]:
    """The entity columns an expression mentions, in the entity's column order.

    Matched exactly first; an unquoted identifier also matches a column that
    differs only in case, as SQL folds unquoted names.
    """
    mentioned: set[str] = set()
    folded: set[str] = set()
    for quoted, bracketed, backticked, bare in _IDENTIFIER.findall(expression):
        exact = quoted or bracketed or backticked
        if exact:
            mentioned.add(exact)
        else:
            mentioned.add(bare)
            folded.add(bare.lower())
    return [n for n in names if n in mentioned or n.lower() in folded]


_ENTITY_DERIVED = frozenset({"is_primary_key", "is_unique", "check_expression"})
_MODEL_DERIVED = frozenset({"is_foreign_key", "references"})


def _joined(expressions: list[str]) -> str | None:
    """One column's check_expression: its single-column CHECKs, conjoined."""
    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]
    return " AND ".join(f"({e})" for e in expressions)


class EntitySchema(BaseModel):
    """An entity node (table / fact / dimension / hub / link / satellite).

    Keys and constraints have one source: ``primary_key``,
    ``unique_constraints`` and ``check_constraints`` here, and the model's
    relationships for foreign keys. The column flags ``is_primary_key``,
    ``is_unique`` and ``check_expression`` are derived from these lists. A
    payload that omits a list is read the older way, from its column flags
    (LLM responses, the gold graphs, trainer labs); a payload that supplies a
    list and a flag contradicting it is refused.
    """

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
    # Default time axis for this entity's measures (Sprint 2). MetricFlow needs
    # `defaults.agg_time_dimension` on any semantic model declaring measures,
    # and its absence is one of B1's four parse blockers.
    #
    # Entity-level rather than a column-level boolean because MetricFlow's
    # construct is one-per-semantic-model: a scalar here makes the invalid state
    # — two columns flagged on one entity — unrepresentable. MetricFlow's
    # per-measure override also names a dimension rather than flagging one, so a
    # boolean would be the wrong shape even for that case.
    #
    # Legitimately None: an entity with no temporal column has no time axis, and
    # Sprint 3's emitter gives those no measures rather than inventing one.
    agg_time_column: str | None = Field(
        default=None,
        max_length=128,
        description="Name of this entity's default aggregation time dimension.",
    )
    canvas_position_x: float = 0.0
    canvas_position_y: float = 0.0
    columns: list[ColumnSchema] = Field(default_factory=list)
    primary_key: list[str] = Field(
        default_factory=list, description="The primary key's columns, in key order."
    )
    unique_constraints: list[UniqueConstraintSchema] = Field(default_factory=list)
    check_constraints: list[CheckConstraintSchema] = Field(default_factory=list)

    @field_validator("columns")
    @classmethod
    def _at_least_one_column(
        cls, value: list[ColumnSchema]
    ) -> list[ColumnSchema]:
        """Reject entities with no columns — topologically invalid."""
        if not value:
            raise ValueError("Entity must declare at least one column.")
        return value

    @model_validator(mode="after")
    def _keys_and_constraints_have_one_source(self) -> EntitySchema:
        """Read the lists, or build them from the flags; then derive the flags."""
        names = [c.name for c in self.columns]
        known = set(names)
        supplied = self.model_fields_set

        def require_known(columns: list[str], what: str) -> None:
            unknown = [c for c in columns if c not in known]
            if unknown:
                raise ValueError(f"{self.entity_name}: {what} names columns it does not have: {unknown}")
            if len(set(columns)) != len(columns):
                raise ValueError(f"{self.entity_name}: {what} repeats a column: {columns}")

        def contradicts(flag: str, derived: Mapping[str, object]) -> None:
            for column in self.columns:
                if flag in column.model_fields_set and getattr(column, flag) != derived[column.name]:
                    raise ValueError(
                        f"{self.entity_name}.{column.name}: {flag}={getattr(column, flag)!r} contradicts "
                        f"the entity's constraints, which give {derived[column.name]!r}")

        if "primary_key" in supplied:
            require_known(self.primary_key, "primary_key")
            contradicts("is_primary_key", {n: n in self.primary_key for n in names})
        else:
            self.primary_key = [c.name for c in self.columns if c.is_primary_key]

        if "unique_constraints" in supplied:
            for unique in self.unique_constraints:
                require_known(unique.columns, "a UNIQUE constraint")
        else:
            self.unique_constraints = [UniqueConstraintSchema(columns=[c.name]) for c in self.columns if c.is_unique]
        single_unique = {u.columns[0] for u in self.unique_constraints if len(u.columns) == 1}
        if "unique_constraints" in supplied:
            contradicts("is_unique", {n: n in single_unique for n in names})

        if "check_constraints" in supplied:
            for check in self.check_constraints:
                if check.columns:
                    require_known(check.columns, "a CHECK constraint")
                else:
                    check.columns = columns_read_by(check.expression, names)
        else:
            self.check_constraints = [CheckConstraintSchema(expression=c.check_expression, columns=[c.name])
                                      for c in self.columns if c.check_expression]
        per_column = {n: _joined([k.expression for k in self.check_constraints if k.columns == [n]]) for n in names}
        if "check_constraints" in supplied:
            contradicts("check_expression", per_column)

        for column in self.columns:
            column.is_primary_key = column.name in self.primary_key
            if column.is_primary_key:
                column.is_nullable = False
            column.is_unique = column.name in single_unique
            column.check_expression = per_column[column.name]
            # Derived, not supplied: a later reading of this object must not
            # take them for input (assignment would otherwise mark them set).
            column.__pydantic_fields_set__.difference_update(_ENTITY_DERIVED)
        return self

    @model_validator(mode="after")
    def _agg_time_column_is_a_temporal_column(self) -> EntitySchema:
        """Drop an aggregation time dimension that cannot be honoured.

        An ``agg_time_column`` naming a column that does not exist, or one that
        is not a date or time, is unemittable — MetricFlow would reject it. It
        is **discarded with a warning rather than raised**, and the entity
        becomes dimension-only.

        Rejecting looks stricter and is worse. This model is the Instructor
        ``response_model`` for synthesis, so a raise fails the whole
        ``SynthesizedModel``: one hallucinated column name from a weaker local
        model and the user gets no schema at all instead of a good schema with
        one hint missing. "LLM-agnostic" is a claim this would quietly break,
        and the damage would first appear in Sprint 5's provider conformance
        report looking like a model-quality problem rather than a schema
        decision made here.

        Nothing is lost on the canvas path: the entity editor offers only that
        entity's temporal columns, so the UI cannot produce a value this
        discards.
        """
        if self.agg_time_column is None:
            return self
        column = next(
            (c for c in self.columns if c.name == self.agg_time_column), None
        )
        if column is None:
            logger.warning(
                "Discarding agg_time_column %r on entity %r: no such column.",
                self.agg_time_column,
                self.entity_name,
            )
            self.agg_time_column = None
        elif not _is_temporal_type(column.data_type):
            logger.warning(
                "Discarding agg_time_column %r on entity %r: %s is not a date "
                "or time type.",
                self.agg_time_column,
                self.entity_name,
                column.data_type,
            )
            self.agg_time_column = None
        return self


class RelationshipSchema(BaseModel):
    """A directed relationship: a foreign key from one entity's columns to another's.

    ``from`` and ``to`` name the entities; ``from_columns`` and ``to_columns``
    pair up position by position, so a composite foreign key is one
    relationship. The older form, ``"entity.column"`` in ``from`` / ``to``, is
    still accepted and read as a one-column pair.

    A relationship without a complete column pairing is **unresolved**: it
    records that two entities are related without saying by which columns
    (every edge drawn on the canvas before Sprint 8 Step 3). It is kept, the
    linter reports it, and exporters list it as an export gap.

    Accepts the LLM's ``from``/``to`` JSON keys (reserved words) via aliases,
    while still allowing construction by field name in Python.
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True,
    )

    from_ref: str = Field(
        ..., alias="from", description="Source entity, e.g. 'fact_orders'."
    )
    to_ref: str = Field(
        ..., alias="to", description="Target entity, e.g. 'dim_customer'."
    )
    from_columns: list[str] = Field(
        default_factory=list, description="The referencing columns, in key order."
    )
    to_columns: list[str] = Field(
        default_factory=list, description="The referenced columns, paired by position."
    )
    name: str | None = Field(default=None, max_length=128)
    cardinality: Cardinality
    # True when the columns came from an older "entity.column" ref, or there
    # are none: the payload stated no column lists of its own.
    _stated_no_columns: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def _entity_refs_and_column_lists(self) -> RelationshipSchema:
        stated = {"from_columns", "to_columns"} & self.model_fields_set
        for side in ("from", "to"):
            ref: str = getattr(self, f"{side}_ref")
            if "." not in ref:
                continue
            entity, column = ref.split(".", 1)
            columns: list[str] = getattr(self, f"{side}_columns")
            if f"{side}_columns" in stated and columns != [column]:
                raise ValueError(f"{side} {ref!r} contradicts {side}_columns {columns}")
            setattr(self, f"{side}_ref", entity)
            setattr(self, f"{side}_columns", [column])
            # Derived from the ref, not supplied. Pydantic runs this validator
            # again when the instance is placed in a parent model, and must
            # still see an older-form relationship there.
            self.__pydantic_fields_set__.discard(f"{side}_columns")
        if self.from_columns and self.to_columns and len(self.from_columns) != len(self.to_columns):
            raise ValueError(
                f"{self.from_ref} -> {self.to_ref}: {len(self.from_columns)} referencing columns "
                f"but {len(self.to_columns)} referenced")
        self._stated_no_columns = not stated
        return self

    @classmethod
    def between(
        cls,
        from_entity: str,
        from_columns: list[str],
        to_entity: str,
        to_columns: list[str],
        cardinality: Cardinality | str,
        name: str | None = None,
    ) -> RelationshipSchema:
        """A relationship stated with its column lists (validated, by alias)."""
        return cls.model_validate({
            "from": from_entity, "from_columns": list(from_columns),
            "to": to_entity, "to_columns": list(to_columns),
            "cardinality": getattr(cardinality, "value", cardinality), "name": name,
        })

    @property
    def resolved(self) -> bool:
        """Whether every referencing column is paired with a referenced one."""
        return bool(self.from_columns) and len(self.from_columns) == len(self.to_columns)

    @property
    def pairs(self) -> list[tuple[str, str]]:
        return list(zip(self.from_columns, self.to_columns, strict=False))


def unify_foreign_keys(
    entities: list[EntitySchema], relationships: list[RelationshipSchema]
) -> list[RelationshipSchema]:
    """Make the relationships the one source of foreign keys; derive the column flags.

    Read the older way when no relationship states column lists of its own:
    a column's ``references`` that no relationship backs becomes an N:1
    relationship (the linter reports it if its target does not exist), and an
    ``is_foreign_key`` with no target at all is dropped with a warning, as
    ``agg_time_column`` is. When the payload states column lists, a flag that
    disagrees with them is refused.
    """
    relationships = list(relationships)
    older_form = all(r._stated_no_columns for r in relationships)

    def backed_by(entity: str, column: str) -> list[tuple[RelationshipSchema, int]]:
        return [(r, i) for r in relationships if r.from_ref == entity
                for i, c in enumerate(r.from_columns) if c == column]

    if older_form:
        for entity in entities:
            for column in entity.columns:
                supplied = "references" in column.model_fields_set
                if supplied and column.references and not backed_by(entity.entity_name, column.name):
                    target = column.references.split(".", 1)
                    relationships.append(RelationshipSchema.between(
                        entity.entity_name, [column.name], target[0], target[1:], Cardinality.MANY_TO_ONE))
                elif ("is_foreign_key" in column.model_fields_set and column.is_foreign_key
                      and not backed_by(entity.entity_name, column.name)):
                    logger.warning("Dropping is_foreign_key on %s.%s: no relationship or reference "
                                   "names its target.", entity.entity_name, column.name)

    derived: dict[tuple[str, str], str | None] = {}
    for relationship in relationships:
        for i, from_column in enumerate(relationship.from_columns):
            to_column = relationship.to_columns[i] if i < len(relationship.to_columns) else None
            derived[(relationship.from_ref, from_column)] = (
                f"{relationship.to_ref}.{to_column}" if to_column else None)
    for entity in entities:
        for column in entity.columns:
            key = (entity.entity_name, column.name)
            is_fk, references = key in derived, derived.get(key)
            if not older_form:
                for flag, value in (("is_foreign_key", is_fk), ("references", references)):
                    if flag in column.model_fields_set and getattr(column, flag) != value:
                        raise ValueError(
                            f"{entity.entity_name}.{column.name}: {flag}={getattr(column, flag)!r} "
                            f"contradicts the relationships, which give {value!r}")
            column.is_foreign_key, column.references = is_fk, references
            column.__pydantic_fields_set__.difference_update(_MODEL_DERIVED)
    return relationships


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

    @model_validator(mode="after")
    def _foreign_keys_have_one_source(self) -> SynthesizedModel:
        self.relationships = unify_foreign_keys(self.entities, self.relationships)
        return self


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

    entities: list[EntitySchema] = Field(default_factory=list)
    relationships: list[RelationshipSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def _foreign_keys_have_one_source(self) -> GraphUpdateRequest:
        self.relationships = unify_foreign_keys(self.entities, self.relationships)
        return self


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


class ConversionFinding(BaseModel):
    """Something migration 0025 could not convert exactly; the model keeps it."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    entity_name: str | None = None
    detail: str


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
    # What migration 0025 could not convert in this model, kept and listed.
    conversion_findings: list[ConversionFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _foreign_keys_have_one_source(self) -> SynthesizeResponse:
        self.relationships = unify_foreign_keys(self.entities, self.relationships)
        return self


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
class ExportGapSchema(BaseModel):
    """One thing an export could not state: its kind, entity and reason."""

    kind: str
    entity: str | None = None
    detail: str


class ExportResponse(BaseModel):
    """GET /api/v1/model/{model_id}/export response body (FR-4)."""

    model_config = ConfigDict(use_enum_values=True, protected_namespaces=())

    model_id: uuid.UUID
    format: ExportFormat
    # Only meaningful for SQL DDL exports; null for dbt/cube.
    dialect: str | None = None
    # Map of artifact file path -> file contents.
    files: dict[str, str] = Field(default_factory=dict)
    # What the model holds that the DDL does not state, and why (Sprint 8
    # Step 3). The same list heads the SQL file as comments.
    gaps: list[ExportGapSchema] = Field(default_factory=list)


__all__ = [
    "ApiKeyCreateRequest",
    "ApiKeyCreatedResponse",
    "ApiKeyInfo",
    "AssetTier",
    "AssignmentCreateRequest",
    "AssignmentInfo",
    "Cardinality",
    "ColumnSchema",
    "ConnectionCreateRequest",
    "ConnectionInfo",
    "ContractExportResponse",
    "ContractFormat",
    "DictionaryExportResponse",
    "DictionaryFormat",
    "DiffRequest",
    "DiffResponse",
    "EntitySchema",
    "EntityType",
    "ExportFormat",
    "ExportResponse",
    "GradeRequest",
    "GradeResponse",
    "GraphUpdateRequest",
    "IntrospectRequest",
    "JobCreatedResponse",
    "JobStatusResponse",
    "ModelInfo",
    "ModelUpdateRequest",
    "PIIType",
    "Paradigm",
    "RegisterRequest",
    "RelationshipSchema",
    "SeedFormat",
    "SemanticEngine",
    "SemanticExportResponse",
    "SocraticStepRequest",
    "SocraticStepResponse",
    "SourceType",
    "SuggestedMetric",
    "SynthesizeRequest",
    "SynthesizeResponse",
    "SynthesizedModel",
    "SyntheticSeedRequest",
    "SyntheticSeedResponse",
    "Token",
    "TransformOptions",
    "TransformParadigmRequest",
    "TransformParadigmResponse",
    "UserOut",
    "ValidationIssue",
    "ValidationReport",
    "WorkspaceInfo",
]
