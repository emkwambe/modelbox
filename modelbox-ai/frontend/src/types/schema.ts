/**
 * Shared domain types for ModelBox AI.
 *
 * These interfaces mirror the backend Pydantic v2 contracts
 * (`backend/app/schemas/data_model.py`) so payloads round-trip without
 * translation. String-literal unions match the exact wire values emitted by
 * the backend (`use_enum_values=True`) and enforced by the PostgreSQL CHECK
 * constraints.
 */

import type { Node, Edge } from '@xyflow/react';

// ---------------------------------------------------------------------------
// Enumerations (wire-value string unions)
// ---------------------------------------------------------------------------
export type Paradigm = '3NF' | 'KIMBALL' | 'DATA_VAULT' | 'OBT';

export type EntityType =
  | 'TABLE'
  | 'FACT'
  | 'DIMENSION'
  | 'HUB'
  | 'LINK'
  | 'SATELLITE';

export type Cardinality = '1:1' | '1:N' | 'N:1' | 'N:M';

export type AssetTier =
  | 'TIER_1_CRITICAL'
  | 'TIER_2_IMPORTANT'
  | 'TIER_3_STANDARD'
  | 'TIER_4_EXPERIMENTAL';

export type SourceType =
  | 'natural_language'
  | 'prd'
  | 'jira_story'
  | 'raw_ddl';

export type PIIType =
  | 'EMAIL'
  | 'SSN'
  | 'PHONE'
  | 'CREDIT_CARD'
  | 'IBAN'
  | 'NAME'
  | 'ADDRESS';

export type ExportFormat = 'ddl' | 'dbt' | 'cube';

// Governance & migration mesh (Phase 2/3) wire-value unions.
export type ConnectionEngine =
  | 'POSTGRESQL'
  | 'SNOWFLAKE'
  | 'BIGQUERY'
  | 'MYSQL';

export type SeedFormat = 'sql_insert' | 'csv';

export type ContractFormat = 'opendatacontract' | 'avro' | 'protobuf';

export type SemanticEngine = 'cube' | 'lookml' | 'metricflow';

export type DictionaryFormat = 'markdown' | 'html' | 'json' | 'csv';

// ---------------------------------------------------------------------------
// Core domain shapes
// ---------------------------------------------------------------------------
/**
 * Keys and constraints (Sprint 8 Step 3) have one source: the entity's
 * `primary_key`, `unique_constraints` and `check_constraints`, and the model's
 * relationships for foreign keys. The column flags below
 * (`is_primary_key`, `is_unique`, `check_expression`, `is_foreign_key`,
 * `references`) are derived from those by the server. The canvas edits the
 * one-column flags and `getGraphPayload` turns them back into lists; it never
 * sends the flags, because a flag that disagrees with a list is refused.
 */
export interface Column {
  name: string;
  data_type: string;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  is_pii: boolean;
  pii_type?: PIIType | null;
  description?: string | null;
  ordinal_position?: number | null;
  references?: string | null;
  is_metric: boolean;
  aggregation?: string | null;
  // Quality rules (Sprint U3) — numeric bounds + text format pattern.
  min_value?: number | null;
  max_value?: number | null;
  regex_pattern?: string | null;
  /**
   * Server-assigned stable identity (Sprint 2). Allocated once and never
   * reused, so it is safe as a Protobuf field tag and lets the diff engine
   * tell a rename from a drop-plus-add. Echo it back unchanged on save;
   * never edit it, and never invent one for a new column.
   */
  stable_id?: number | null;
  // Physical constraints (Sprint 2). is_nullable defaults to true — the SQL
  // default — and is forced false on primary keys by the server.
  is_nullable?: boolean;
  is_unique?: boolean;
  default_value?: string | null;
  check_expression?: string | null;
  /** The type exactly as an imported DDL file declared it; null if not imported. */
  source_data_type?: string | null;
  /** The DEFAULT exactly as an imported DDL file declared it; null if not imported. */
  source_default_value?: string | null;
  /**
   * How an imported column's values are generated: an identity column's
   * generation, seed and increment, or the Oracle trigger and sequence that
   * fill it. Set by the importer only; the canvas echoes it back unchanged.
   */
  identity?: ColumnIdentity | null;
  /** A computed column's expression exactly as the imported file declared it. */
  computed_expression?: string | null;
  /** Whether the source stores the computed value (SQL Server PERSISTED). */
  computed_persisted?: boolean | null;
  // Dictionary fields a person supplies (Sprint 8 Step 4b).
  business_name?: string | null;
  /** The values the column may hold: a JSON list. */
  permissible_values?: (string | number | boolean)[] | null;
  unit?: string | null;
  /** Critical data element; null means not assessed, which is not "no". */
  critical_data_element?: boolean | null;
  authoritative_source?: string | null;
  /** A level of the workspace's classification scale, by id. */
  classification_level_id?: string | null;
}

