/**
 * Source-to-target mapping (Sprint 9 Step 3): the shapes the mapping routes
 * return. A proposal is inference and counts as nothing; an entry is a
 * person's decision.
 */

export type EntryKind = 'mapped' | 'constant' | 'derived' | 'not_yet_mapped';
export type RowStatus = EntryKind | 'drift' | 'pending' | 'silent';
export type MappingExportFormat = 'csv' | 'markdown' | 'html' | 'json';

export interface ColumnPick {
  entity: string;
  column: string;
}

export interface MappingColumn extends ColumnPick {
  stable_id?: number | null;
  exists: boolean;
  type?: string | null;
  nullable?: boolean | null;
  key?: string | null;
}

export interface MappingDocument {
  document_id: string;
  workspace_id: string;
  title: string;
  target_model_id: string;
  source_model_id: string | null;
  source_model_title: string;
  source_system: string | null;
  target_system: string | null;
  version: number;
  status: string;
  created_by_email: string | null;
  created_at: string;
}

export interface Completeness {
  total: number;
  mapped: number;
  explicitly_unmapped: number;
  pending: number;
  silent: number;
  in_drift: number;
  orphaned: number;
  accepted_entries: number;
  pending_proposals: number;
  complete: boolean;
  summary: string;
}

export interface MappingEntryView {
  entry_id: string | null;
  mapping_key: string;
  kind: EntryKind;
  revision: number;
  sources: MappingColumn[];
  fields: Record<string, unknown>;
  provenance_by: string | null;
  provenance_at: string | null;
}

export interface MappingProposalView {
  proposal_id: string | null;
  sources: MappingColumn[];
  name_similarity: number;
  type_compatibility: number;
  confidence: number;
  method: string;
  method_version: string;
}

export interface MappingRow {
  target: MappingColumn;
  status: RowStatus;
  entry: MappingEntryView | null;
  proposals: MappingProposalView[];
  drift: string[];
}

export interface MappingReport {
  document: MappingDocument;
  completeness: Completeness;
  rows: MappingRow[];
}

export interface MappingDecisionView {
  decision_id: string;
  decision: string;
  mapping_key: string | null;
  proposal_id: string | null;
  decided_by_email: string;
  decided_at: string;
  evidence: Record<string, unknown>;
}

export interface MappingLineage {
  document_id: string;
  row: MappingRow;
  decisions: MappingDecisionView[];
}

export interface MappingExport {
  document_id: string;
  format: MappingExportFormat;
  filename: string;
  content: string;
}

export interface AuthorEntryBody {
  target: ColumnPick;
  kind: EntryKind;
  sources: ColumnPick[];
  fields: Record<string, unknown>;
}
