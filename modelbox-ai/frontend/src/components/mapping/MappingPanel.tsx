'use client';

/**
 * Source-to-target mapping (Sprint 9 Step 3), for the model on the canvas as
 * the target: every target column with its status, completeness as
 * "N of M target columns mapped, K explicitly unmapped, S silent", drift
 * flags, ModelBox's proposals with their scores, the exports and a lineage
 * view per target column.
 *
 * A proposal is shown as pending and counts as nothing. It becomes an entry
 * only when a person accepts it, or writes an entry of their own; the server
 * records who, when and what was shown. A VIEWER sees the document and no
 * controls; the server refuses them too.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  acceptProposal,
  authorEntry,
  createMapping,
  exportMapping,
  getLineage,
  getMapping,
  getModel,
  listMappings,
  listModels,
  listWorkspaces,
  proposeMappings,
  rejectProposal,
  removeEntry,
} from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { ROLE_LADDER } from '@/lib/roles';
import type { Role } from '@/lib/roles';
import { useCanvasStore } from '@/store/canvasStore';
import { color, radius, semantic, space, type } from '@/styles/tokens';
import type {
  ColumnPick,
  EntryKind,
  MappingDocument,
  MappingExportFormat,
  MappingLineage,
  MappingReport,
  MappingRow,
  RowStatus,
} from '@/types/mapping';
import type { ModelInfo } from '@/types/schema';

export const ROW_STATUS_TEXT: Record<RowStatus, string> = {
  mapped: 'mapped',
  constant: 'unmapped: constant',
  derived: 'unmapped: derived',
  not_yet_mapped: 'unmapped: not yet mapped',
  drift: 'in drift',
  pending: 'pending review',
  silent: 'silent',
};

const KINDS: { value: EntryKind; label: string }[] = [
  { value: 'mapped', label: 'Mapped from source' },
  { value: 'constant', label: 'Unmapped: constant' },
  { value: 'derived', label: 'Unmapped: derived' },
  { value: 'not_yet_mapped', label: 'Unmapped: not yet mapped' },
];

const FORMATS: MappingExportFormat[] = ['csv', 'markdown', 'html', 'json'];
const CAN_DECIDE = ROLE_LADDER.indexOf('MEMBER');

export function columnLabel(c: ColumnPick): string {
  return `${c.entity}.${c.column}`;
}

function rowKey(row: MappingRow): string {
  return `${row.target.entity}\u0000${row.target.column}\u0000${row.entry?.mapping_key ?? ''}`;
}

function download(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

interface Draft {
  kind: EntryKind;
  sources: string[];
  rule: string;
}

export default function MappingPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);
  const workspaceId = useCanvasStore((s) => s.workspaceId);

  const [documents, setDocuments] = useState<MappingDocument[]>([]);
  const [report, setReport] = useState<MappingReport | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [sourceColumns, setSourceColumns] = useState<ColumnPick[]>([]);
  const [role, setRole] = useState<Role | null>(null);
  const [newSource, setNewSource] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [format, setFormat] = useState<MappingExportFormat>('csv');
  const [lineage, setLineage] = useState<MappingLineage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canDecide = role !== null && ROLE_LADDER.indexOf(role) >= CAN_DECIDE;
  const documentId = report?.document.document_id ?? null;

  const loadDocuments = useCallback(async () => {
    if (!modelId) return;
    try {
      const listed = await listMappings(modelId);
      setDocuments(listed);
      const first = listed[0];
      if (first && !report) setReport(await getMapping(first.document_id));
    } catch (e) {
      setError(errMessage(e, 'The mappings could not be loaded.'));
    }
    // `report` is read once to pick the first document; reloading on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!workspaceId) return;
    listWorkspaces()
      .then((all) => setRole((all.find((w) => w.workspace_id === workspaceId)?.role as Role) ?? null))
      .catch(() => setRole(null));
    listModels()
      .then((all) => setModels(all.filter((m) => m.workspace_id === workspaceId)))
      .catch(() => setModels([]));
  }, [workspaceId]);

  const sourceId = report?.document.source_model_id ?? null;
  useEffect(() => {
    if (!sourceId) {
      setSourceColumns([]);
      return;
    }
    getModel(sourceId)
      .then((m) => setSourceColumns(m.entities.flatMap((e) => e.columns.map((c) => ({ entity: e.entity_name, column: c.name })))))
      .catch(() => setSourceColumns([]));
  }, [sourceId]);

  async function run(action: () => Promise<MappingReport | void>) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      if (next) setReport(next);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!modelId || !newSource || !newTitle.trim()) return;
    await run(async () => {
      const made = await createMapping(modelId, { source_model_id: newSource, title: newTitle.trim() });
      setDocuments((d) => [...d, made.document]);
      setNewTitle('');
      return made;
    });
  }

  function draftFor(row: MappingRow): Draft {
    return drafts[rowKey(row)] ?? { kind: 'mapped', sources: [], rule: '' };
  }

  function setDraft(row: MappingRow, change: Partial<Draft>) {
    setDrafts((d) => ({ ...d, [rowKey(row)]: { ...draftFor(row), ...change } }));
  }

  async function saveEntry(row: MappingRow) {
    if (!documentId) return;
    const draft = draftFor(row);
    const sources = draft.kind === 'mapped'
      ? draft.sources.map((s) => sourceColumns.find((c) => columnLabel(c) === s)).filter((c): c is ColumnPick => !!c)
      : [];
    await run(() => authorEntry(documentId, {
      target: { entity: row.target.entity, column: row.target.column },
      kind: draft.kind,
      sources,
      fields: draft.rule.trim() ? { rule_description: draft.rule.trim() } : {},
    }));
  }

  async function downloadExport() {
    if (!documentId) return;
    await run(async () => {
      const exported = await exportMapping(documentId, format);
      download(exported.filename, exported.content);
    });
  }

  const counts = report?.completeness;
  const sourceOptions = useMemo(() => sourceColumns.map(columnLabel), [sourceColumns]);

  return (
    <section aria-label="Source-to-target mapping" style={container}>
      <div style={header}>
        <div>
          <div style={title}>Mapping{report ? `: ${report.document.title}` : ''}</div>
          <div role="status" style={meta}>
            {counts ? counts.summary : documents.length ? 'Loading…' : 'No mapping into this model yet.'}
          </div>
          {counts && (
            <div aria-label="Completeness" style={{ ...meta, color: counts.complete ? semantic.validated.onLight : semantic.breaking.onLight }}>
              {counts.complete ? 'Complete' : 'Not complete: pending, silent and drifted columns need a person'}
            </div>
          )}
        </div>
        <button type="button" onClick={onClose} aria-label="Close mapping" style={closeBtn}>
          ✕
        </button>
      </div>

      <div style={body}>
        <div style={toolbar}>
          {documents.length > 0 && (
            <label style={fieldStyle}>
              <span style={labelStyle}>Mapping</span>
              <select
                aria-label="Mapping document"
                value={documentId ?? ''}
                onChange={(e) => void run(() => getMapping(e.target.value))}
                style={input}
              >
                {documents.map((d) => (
                  <option key={d.document_id} value={d.document_id}>
                    {d.title} (from {d.source_model_title})
                  </option>
                ))}
              </select>
            </label>
          )}
          {canDecide && documentId && (
            <button type="button" disabled={busy} onClick={() => void run(() => proposeMappings(documentId))} style={smallBtn}>
              Propose mappings
            </button>
          )}
          {documentId && (
            <>
              <select aria-label="Export format" value={format} onChange={(e) => setFormat(e.target.value as MappingExportFormat)} style={input}>
                {FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f.toUpperCase()}
                  </option>
                ))}
              </select>
              <button type="button" disabled={busy} onClick={() => void downloadExport()} style={smallBtn}>
                Export
              </button>
            </>
          )}
        </div>

        {canDecide && (
          <div aria-label="New mapping" style={toolbar}>
            <select aria-label="Source model" value={newSource} onChange={(e) => setNewSource(e.target.value)} style={input}>
              <option value="">Map from…</option>
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.title}
                </option>
              ))}
            </select>
            <input aria-label="Mapping title" placeholder="Title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} style={input} />
            <button type="button" disabled={busy || !newSource || !newTitle.trim()} onClick={() => void create()} style={primaryBtn}>
              New mapping
            </button>
          </div>
        )}
        {!canDecide && role !== null && <p style={note}>Only a member or above can propose or decide mappings.</p>}

        {error && (
          <p role="alert" style={{ ...note, color: semantic.breaking.onLight }}>
            {error}
          </p>
        )}

        {lineage && (
          <div aria-label="Lineage" style={box}>
            <div style={labelStyle}>Lineage of {columnLabel(lineage.row.target)}</div>
            <div>
              {lineage.row.entry
                ? lineage.row.entry.sources.map((s) => `${columnLabel(s)}${s.exists ? '' : ' (missing)'}`).join(', ') || 'no source (explicitly unmapped)'
                : 'no entry'}
            </div>
            {lineage.row.drift.map((d) => (
              <div key={d} style={{ color: semantic.breaking.onLight }}>{d}</div>
            ))}
            <ul style={plainList}>
              {lineage.decisions.map((d) => (
                <li key={d.decision_id}>
                  {d.decision} by {d.decided_by_email} at {d.decided_at}
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => setLineage(null)} style={smallBtn}>
              Close lineage
            </button>
          </div>
        )}

        <ul aria-label="Target columns" style={list}>
          {(report?.rows ?? []).map((row) => {
            const label = columnLabel(row.target);
            const draft = draftFor(row);
            return (
              <li key={rowKey(row)} style={rowStyle}>
                <div style={rowHead}>
                  <strong style={{ flex: 1 }}>
                    {label} <span style={meta}>{row.target.type ?? ''}</span>
                  </strong>
                  <span aria-label={`Status of ${label}`} style={badge(row.status)}>
                    {ROW_STATUS_TEXT[row.status]}
                  </span>
                </div>
                {row.entry && (
                  <div style={meta}>
                    {row.entry.mapping_key}: {row.entry.sources.map(columnLabel).join(' + ') || 'no source'}
                    {row.entry.provenance_by ? ` · by ${row.entry.provenance_by}` : ''}
                  </div>
                )}
                {row.drift.map((d) => (
                  <div key={d} role="note" style={{ ...meta, color: semantic.breaking.onLight }}>
                    Drift: {d}
                  </div>
                ))}
                {row.proposals.map((p) => (
                  <div key={p.proposal_id ?? ''} aria-label={`Proposal for ${label}`} style={proposalRow}>
                    <span style={{ flex: 1 }}>
                      Proposed: {p.sources.map(columnLabel).join(' + ')} · name {p.name_similarity.toFixed(2)} · type{' '}
                      {p.type_compatibility.toFixed(2)} · confidence {p.confidence.toFixed(2)}
                    </span>
                    {canDecide && documentId && p.proposal_id && (
                      <>
                        <button type="button" disabled={busy} onClick={() => void run(() => acceptProposal(documentId, p.proposal_id as string))} style={smallBtn}>
                          Accept
                        </button>
                        <button type="button" disabled={busy} onClick={() => void run(() => rejectProposal(documentId, p.proposal_id as string))} style={smallBtn}>
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                ))}
                <div style={rowHead}>
                  {documentId && (
                    <button
                      type="button"
                      aria-label={`Lineage of ${label}`}
                      onClick={() => void getLineage(documentId, row.target).then(setLineage).catch((e) => setError(errMessage(e)))}
                      style={smallBtn}
                    >
                      Lineage
                    </button>
                  )}
                  {canDecide && documentId && row.entry && (
                    <button
                      type="button"
                      aria-label={`Remove entry for ${label}`}
                      disabled={busy}
                      onClick={() => void run(() => removeEntry(documentId, (row.entry as { mapping_key: string }).mapping_key))}
                      style={smallBtn}
                    >
                      Remove
                    </button>
                  )}
                </div>
                {canDecide && documentId && !row.entry && (
                  <div aria-label={`Entry for ${label}`} style={toolbar}>
                    <select aria-label={`Kind for ${label}`} value={draft.kind} onChange={(e) => setDraft(row, { kind: e.target.value as EntryKind })} style={input}>
                      {KINDS.map((k) => (
                        <option key={k.value} value={k.value}>
                          {k.label}
                        </option>
                      ))}
                    </select>
                    {draft.kind === 'mapped' && (
                      <select
                        multiple
                        aria-label={`Source columns for ${label}`}
                        value={draft.sources}
                        onChange={(e) => setDraft(row, { sources: Array.from(e.target.selectedOptions).map((o) => o.value) })}
                        style={{ ...input, minWidth: 200 }}
                      >
                        {sourceOptions.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    )}
                    <input aria-label={`Rule for ${label}`} placeholder="Rule in plain language" value={draft.rule} onChange={(e) => setDraft(row, { rule: e.target.value })} style={input} />
                    <button type="button" disabled={busy} onClick={() => void saveEntry(row)} style={primaryBtn}>
                      Save entry
                    </button>
                  </div>
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

const toolbar: React.CSSProperties = { display: 'flex', alignItems: 'flex-end', gap: space.sm, flexWrap: 'wrap' };

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
  gap: space.sm,
};

const plainList: React.CSSProperties = { margin: 0, paddingLeft: space.lg };

const rowStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.xs,
  padding: space.sm,
  border: `1px solid ${color.neutral[100]}`,
  borderRadius: radius.md,
  fontSize: type.uiSmall.size,
};

const rowHead: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: space.sm };

const proposalRow: React.CSSProperties = { ...rowHead, color: color.neutral[600] };

const box: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.sm,
  padding: space.md,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: radius.lg,
  background: color.neutral[50],
  fontSize: type.uiSmall.size,
};

const badge = (status: RowStatus): React.CSSProperties => ({
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color:
    status === 'mapped'
      ? semantic.validated.onLight
      : status === 'silent' || status === 'drift'
        ? semantic.breaking.onLight
        : color.neutral[600],
});

const primaryBtn: React.CSSProperties = {
  padding: `${space.xs}px ${space.md}px`,
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
