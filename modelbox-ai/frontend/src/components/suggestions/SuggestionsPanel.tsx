'use client';

/**
 * Suggestions (Sprint 9 Step 4): ModelBox's guesses about which columns hold
 * PII, and which column each table's measures should be aggregated over.
 *
 * Every suggestion is shown as what it is: a guess from a named rule, with
 * the rule, its category's anchor and the signals it read, never as a
 * confirmed value. A member, admin, approver or owner accepts or rejects it.
 * Accepting writes the value into the saved model as that person's, and the
 * value is then pending review in the dictionary: only an approver can verify
 * it. Time-column candidates are ranked; their confidence is a ranking from
 * written rules, not a measured probability, and a column whose name reads
 * as a row-audit timestamp is flagged. No accuracy figure is shown for any
 * rule, because none is measured.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { acceptSuggestion, getModel, listSuggestions, listWorkspaces, rejectSuggestion, runSuggestions } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { ROLE_LADDER } from '@/lib/roles';
import type { Role } from '@/lib/roles';
import { useCanvasStore } from '@/store/canvasStore';
import { color, radius, semantic, space, type } from '@/styles/tokens';
import type { Suggestion, SuggestionKind, SuggestionsResponse } from '@/types/suggestion';

const CAN_DECIDE = ROLE_LADDER.indexOf('MEMBER');

export const STATUS_TEXT: Record<Suggestion['status'], string> = {
  pending: 'suggested, not confirmed',
  accepted: 'accepted',
  rejected: 'rejected',
  superseded: 'superseded',
};

/** "TABLE.COLUMN". */
export function columnLabel(s: Suggestion): string {
  return `${s.entity}.${s.column}`;
}

/** What the rule read, in words, from the signals it recorded. */
export function evidence(s: Suggestion): string[] {
  const out: string[] = [];
  if (s.kind === 'pii') {
    if (s.signals.name) out.push(`column name "${s.signals.name}"`);
    if (s.signals.comment) out.push(`source comment "${s.signals.comment}"`);
    if (s.signals.check) out.push(`CHECK ${s.signals.check}`);
    if (s.signals.type) out.push(`type ${s.signals.type}`);
    return out;
  }
  out.push(`type ${s.signals.type}`);
  out.push(s.signals.not_null ? 'never NULL' : 'may be NULL');
  if (s.signals.event_word) out.push(`name reads as a business event ("${s.signals.event_word}")`);
  if (s.signals.likely_audit_column) out.push(`name reads as a row-audit timestamp ("${s.signals.audit_word}")`);
  return out;
}

/** Why a pending suggestion cannot be decided now, or null. */
export function blocked(s: Suggestion): string | null {
  if (s.stale) return s.stale;
  if (s.resolved_elsewhere) return 'the field already holds a value';
  return null;
}

