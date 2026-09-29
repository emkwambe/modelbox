'use client';

/**
 * Drift report (Sprint 8 Step 7): the open model, as the documented design,
 * against a DDL export of the deployed schema. The file is imported on the
 * server and never saved. The report names both sources and their
 * reconciliation (an unreconciled import is warned about first), lists each
 * drift with its class and the written rule behind it, flags a drift that
 * touches a verified dictionary field, and lists possible renames as hints.
 */

import { useEffect, useState } from 'react';

import { driftReport, listImportDialects } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { useCanvasStore } from '@/store/canvasStore';
import { color, radius, semantic, space, type } from '@/styles/tokens';
import type { Drift, DriftReport, DriftSource, ImportDialectInfo } from '@/types/schema';

export function where(d: Drift): string {
  if (d.column) return `${d.table}.${d.column}`;
  if (d.columns.length) return `${d.table}(${d.columns.join(', ')})`;
  return d.table;
}

function sourceLine(s: DriftSource): string {
  const parts = [`${s.label}: ${s.name}`];
  if (s.version !== null) parts.push(`version ${s.version}`);
  if (s.imported_at) parts.push(`imported ${s.imported_at}`);
  if (s.dialect) parts.push(s.dialect);
  return `${parts.join(', ')} — ${s.statement}`;
}

export default function DriftPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);
  const [dialects, setDialects] = useState<ImportDialectInfo[]>([]);
  const [dialect, setDialect] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<DriftReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listImportDialects()
      .then((all) => {
        setDialects(all);
        setDialect((current) => current || all[0]?.dialect || '');
      })
      .catch((e) => setError(errMessage(e)));
  }, []);

  async function compare(e: React.FormEvent) {
    e.preventDefault();
    if (!modelId || !file || !dialect) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await driftReport(modelId, file, dialect));
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const s = report?.summary;

  return (
    <section aria-label="Drift report" style={container}>
      <div style={header}>
        <div style={title}>Drift report</div>
        <button type="button" onClick={onClose} aria-label="Close drift report" style={closeBtn}>
          ✕
        </button>
      </div>

      <div style={body}>
        <form onSubmit={compare} style={form}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Deployed schema DDL file</span>
            <input
              type="file"
              accept=".sql,.ddl,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Dialect of the file</span>
            <select value={dialect} onChange={(e) => setDialect(e.target.value)} style={input}>
              {dialects.map((d) => (
                <option key={d.dialect} value={d.dialect}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={busy || !file || !dialect} style={primaryBtn}>
            {busy ? 'Comparing…' : 'Compare'}
          </button>
        </form>

        {error && (
          <p role="alert" style={{ ...note, color: semantic.breaking.onLight }}>
            {error}
          </p>
        )}

        {report && s && (
          <div aria-label="Drift report result" style={result}>
            {report.warnings.map((w) => (
              <p key={w} role="alert" style={warning}>
                <strong>Unreconciled import.</strong> {w}
              </p>
            ))}
            <p style={note}>
              <strong>Design:</strong> {sourceLine(report.design)}
            </p>
            <p style={note}>
              <strong>Deployed:</strong> {sourceLine(report.deployed)}
            </p>
            <p style={note}>
              <strong>Drifts:</strong> {s.total} — {s.breaking} breaking, {s['non-breaking']} non-breaking,{' '}
              {s.informational} informational; {s.verified_fields_affected} touch a verified field
            </p>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={cell}>Class</th>
                  <th style={cell}>Rule</th>
                  <th style={cell}>Drift</th>
                  <th style={cell}>Where</th>
                  <th style={cell}>Flag</th>
                </tr>
              </thead>
              <tbody>
                {report.drifts.map((d, i) => (
                  <tr key={`${d.kind}-${where(d)}-${i}`}>
                    <td style={cell}>{d.class}</td>
                    <td style={cell} title={d.rule_text}>
                      {d.rule}
                    </td>
                    <td style={cell}>{d.kind.replace(/_/g, ' ')}</td>
                    <td style={cell}>{where(d)}</td>
                    <td style={{ ...cell, color: semantic.preview.onLight }}>
                      {d.flag ? `${d.flag}: ${d.verified_fields_affected.join(', ')}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {report.possible_renames.length > 0 && (
              <div>
                <div style={labelStyle}>Possible renames (hints, not counted as renames)</div>
                <ul>
                  {report.possible_renames.map((h) => (
                    <li key={`${h.table}-${h.removed}-${h.added}`}>
                      {h.table}: {h.removed} removed and {h.added} added, same type ({h.type}) at position{' '}
                      {h.position}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
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
  alignItems: 'center',
  padding: space.lg,
  borderBottom: `1px solid ${color.neutral[200]}`,
};

const title: React.CSSProperties = { fontSize: type.h3.size, fontWeight: type.h3.weight };

const body: React.CSSProperties = {
  padding: space.lg,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: space.md,
};

const form: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.sm };

const fieldStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.xs };

const labelStyle: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[600],
};

const note: React.CSSProperties = { fontSize: type.uiSmall.size, color: color.neutral[700], margin: 0 };

const warning: React.CSSProperties = {
  margin: 0,
  padding: space.md,
  border: `2px solid ${semantic.preview.onLight}`,
  borderRadius: radius.md,
  fontSize: type.uiSmall.size,
};

const input: React.CSSProperties = {
  padding: `${space.xs}px ${space.sm}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: type.uiSmall.size,
};

const result: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.sm };

const tableStyle: React.CSSProperties = { borderCollapse: 'collapse', width: '100%' };

const cell: React.CSSProperties = {
  border: `1px solid ${color.neutral[200]}`,
  padding: `${space.xs}px ${space.sm}px`,
  fontSize: type.uiXSmall.size,
  textAlign: 'left',
};

const primaryBtn: React.CSSProperties = {
  alignSelf: 'flex-start',
  padding: `${space.sm}px ${space.md}px`,
  borderRadius: radius.md,
  border: 'none',
  background: color.blue,
  color: color.white,
  fontWeight: type.uiXSmall.weight,
  cursor: 'pointer',
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: type.body.size,
  color: color.neutral[500],
  cursor: 'pointer',
};