export interface ColumnIdentity {
  kind: 'identity' | 'trigger';
  generation?: 'ALWAYS' | 'BY DEFAULT' | null;
  on_null?: boolean;
  start?: number | null;
  increment?: number | null;
  sequence?: string | null;
  trigger?: string | null;
}

export interface UniqueConstraint {
  name?: string | null;
  columns: string[];
}

export interface CheckConstraint {
  name?: string | null;
  expression: string;
  /** The columns the expression reads. */
  columns?: string[];
}

export interface Entity {
  entity_name: string;
  entity_type: EntityType;
  description?: string | null;
  grain?: string | null;
  tier?: AssetTier | null;
  freshness_sla?: string | null;
  /**
   * Default aggregation time dimension: the name of a temporal column on this
   * entity. MetricFlow requires `defaults.agg_time_dimension` on any semantic
   * model declaring measures. Null is legitimate — an entity with no temporal
   * column has no time axis, and gets no measures rather than an invented one.
   */
  agg_time_column?: string | null;
  // Dictionary fields a person supplies (Sprint 8 Step 4b).
  business_name?: string | null;
  business_owner?: string | null;
  it_steward?: string | null;
  authoritative_source?: string | null;
  canvas_position_x: number;
  canvas_position_y: number;
  columns: Column[];
  /** The primary key's columns, in key order. */
  primary_key?: string[];
  unique_constraints?: UniqueConstraint[];
  check_constraints?: CheckConstraint[];
}

export interface Relationship {
  /** Source entity, e.g. `fact_orders`. The older `entity.column` form is still read. */
  from: string;
  /** Target entity, e.g. `dim_customer`. */
  to: string;
  /** The referencing columns, in key order; empty on an unresolved relationship. */
  from_columns?: string[];
  /** The referenced columns, paired with `from_columns` by position. */
  to_columns?: string[];
  name?: string | null;
  cardinality: Cardinality;
}

/** Something the keys-and-constraints migration could not convert exactly. */
export interface ConversionFinding {
  kind: string;
  entity_name?: string | null;
  detail: string;
}

export interface SuggestedMetric {
  name: string;
  formula: string;
  group_by?: string | null;
}

// ---------------------------------------------------------------------------
// API request / response contracts
// ---------------------------------------------------------------------------
export interface SynthesizeRequest {
  source_type: SourceType;
  content: string;
  target_paradigm: Paradigm;
  dialect: string;
  workspace_id?: string | null;
  title?: string | null;
  llm_override?: string | null;
}

export interface SynthesizeResponse {
  model_id: string;
  paradigm: Paradigm;
  entities: Entity[];
  relationships: Relationship[];
  suggested_metrics: SuggestedMetric[];
  validation?: ValidationReport | null;
  /** What the keys-and-constraints migration kept but could not convert exactly. */
  conversion_findings?: ConversionFinding[];
  /** The model's workspace, whose classification scale its columns use. */
  workspace_id?: string | null;
}

export interface TransformParadigmRequest {
  target_paradigm: Paradigm;
  preserve_descriptions: boolean;
  options: {
    hash_key_algorithm: string;
    satellite_split_strategy: string;
    [key: string]: unknown;
  };
}

export interface TransformParadigmResponse {
  model_id: string;
  previous_paradigm: Paradigm | null;
  new_paradigm: Paradigm;
  generated_entities_count: number;
  entities: Entity[];
  transformation_execution_time_ms: number;
}

// ---------------------------------------------------------------------------
// Validation report (graph engine output — FR-2.3)
// ---------------------------------------------------------------------------
export interface ExportResponse {
  model_id: string;
  format: ExportFormat;
  dialect?: string | null;
  files: Record<string, string>;
}

export interface WorkspaceInfo {
  workspace_id: string;
  name: string;
  role: string;
}

export type WorkspaceRole = 'OWNER' | 'ADMIN' | 'APPROVER' | 'MEMBER' | 'VIEWER';

// --- Field attestations (Sprint 8 Steps 4b and 7) ---
export type FieldStatus = 'verified' | 'pending' | 'recorded';

