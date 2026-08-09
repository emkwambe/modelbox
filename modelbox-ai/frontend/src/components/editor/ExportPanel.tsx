'use client';

/**
 * ExportPanel — generates and displays artifacts (SQL DDL / dbt / Cube.js) for
 * the current model, rendering each file in the Monaco CodeEditor.
 */

import { useState } from 'react';

import CodeEditor from '@/components/editor/CodeEditor';
import { exportArtifact } from '@/lib/api';
import { useCanvasStore } from '@/store/canvasStore';
import type { ExportFormat } from '@/types/schema';

const FORMATS: { value: ExportFormat; label: string }[] = [
  { value: 'ddl', label: 'SQL DDL' },
  { value: 'dbt', label: 'dbt' },
  { value: 'cube', label: 'Cube.js' },
];

const DIALECTS = ['snowflake', 'postgres', 'bigquery', 'databricks', 'duckdb'];

/** Pick a Monaco language id from a file path. */
function languageFor(path: string | null): string {
  if (!path) return 'plaintext';
  if (path.endsWith('.sql')) return 'sql';
  if (path.endsWith('.yml') || path.endsWith('.yaml')) return 'yaml';
  if (path.endsWith('.js')) return 'javascript';
  return 'plaintext';
}

export default function ExportPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);

  const [format, setFormat] = useState<ExportFormat>('ddl');
  const [dialect, setDialect] = useState('snowflake');
  const [files, setFiles] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!modelId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await exportArtifact(modelId, format, dialect);
      setFiles(result.files);
      setActiveFile(Object.keys(result.files)[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.');
      setFiles({});
      setActiveFile(null);
    } finally {
      setLoading(false);
    }
  }

  const fileNames = Object.keys(files);
  const activeContent = activeFile ? (files[activeFile] ?? '') : '';

  const selectStyle: React.CSSProperties = {
    padding: '4px 8px',
    borderRadius: 6,
    border: '1px solid #cbd5e1',
    fontSize: 12,
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        borderLeft: '1px solid #e2e8f0',
        background: '#0f172a',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          background: '#1e293b',
          color: '#e2e8f0',
          flexWrap: 'wrap',
        }}
      >
        <strong style={{ fontSize: 13 }}>Export</strong>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value as ExportFormat)}
          style={selectStyle}
        >
          {FORMATS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <select
          value={dialect}
          onChange={(e) => setDialect(e.target.value)}
          disabled={format !== 'ddl'}
          style={{ ...selectStyle, opacity: format === 'ddl' ? 1 : 0.4 }}
        >
          {DIALECTS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading || !modelId}
          style={{
            padding: '4px 12px',
            borderRadius: 6,
            border: 'none',
            background: loading ? '#64748b' : '#2563eb',
            color: '#fff',
            fontSize: 12,
            fontWeight: 600,
            cursor: loading || !modelId ? 'default' : 'pointer',
          }}
        >
          {loading ? 'Generating…' : 'Generate'}
        </button>
        <button
          type="button"
          onClick={onClose}
          style={{ ...selectStyle, marginLeft: 'auto', cursor: 'pointer' }}
        >
          ✕
        </button>
      </div>

      {fileNames.length > 1 && (
        <select
          value={activeFile ?? ''}
          onChange={(e) => setActiveFile(e.target.value)}
          style={{
            ...selectStyle,
            margin: 8,
            background: '#1e293b',
            color: '#e2e8f0',
          }}
        >
          {fileNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      )}

      <div style={{ flex: 1, minHeight: 0 }}>
        {error ? (
          <p style={{ color: '#f87171', padding: 12 }} role="alert">
            {error}
          </p>
        ) : !modelId ? (
          <p style={{ color: '#94a3b8', padding: 12 }}>
            Synthesize a model first to export artifacts.
          </p>
        ) : fileNames.length === 0 ? (
          <p style={{ color: '#94a3b8', padding: 12 }}>
            Choose a format and click Generate.
          </p>
        ) : (
          <CodeEditor
            value={activeContent}
            language={languageFor(activeFile)}
            height="100%"
            readOnly
          />
        )}
      </div>
    </div>
  );
}