export default function SuggestionsPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);
  const workspaceId = useCanvasStore((s) => s.workspaceId);
  const dirty = useCanvasStore((s) => s.dirty);
  const loadModel = useCanvasStore((s) => s.loadModel);

  const [data, setData] = useState<SuggestionsResponse | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [kind, setKind] = useState<SuggestionKind>('pii');
  const [onlyPending, setOnlyPending] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!modelId) return;
    setError(null);
    try {
      setData(await listSuggestions(modelId));
    } catch (e) {
      setError(errMessage(e, 'The suggestions could not be loaded.'));
    }
  }, [modelId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!workspaceId) return;
    listWorkspaces()
      .then((all) => setRole((all.find((w) => w.workspace_id === workspaceId)?.role as Role) ?? null))
      .catch(() => setRole(null));
  }, [workspaceId]);

  const canDecide = role !== null && ROLE_LADDER.indexOf(role) >= CAN_DECIDE;

  const shown = useMemo(
    () => (data?.suggestions ?? []).filter((s) => s.kind === kind && (!onlyPending || s.status === 'pending')),
    [data, kind, onlyPending],
  );
  // Time-column candidates, grouped by table, in rank order as served.
  const tables = useMemo(() => [...new Set(shown.map((s) => s.entity))], [shown]);

  async function run() {
    if (!modelId) return;
    setBusy(true);
    setError(null);
    try {
      setData(await runSuggestions(modelId));
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function decide(s: Suggestion, accept: boolean) {
    if (!modelId) return;
    setBusy(true);
    setError(null);
    try {
      setData(await (accept ? acceptSuggestion(modelId, s.suggestion_id) : rejectSuggestion(modelId, s.suggestion_id)));
    } catch (e) {
      setError(errMessage(e));
      setBusy(false);
      return;
    }
    // An accepted suggestion changed the saved model: show it on the canvas.
    // If that read fails, say so: saving this canvas would write the old graph back.
    if (accept) {
      try {
        loadModel(await getModel(modelId));
      } catch {
        setError(
          'The suggestion was accepted and saved, but the canvas could not be refreshed. Reload the page before ' +
            'saving the canvas, or the save will undo the accepted value.',
        );
      }
    }
    setBusy(false);
  }

  function row(s: Suggestion) {
    const label = columnLabel(s);
    const why = blocked(s);
    const decidable = canDecide && s.status === 'pending' && !why;
    return (
      <li key={s.suggestion_id} style={rowStyle} aria-label={`Suggestion for ${label}`}>
        <div style={rowHead}>
          <strong>{label}</strong>
          <span>
            {s.kind === 'pii' ? `${s.category_label} (${s.category})` : 'aggregation time column'}
          </span>
          {s.confidence !== null && (
            <span aria-label={`Confidence of ${label}`} style={muted}>
              rank {s.signals.rank} of {s.signals.of} · confidence {s.confidence.toFixed(1)}
            </span>
          )}
          <span aria-label={`Status of ${label}`} style={badge}>
            {STATUS_TEXT[s.status]}
          </span>
        </div>
        {s.signals.flag && (
          <div style={{ color: semantic.breaking.onLight }} aria-label={`Flag on ${label}`}>
            {s.signals.flag}
          </div>
        )}
        <div style={muted}>
          Rule {s.rule_name}
          {s.rule_source === 'client' ? ' (client rule)' : ''} · {s.anchor}
        </div>
        <div style={muted}>Read: {evidence(s).join('; ')}</div>
        {s.decided_by_email && (
          <div style={muted}>
            {STATUS_TEXT[s.status]} by {s.decided_by_email}
          </div>
        )}
        {s.status === 'pending' && why && <div style={muted}>Cannot be decided: {why}.</div>}
        {decidable && (
          <div style={actions}>
            <button
              type="button"
              aria-label={`Accept ${label}`}
              disabled={busy || dirty}
              onClick={() => void decide(s, true)}
              style={smallBtn}
            >
              Accept
            </button>
            <button
              type="button"
              aria-label={`Reject ${label}`}
              disabled={busy || dirty}
              onClick={() => void decide(s, false)}
              style={smallBtn}
            >
              Reject
            </button>
          </div>
        )}
      </li>
    );
  }

  return (
    <section aria-label="Suggestions" style={container}>
      <div style={header}>
        <div>
          <div style={title}>Suggestions</div>
          <div role="status" style={meta}>
            {data ? data.counts.statement : 'Loading…'}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close suggestions" style={closeBtn}>
          ✕
        </button>
      </div>

      <div style={body}>
        <p style={note}>
          Guesses from named rules that read column names, types, source comments and CHECK constraints. None is
          part of the model until a person accepts it. An accepted value is recorded as yours. An accepted PII
          value is then pending review in the dictionary, and only an approver can verify it; an accepted time
          column is your choice, with no review step. No accuracy figure is given for these rules.
        </p>
        {!canDecide && role !== null && (
          <p style={note}>Only a member, approver, admin or owner can run the rules or decide a suggestion.</p>
        )}
        {canDecide && dirty && (
          <p role="alert" style={{ ...note, color: semantic.breaking.onLight }}>
            Save the canvas before deciding: a decision changes the saved model.
          </p>
        )}

        <div style={toolbar}>
          <div role="tablist" aria-label="Kind of suggestion" style={tabs}>
            {(['pii', 'agg_time_column'] as const).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={kind === k}
                onClick={() => setKind(k)}
                style={tab(kind === k)}
              >
                {k === 'pii' ? 'PII' : 'Time column'}
              </button>
            ))}
          </div>
          <label style={checkLabel}>
            <input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
            Pending only
          </label>
          {canDecide && (
            <button type="button" disabled={busy} onClick={() => void run()} style={primaryBtn}>
              Run the rules
            </button>
          )}
        </div>

        {kind === 'agg_time_column' && (
          <p style={note}>
            Every date or time column of a table is a candidate. The confidence ranks them by written rules (never
            NULL, a business-event name, not a row-audit name); it is not a measured probability. Nothing is chosen
            until a person accepts one.
          </p>
        )}

        {error && (
          <p role="alert" style={{ ...note, color: semantic.breaking.onLight }}>
            {error}
          </p>
        )}

        {shown.length === 0 && data && <p style={note}>Nothing to show.</p>}
        {kind === 'pii' ? (
          <ul aria-label="PII suggestions" style={list}>
            {shown.map(row)}
          </ul>
        ) : (
          tables.map((t) => (
            <div key={t} style={group}>
              <div style={labelStyle}>{t}</div>
              <ul aria-label={`Time column candidates for ${t}`} style={list}>
                {shown.filter((s) => s.entity === t).map(row)}
              </ul>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

const container: React.CSSProperties = {
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  borderLeft: `1px solid ${color.neutral[200]}`,
  background: color.white,
};

const header: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  padding: space.lg,
  borderBottom: `1px solid ${color.neutral[200]}`,
};

const title: React.CSSProperties = { fontSize: type.h3.size, fontWeight: type.h3.weight };

const meta: React.CSSProperties = { fontSize: type.caption.size, color: color.neutral[600], marginTop: space.xs };

const body: React.CSSProperties = {
  padding: space.lg,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: space.md,
};

const toolbar: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: space.md, flexWrap: 'wrap' };

const tabs: React.CSSProperties = { display: 'flex', gap: space.xs };

const tab = (active: boolean): React.CSSProperties => ({
  padding: `${space.xs}px ${space.md}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  background: active ? color.neutral[700] : color.white,
  color: active ? color.white : color.neutral[700],
  fontSize: type.uiSmall.size,
  cursor: 'pointer',
});

const checkLabel: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: space.xs,
  fontSize: type.uiSmall.size,
  color: color.neutral[700],
};

const labelStyle: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[600],
};

const note: React.CSSProperties = { fontSize: type.uiSmall.size, color: color.neutral[600], margin: 0 };

const muted: React.CSSProperties = { fontSize: type.uiXSmall.size, color: color.neutral[600] };

const group: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.xs };

const list: React.CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: space.xs,
};

const rowStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.xs,
  padding: `${space.sm}px ${space.sm}px`,
  border: `1px solid ${color.neutral[100]}`,
  borderRadius: radius.md,
  fontSize: type.uiSmall.size,
};

const rowHead: React.CSSProperties = { display: 'flex', alignItems: 'baseline', gap: space.sm, flexWrap: 'wrap' };

const actions: React.CSSProperties = { display: 'flex', gap: space.sm };

// Neutral for every status: an accepted value is pending review, not
// verified, so no status here wears the "validated" colour.
const badge: React.CSSProperties = {
  marginLeft: 'auto',
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[600],
};

const primaryBtn: React.CSSProperties = {
  padding: `${space.sm}px ${space.md}px`,
  borderRadius: radius.md,
  border: 'none',
  background: color.blue,
  color: color.white,
  fontWeight: type.uiXSmall.weight,
  cursor: 'pointer',
};

const smallBtn: React.CSSProperties = {
  padding: `${space.xs}px ${space.sm}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  background: color.white,
  fontSize: type.uiXSmall.size,
  cursor: 'pointer',
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: type.body.size,
  color: color.neutral[500],
  cursor: 'pointer',
};