export interface FieldRef {
  entity: string;
  column: string | null;
  field: string;
}

export interface FieldStatusInfo extends FieldRef {
  status: FieldStatus;
  provenance: string | null;
  provenance_by: string | null;
  provenance_at: string | null;
  verified_by: string | null;
  verified_at: string | null;
}

export interface AttestationSummary {
  verified: number;
  fields: number;
  pending_review: number;
  statement: string;
}

export interface AttestationsResponse {
  model_id: string;
  summary: AttestationSummary;
  fields: FieldStatusInfo[];
}

/** The three conditions for "verified", as the server found them. */
export interface VerifyConditions {
  reconciled_import: boolean;
  definition_failures: string[];
  provenance: string | null;
  provenance_verifiable: boolean;
}

export interface VerifyResult extends FieldStatusInfo {
  conditions: VerifyConditions;
}

export interface VerifyResponse {
  model_id: string;
  summary: AttestationSummary;
  results: VerifyResult[];
}

// --- Drift report (Sprint 8 Steps 5 and 7) ---
export interface DriftSource {
  label: string;
  name: string;
  model_id: string | null;
  version: number | null;
  imported_at: string | null;
  dialect: string | null;
  reconciliation: string | null;
  statement: string;
}

export interface Drift {
  kind: string;
  table: string;
  column: string | null;
  columns: string[];
  before: unknown;
  after: unknown;
  class: 'breaking' | 'non-breaking' | 'informational';
  rule: string;
  rule_text: string;
  verified_fields_affected: string[];
  flag: string | null;
}

export interface DriftReport {
  report: string;
  warnings: string[];
  design: DriftSource;
  deployed: DriftSource;
  summary: Record<string, number>;
  drifts: Drift[];
  possible_renames: { table: string; removed: string; added: string; type: string; position: number }[];
}

/** A member of a workspace (Sprint 8 Step 6). */
export interface MemberInfo {
  user_id: string;
  email: string;
  role: WorkspaceRole;
}

/** One level of a workspace's classification scale, least sensitive first. */
export interface ClassificationLevel {
  level_id: string;
  name: string;
  rank: number;
  /** Columns classified at this level; a level in use cannot be deleted. */
  columns_using: number;
}

export interface ClassificationScale {
  workspace_id: string;
  scale_id: string;
  name: string;
  levels: ClassificationLevel[];
}

/**
 * What the appliance has verified about one exportable artifact (F5).
 *
 * Served by `GET /export/status`. The UI must not carry its own copy — that is
 * how the certified-dialect list came to be maintained in two places, kept in
 * step by a test that read this codebase as text.
 */
export interface ArtifactStatusInfo {
  variant: string;
  family: string;
  status: 'CERTIFIED' | 'PREVIEW' | 'UNVERIFIED';
  reason: string;
  /** Export options the variant accepts, e.g. `target_has_ltree` for PostgreSQL DDL. */
  options?: string[];
}

/**
 * A dialect a DDL file can be imported from, and what its import has been
 * tested against. Served by `GET /import/dialects`; the UI keeps no copy.
 */
export interface ImportDialectInfo {
  dialect: string;
  label: string;
  evidence: 'genuine export' | 'documentation-derived' | string;
  tool: string;
}

export type ImportCounts = Record<string, number>;

export interface ImportGap {
  table: string;
  kind: string;
  source: number;
  imported: number;
  statements: { index: number; line: number; statement: string }[];
}

export interface ImportFailureInfo {
  statement: number | null;
  line: number | null;
  head?: string;
  reason: string;
}

/** The reconciliation report stored on an imported model (abridged). */
export interface ImportReport {
  file: string;
  dialect: string;
  evidence: string;
  encoding: string | null;
  status: 'reconciled' | 'unreconciled';
  failures: ImportFailureInfo[];
  not_imported: { index: number; line: number; reason: string; statement: string }[];
  reconciliation?: {
    source: { tables: ImportCounts; partitions: ImportCounts };
    imported: { tables: ImportCounts; partitions: ImportCounts };
    gaps: ImportGap[];
  };
}

export interface ImportResponse {
  model_id: string;
  title: string;
  status: 'reconciled' | 'unreconciled';
  entities: number;
  relationships: number;
  report: ImportReport;
}

/** One row of the egress ledger (D4). Metadata only — never the prompt text. */
export interface EgressEvent {
  egress_id: string;
  attempt_id: string;
  event: string;
  task: string;
  provider: string;
  egress_class: string;
  prompt_sha256: string;
  prompt_chars: number;
  model_id: string | null;
  user_id: string | null;
  workspace_id: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  error: string | null;
  occurred_at: string;
}

