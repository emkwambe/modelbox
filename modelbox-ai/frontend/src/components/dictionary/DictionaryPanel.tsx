'use client';

/**
 * Dictionary review (Sprint 8 Step 7): every field of the model that holds a
 * value, with its status (verified, pending review, recorded), and the
 * "N of M fields verified, K pending review" count.
 *
 * An APPROVER, ADMIN or OWNER can ask for one field, or a selection, to be
 * verified. The server decides, from three conditions, and this panel shows
 * each condition as the server found it, and why a field it refused stayed
 * pending. A MEMBER or VIEWER sees no control; the server refuses them too.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import { listAttestations, listWorkspaces, verifyFields } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { ROLE_LADDER } from '@/lib/roles';
import type { Role } from '@/lib/roles';
import { useCanvasStore } from '@/store/canvasStore';
import { color, radius, semantic, space, type } from '@/styles/tokens';
import type { AttestationsResponse, FieldRef, FieldStatus, VerifyResult } from '@/types/schema';

export const STATUS_TEXT: Record<FieldStatus, string> = {
  verified: 'verified',
  pending: 'pending review',
  recorded: 'recorded',
};

/** "TABLE.COLUMN · field", or "TABLE · field" for a table-level field. */
export function fieldLabel(ref: FieldRef): string {
  return `${ref.entity}${ref.column ? `.${ref.column}` : ''} · ${ref.field}`;
}

function key(ref: FieldRef): string {
  return `${ref.entity}\u0000${ref.column ?? ''}\u0000${ref.field}`;
}

/** Why the server left a field pending, in words, from the conditions it returned. */
export function whyPending(result: VerifyResult): string[] {
  const c = result.conditions;
  const reasons: string[] = [];
  if (!c.reconciled_import) reasons.push('the model is not a reconciled import');
  if (c.definition_failures.length) {
    reasons.push(`its definition fails the ISO/IEC 11179-4 rules: ${c.definition_failures.join(', ')}`);
  }
  if (!c.provenance_verifiable) {
    reasons.push(c.provenance ? `its provenance (${c.provenance}) cannot support verified` : 'no provenance is recorded');
  }
  return reasons;
}

const CAN_VERIFY = ROLE_LADDER.indexOf('APPROVER');

export default function DictionaryPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);
  const workspaceId = useCanvasStore((s) => s.workspaceId);

  const [data, setData] = useState<AttestationsResponse | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [table, setTable] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [results, setResults] = useState<VerifyResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!modelId) return;
    setError(null);
    try {
      setData(await listAttestations(modelId));
    } catch (e) {
      setError(errMessage(e, 'The dictionary could not be loaded.'));
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

  const canVerify = role !== null && ROLE_LADDER.indexOf(role) >= CAN_VERIFY;
  const tables = useMemo(() => [...new Set((data?.fields ?? []).map((f) => f.entity))], [data]);
  const shown = (data?.fields ?? []).filter((f) => !table || f.entity === table);

  async function verify(refs: FieldRef[]) {
    if (!modelId || refs.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const response = await verifyFields(modelId, refs);
      setResults(response.results);
      setSelected(new Set());
      await load();
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function toggle(ref: FieldRef) {
    setSelected((prev) => {
      const next = new Set(prev);
      const k = key(ref);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  // References only: the server refuses a request that carries a status.
  const selectedRefs: FieldRef[] = shown
    .filter((f) => selected.has(key(f)))
    .map((f) => ({ entity: f.entity, column: f.column, field: f.field }));

  return (
    <section aria-label="Dictionary review" style={container}>
      <div style={header}>
        <div>
          <div style={title}>Dictionary review</div>
          <div role="status" style={meta}>
            {data ? data.summary.statement : 'Loading…'}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close dictionary review" style={closeBtn}>
          ✕
        </button>
      </div>

      <div style={body}>
        {!canVerify && role !== null && (
          <p style={note}>Only an approver, admin or owner can ask for fields to be verified.</p>
        )}

        <div style={toolbar}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Table</span>
            <select value={table} onChange={(e) => setTable(e.target.value)} style={input}>
              <option value="">All tables</option>
              {tables.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          {canVerify && (
            <button
              type="button"
              disabled={busy || selectedRefs.length === 0}
              onClick={() => void verify(selectedRefs)}
              style={primaryBtn}
            >
              Verify selected ({selectedRefs.length})
            </button>
          )}
        </div>

        {error && (
          <p role="alert" style={{ ...note, color: semantic.breaking.onLight }}>
            {error}
          </p>
        )}

        {results && (
          <div aria-label="Verification results" style={resultsBox}>
            <div style={labelStyle}>Verification results</div>
            {results.map((r) => (
              <div key={key(r)} style={resultRow}>
                <div>
                  <strong>{fieldLabel(r)}</strong>: {STATUS_TEXT[r.status]}
                </div>
                <ul style={conditionList}>
                  <li>Reconciled import: {r.conditions.reconciled_import ? 'yes' : 'no'}</li>
                  <li>
                    Definition (ISO/IEC 11179-4):{' '}
                    {r.conditions.definition_failures.length
                      ? `fails (${r.conditions.definition_failures.join(', ')})`
                      : 'passes'}
                  </li>
                  <li>
                    Provenance: {r.conditions.provenance ?? 'none recorded'}
                    {r.conditions.provenance_verifiable ? ' (can support verified)' : ' (cannot support verified)'}
                  </li>
                </ul>
                {r.status !== 'verified' && (
                  <div style={{ color: semantic.breaking.onLight }}>
                    Stayed {STATUS_TEXT[r.status]} because {whyPending(r).join('; ')}.
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <ul aria-label="Dictionary fields" style={list}>
          {shown.map((f) => {
            const label = fieldLabel(f);
            return (
              <li key={key(f)} style={row}>
                {canVerify && (
                  <input
                    type="checkbox"
                    aria-label={`Select ${label}`}
                    checked={selected.has(key(f))}
                    onChange={() => toggle(f)}
                  />
                )}
                <span style={{ flex: 1 }}>{label}</span>
                <span aria-label={`Status of ${label}`} style={badge(f.status)}>
                  {STATUS_TEXT[f.status]}
                </span>
                {canVerify && f.status !== 'verified' && (
                  <button
                    type="button"
                    aria-label={`Verify ${label}`}
                    disabled={busy}
                    onClick={() => void verify([{ entity: f.entity, column: f.column, field: f.field }])}
                    style={smallBtn}
                  >
                    Verify
                  </button>
                )}
              </li>
            );
          })}
        </ul>
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

const toolbar: React.CSSProperties = { display: 'flex', alignItems: 'flex-end', gap: space.md, flexWrap: 'wrap' };

const fieldStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.xs };

const labelStyle: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[600],
};

const note: React.CSSProperties = { fontSize: type.uiSmall.size, color: color.neutral[600], margin: 0 };

const input: React.CSSProperties = {
  padding: `${space.xs}px ${space.sm}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: type.uiSmall.size,
};

const list: React.CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: space.xs,
};

const row: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: space.sm,
  padding: `${space.xs}px ${space.sm}px`,
  border: `1px solid ${color.neutral[100]}`,
  borderRadius: radius.md,
  fontSize: type.uiSmall.size,
};

const badge = (status: FieldStatus): React.CSSProperties => ({
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: status === 'verified' ? semantic.validated.onLight : color.neutral[600],
});

const resultsBox: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.sm,
  padding: space.md,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: radius.lg,
  background: color.neutral[50],
  fontSize: type.uiSmall.size,
};

const resultRow: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.xs };

const conditionList: React.CSSProperties = { margin: 0, paddingLeft: space.lg };

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
