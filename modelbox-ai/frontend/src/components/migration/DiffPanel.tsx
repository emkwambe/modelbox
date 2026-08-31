'use client';

/**
 * Schema Diff & Migration panel (FR-2.2).
 *
 * Compares the current canvas model (source / V1) against a chosen target model
 * (V2), rendering the generated ALTER DDL and color-coded breaking changes.
 */

import { useEffect, useMemo, useState } from 'react';

import { diffModels, listModels } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { useCanvasStore } from '@/store/canvasStore';
import type { DiffResponse, ModelInfo } from '@/types/schema';

const DIALECTS = ['postgres', 'snowflake', 'databricks', 'bigquery', 'duckdb', 'redshift'];

export default function DiffPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [targetId, setTargetId] = useState('');
  const [dialect, setDialect] = useState('postgres');
  const [result, setResult] = useState<DiffResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listModels()
      .then(setModels)
      .catch((e) => setError(errMessage(e)));
  }, []);

  // Candidate targets exclude the current (source) model.
  const targets = useMemo(
    () => models.filter((m) => m.model_id !== modelId),
    [models, modelId],
  );

  async function handleDiff() {
    if (!modelId || !targetId) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await diffModels({
          source_model_id: modelId,
          target_model_id: targetId,
          dialect,
        }),
      );
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const ddl = result?.alter_statements.join('\n') ?? '';

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <div>
          <div style={{ fontWeight: 700 }}>Schema Diff &amp; Migration</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>
            Current model → target model
          </div>
        </div>
        <button type="button" onClick={onClose} style={closeBtn}>
          ✕
        </button>
      </div>

      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {!modelId && (
          <p style={{ color: '#dc2626', fontSize: 13 }}>
            Load or save a model first to use it as the diff source.
          </p>
        )}

        <label style={fieldStyle}>
          <span style={labelStyle}>Target model (V2)</span>
          <select
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            style={inputStyle}
          >
            <option value="">Select a model…</option>
            {targets.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {m.title} · v{m.version_number}
              </option>
            ))}
          </select>
        </label>

        <label style={fieldStyle}>
          <span style={labelStyle}>Dialect</span>
          <select
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
            style={inputStyle}
          >
            {DIALECTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={handleDiff}
          disabled={!modelId || !targetId || busy}
          style={{
            ...primaryBtn,
            opacity: !modelId || !targetId || busy ? 0.5 : 1,
          }}
        >
          {busy ? 'Computing…' : 'Compute diff'}
        </button>

        {error && <p style={{ color: '#dc2626', fontSize: 13 }}>{error}</p>}

        {result && (
          <>
            {result.breaking_changes.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={labelStyle}>
                  ⚠ Breaking changes ({result.breaking_changes.length})
                </span>
                {result.breaking_changes.map((b) => (
                  <span key={b} style={breakingBadge}>
                    {b}
                  </span>
                ))}
              </div>
            ) : (
              <span style={{ color: '#16a34a', fontSize: 13, fontWeight: 600 }}>
                ✓ No breaking changes
              </span>
            )}

            {result.semantic_breaks.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={labelStyle}>
                  Σ Semantic impact ({result.semantic_breaks.length})
                </span>
                {result.semantic_breaks.map((s) => (
                  <span key={s} style={semanticBadge}>
                    {s}
                  </span>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={labelStyle}>
                  Migration DDL ({result.alter_statements.length} statement
                  {result.alter_statements.length === 1 ? '' : 's'})
                </span>
                {ddl && (
                  <button
                    type="button"
                    onClick={() => void navigator.clipboard?.writeText(ddl)}
                    style={copyBtn}
                  >
                    Copy
                  </button>
                )}
              </div>
              <pre style={ddlStyle}>
                {ddl || '-- No changes between the two models.'}
              </pre>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  height: '100%',
  borderLeft: '1px solid #e2e8f0',
  background: '#ffffff',
  overflowY: 'auto',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '12px 16px',
  borderBottom: '1px solid #e2e8f0',
  position: 'sticky',
  top: 0,
  background: '#ffffff',
};

const fieldStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: '#475569',
};

const inputStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  fontSize: 14,
};

const primaryBtn: React.CSSProperties = {
  padding: '8px 14px',
  borderRadius: 6,
  border: '1px solid #2563eb',
  background: '#2563eb',
  color: '#ffffff',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: 16,
  color: '#64748b',
  cursor: 'pointer',
  lineHeight: 1,
};

const copyBtn: React.CSSProperties = {
  padding: '2px 8px',
  borderRadius: 4,
  border: '1px solid #cbd5e1',
  background: '#ffffff',
  color: '#334155',
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
};

const breakingBadge: React.CSSProperties = {
  fontSize: 12,
  color: '#b91c1c',
  background: '#fef2f2',
  border: '1px solid #fecaca',
  borderRadius: 6,
  padding: '4px 8px',
};

const semanticBadge: React.CSSProperties = {
  fontSize: 12,
  color: '#6d28d9',
  background: '#f5f3ff',
  border: '1px solid #ddd6fe',
  borderRadius: 6,
  padding: '4px 8px',
};

const ddlStyle: React.CSSProperties = {
  margin: 0,
  padding: 12,
  background: '#0f172a',
  color: '#e2e8f0',
  borderRadius: 6,
  fontSize: 12,
  fontFamily: 'monospace',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  maxHeight: 360,
  overflowY: 'auto',
};