export interface EgressLedgerPage {
  events: EgressEvent[];
  total: number;
  /** Rows carrying no workspace, which scoping can return to nobody. */
  unattributed: number;
}

export interface ApiKeyInfo {
  api_key_id: string;
  workspace_id: string;
  name: string;
  key_prefix: string;
  /** The most the key may do; it acts at the lower of this and its creator's role. */
  role_cap?: string;
  created_at: string;
  expires_at?: string | null;
  last_used_at?: string | null;
}

export interface ApiKeyCreatedResponse extends ApiKeyInfo {
  /** The plaintext secret — returned once, at creation. */
  api_key: string;
}

export interface ModelInfo {
  model_id: string;
  workspace_id: string;
  title: string;
  current_paradigm?: string | null;
  target_dialect: string;
  version_number: number;
}

export type JobStatusValue = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface JobCreatedResponse {
  job_id: string;
  status: JobStatusValue;
  poll_url: string;
}

export interface JobStatus {
  job_id: string;
  status: JobStatusValue;
  result_model_id?: string | null;
  error?: string | null;
}

export type IssueSeverity = 'error' | 'warning';

export interface ValidationIssue {
  severity: IssueSeverity;
  code: string;
  message: string;
  entities: string[];
  entity_name?: string | null;
  column_name?: string | null;
}

export interface ValidationReport {
  is_valid: boolean;
  issues: ValidationIssue[];
}

// ---------------------------------------------------------------------------
// Migration & Governance Mesh (Phase 2/3)
// ---------------------------------------------------------------------------
export interface ConnectionInfo {
  connection_id: string;
  workspace_id: string;
  name: string;
  engine: string;
  uri_masked?: string | null;
}

export interface ConnectionCreateRequest {
  name: string;
  engine: ConnectionEngine;
  connection_uri: string;
  workspace_id?: string | null;
}

export interface IntrospectRequest {
  connection_id: string;
  schema_name: string;
}

export interface DiffRequest {
  source_model_id: string;
  target_model_id: string;
  dialect: string;
}

export interface DiffResponse {
  source_model_id: string;
  target_model_id: string;
  dialect: string;
  alter_statements: string[];
  breaking_changes: string[];
  semantic_breaks: string[];
  /** Every statement that destroys data, in words; the same text heads it in the DDL. */
  data_loss?: string[];
}

export interface SyntheticSeedRequest {
  row_count_per_entity: number;
  format: SeedFormat;
  dialect: string;
}

export interface SyntheticSeedResponse {
  model_id: string;
  format: SeedFormat;
  dialect: string;
  row_count_per_entity: number;
  generation_order: string[];
  files: Record<string, string>;
}

export interface ContractExportResponse {
  model_id: string;
  format: ContractFormat;
  files: Record<string, string>;
}

export interface SemanticExportResponse {
  model_id: string;
  engine: SemanticEngine;
  files: Record<string, string>;
}

export interface DictionaryExportResponse {
  model_id: string;
  format: DictionaryFormat;
  files: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Canvas types (React Flow bindings)
// ---------------------------------------------------------------------------

/** Data payload carried by each entity node on the canvas. */
export interface EntityNodeData extends Record<string, unknown> {
  entity_name: string;
  entity_type: EntityType;
  description?: string | null;
  grain?: string | null;
  tier?: AssetTier | null;
  freshness_sla?: string | null;
  agg_time_column?: string | null;
  business_name?: string | null;
  business_owner?: string | null;
  it_steward?: string | null;
  authoritative_source?: string | null;
  columns: Column[];
  primary_key?: string[];
  unique_constraints?: UniqueConstraint[];
  check_constraints?: CheckConstraint[];
}

/** A canvas node representing a single entity. */
export type EntityNode = Node<EntityNodeData, 'entity'>;

/** Edge data carried by relationship connectors. */
export interface RelationshipEdgeData extends Record<string, unknown> {
  cardinality: Cardinality;
  /** The source entity. */
  from_ref: string;
  /** The target entity. */
  to_ref: string;
  from_columns: string[];
  to_columns: string[];
  name?: string | null;
}

/** A canvas edge representing a relationship. */
export type RelationshipEdge = Edge<RelationshipEdgeData>;

/** Serializable snapshot of canvas state for undo/redo. */
export interface CanvasSnapshot {
  nodes: EntityNode[];
  edges: RelationshipEdge[];
}
