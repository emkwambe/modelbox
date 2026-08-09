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

export type Cardinality = '1:1' | '1:N' | 'N:M';

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

// ---------------------------------------------------------------------------
// Core domain shapes
// ---------------------------------------------------------------------------
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
}

export interface Entity {
  entity_name: string;
  entity_type: EntityType;
  description?: string | null;
  grain?: string | null;
  canvas_position_x: number;
  canvas_position_y: number;
  columns: Column[];
}

export interface Relationship {
  /** Source ref, e.g. `fact_orders.customer_hk`. */
  from: string;
  /** Target ref, e.g. `dim_customer.customer_hk`. */
  to: string;
  cardinality: Cardinality;
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

export type IssueSeverity = 'error' | 'warning';

export interface ValidationIssue {
  severity: IssueSeverity;
  code: string;
  message: string;
  entities: string[];
}

export interface ValidationReport {
  is_valid: boolean;
  issues: ValidationIssue[];
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
  columns: Column[];
}

/** A canvas node representing a single entity. */
export type EntityNode = Node<EntityNodeData, 'entity'>;

/** Edge data carried by relationship connectors. */
export interface RelationshipEdgeData extends Record<string, unknown> {
  cardinality: Cardinality;
  from_ref: string;
  to_ref: string;
}

/** A canvas edge representing a relationship. */
export type RelationshipEdge = Edge<RelationshipEdgeData>;

/** Serializable snapshot of canvas state for undo/redo. */
export interface CanvasSnapshot {
  nodes: EntityNode[];
  edges: RelationshipEdge[];
}
