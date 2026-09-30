/**
 * PII and aggregation-time suggestions (Sprint 9 Step 4), as the API serves them.
 *
 * A suggestion is a guess with provenance "heuristic": never a value the
 * model holds, never verified. Accepting or rejecting it is a person's
 * decision, taken by the signed-in caller; no request names a decider.
 */

export type SuggestionKind = 'pii' | 'agg_time_column';
export type SuggestionStatus = 'pending' | 'accepted' | 'rejected' | 'superseded';

export interface SuggestionSignals {
  rules: string[];
  type?: string;
  name?: string;
  comment?: string;
  check?: string;
  // Time-column candidates only.
  not_null?: boolean;
  event_word?: string | null;
  audit_word?: string | null;
  likely_audit_column?: boolean;
  flag?: string | null;
  rank?: number;
  of?: number;
  [key: string]: unknown;
}

export interface Suggestion {
  suggestion_id: string;
  kind: SuggestionKind;
  entity: string;
  column: string;
  suggested: { is_pii?: boolean; pii_type?: string | null; agg_time_column?: string };
  category: string;
  category_label: string;
  anchor: string;
  rule_name: string;
  rule_source: 'builtin' | 'client';
  signals: SuggestionSignals;
  /** A time-column candidate's rank score from written rules; never set on a PII suggestion. */
  confidence: number | null;
  provenance: 'heuristic';
  status: SuggestionStatus;
  stale: string | null;
  resolved_elsewhere: boolean;
  decided_by_email: string | null;
  decided_at: string | null;
}

export interface SuggestionsResponse {
  model_id: string;
  counts: { pending: number; accepted: number; rejected: number; superseded: number; statement: string };
  ruleset_digest: string;
  suggestions: Suggestion[];
}

export interface RunSuggestionsResponse extends SuggestionsResponse {
  created: number;
  superseded_now: number;
}
