'use client';

/**
 * ExportPanel — generates and displays artifacts for the current model in the
 * Monaco CodeEditor. Tabs cover core artifacts (SQL DDL / dbt / Cube.js),
 * synthetic seed data (FR-2.4), governance data contracts (FR-2.3), and BI
 * semantic layers (FR-2.3).
 */

import { useState } from 'react';

import CodeEditor from '@/components/editor/CodeEditor';
import {
  downloadExportZip,
  exportArtifact,
  exportContract,
  exportSemantic,
  exportSyntheticData,
} from '@/lib/api';
import { useCanvasStore } from '@/store/canvasStore';
import type {
  ContractFormat,
  ExportFormat,
  SeedFormat,
  SemanticEngine,
} from '@/types/schema';

type Kind = 'artifact' | 'seed' | 'contract' | 'semantic';

const KINDS: { value: Kind; label: string }[] = [
  { value: 'artifact', label: 'Artifacts' },
  { value: 'seed', label: 'Seed data' },
  { value: 'contract', label: 'Contracts' },
  { value: 'semantic', label: 'Semantic' },
];

const FORMATS: { value: ExportFormat; label: string }[] = [
  { value: 'ddl', label: 'SQL DDL' },
  { value: 'dbt', label: 'dbt' },
  { value: 'cube', label: 'Cube.js' },
];

const DIALECTS = ['snowflake', 'postgres', 'bigquery', 'databricks', 'duckdb'];

const SEED_FORMATS: { value: SeedFormat; label: string }[] = [
  { value: 'sql_insert', label: 'SQL INSERT' },
  { value: 'csv', label: 'CSV bundle' },
];

const CONTRACT_FORMATS: { value: ContractFormat; label: string }[] = [
  { value: 'opendatacontract', label: 'OpenDataContract' },
  { value: 'avro', label: 'Apache Avro' },
  { value: 'protobuf', label: 'Protobuf' },
];

const SEMANTIC_ENGINES: { value: SemanticEngine; label: string }[] = [
  { value: 'cube', label: 'Cube.js' },
  { value: 'lookml', label: 'LookML' },
  { value: 'metricflow', label: 'MetricFlow' },
];

/** Pick a Monaco language id from a file path. */
function languageFor(path: string | null): string {
  if (!path) return 'plaintext';
  if (path.endsWith('.sql')) return 'sql';
  if (path.endsWith('.yml') || path.endsWith('.yaml')) return 'yaml';
  if (path.endsWith('.js')) return 'javascript';
  if (path.endsWith('.json') || path.endsWith('.avsc')) return 'json';
  return 'plaintext';
}

export default function ExportPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);

  const [kind, setKind] = useState<Kind>('artifact');
  const [format, setFormat] = useState<ExportFormat>('ddl');
  const [dialect, setDialect] = useState('snowflake');
  const [seedFormat, setSeedFormat] = useState<SeedFormat>('sql_insert');
  const [rowCount, setRowCount] = useState(50);
  const [contractFormat, setContractFormat] =
    useState<ContractFormat>('opendatacontract');
  const [semanticEngine, setSemanticEngine] = useState<SemanticEngine>('cube');

  const [files, setFiles] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!modelId) return;
    setLoading(true);
    setError(null);
    try {
      let result: { files: Record<string, string> };
      if (kind === 'seed') {
        result = await exportSyntheticData(modelId, {
          row_count_per_entity: rowCount,
          format: seedFormat,
          dialect,
        });
      } else if (kind === 'contract') {
        result = await exportContract(modelId, contractFormat);
      } else if (kind === 'semantic') {
        result = await exportSemantic(modelId, semanticEngine);
      } else {
        result = await exportArtifact(modelId, format, dialect);
      }
      setFiles(result.files);
      setActiveFile(Object.keys(result.files)[0] ?? null);
    } catch (err) {
      setError(errMessage(err));
      setFiles({});
      setActiveFile(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadZip() {
    if (!modelId) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadExportZip(modelId, format, dialect);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setDownloading(false);
    }
  }

  function handleDownloadFile() {
    if (!activeFile) return;
    const blob = new Blob([files[activeFile] ?? ''], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = activeFile.split('/').pop() ?? activeFile;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const fileNames = Object.keys(files);
  const activeContent = activeFile ? (files[activeFile] ?? '') : '';
  const zipEligible = kind === 'artifact' && (format === 'dbt' || format === 'cube');
  const dialectRelevant =
    (kind === 'artifact' && format === 'ddl') || kind === 'seed';

  return (
    <div style={containerStyle}>
      {/* Kind tabs */}
      <div style={tabRow}>
        {KINDS.map((k) => (
          <button
            key={k.value}
            type="button"
            onClick={() => {
              setKind(k.value);
              setFiles({});
              setActiveFile(null);
              setError(null);
            }}
            style={{
              ...tabBtn,
              background: kind === k.value ? '#2563eb' : 'transparent',
              color: kind === k.value ? '#ffffff' : '#94a3b8',
            }}
          >
            {k.label}
          </button>
        ))}
        <button type="button" onClick={onClose} style={{ ...tabBtn, marginLeft: 'auto' }}>
          ✕
        </button>
      </div>

      {/* Controls */}
      <div style={controlRow}>
        {kind === 'artifact' && (
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
        )}
        {kind === 'seed' && (
          <>
            <select
              value={seedFormat}
              onChange={(e) => setSeedFormat(e.target.value as SeedFormat)}
              style={selectStyle}
            >
              {SEED_FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <label style={{ color: '#94a3b8', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              Rows
              <input
                type="range"
                min={1}
                max={500}
                value={rowCount}
                onChange={(e) => setRowCount(Number(e.target.value))}
              />
              <span style={{ color: '#e2e8f0', width: 30 }}>{rowCount}</span>
            </label>
          </>
        )}
        {kind === 'contract' && (
          <select
            value={contractFormat}
            onChange={(e) => setContractFormat(e.target.value as ContractFormat)}
            style={selectStyle}
          >
            {CONTRACT_FORMATS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        )}
        {kind === 'semantic' && (
          <select
            value={semanticEngine}
            onChange={(e) => setSemanticEngine(e.target.value as SemanticEngine)}
            style={selectStyle}
          >
            {SEMANTIC_ENGINES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        )}
        {dialectRelevant && (
          <select
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
            style={selectStyle}
          >
            {DIALECTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading || !modelId}
          style={{
            ...actionBtn,
            background: loading ? '#64748b' : '#2563eb',
            color: '#fff',
            cursor: loading || !modelId ? 'default' : 'pointer',
          }}
        >
          {loading ? 'Generating…' : 'Generate'}
        </button>
        {zipEligible && (
          <button
            type="button"
            onClick={handleDownloadZip}
            disabled={downloading || !modelId}
            title="Download the full project as a .zip"
            style={{ ...actionBtn, border: '1px solid #334155', color: '#e2e8f0' }}
          >
            {downloading ? 'Zipping…' : '.ZIP'}
          </button>
        )}
        {activeFile && (
          <button
            type="button"
            onClick={handleDownloadFile}
            title="Download the current file"
            style={{ ...actionBtn, border: '1px solid #334155', color: '#e2e8f0' }}
          >
            Download
          </button>
        )}
      </div>

      {fileNames.length > 1 && (
        <select
          value={activeFile ?? ''}
          onChange={(e) => setActiveFile(e.target.value)}
          style={{ ...selectStyle, margin: 8, background: '#1e293b', color: '#e2e8f0' }}
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
            Synthesize or introspect a model first to export.
          </p>
        ) : fileNames.length === 0 ? (
          <p style={{ color: '#94a3b8', padding: 12 }}>
            Choose options and click Generate.
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

function errMessage(e: unknown): string {
  if (
    typeof e === 'object' &&
    e !== null &&
    'response' in e &&
    typeof (e as { response?: unknown }).response === 'object'
  ) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response
      ?.data?.detail;
    if (typeof detail === 'string') return detail;
  }
  return e instanceof Error ? e.message : 'Export failed.';
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  borderLeft: '1px solid #e2e8f0',
  background: '#0f172a',
};

const tabRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: '6px 8px',
  background: '#1e293b',
};

const tabBtn: React.CSSProperties = {
  padding: '4px 12px',
  borderRadius: 6,
  border: 'none',
  background: 'transparent',
  color: '#94a3b8',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const controlRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 12px',
  background: '#1e293b',
  color: '#e2e8f0',
  flexWrap: 'wrap',
  borderTop: '1px solid #0f172a',
};

const selectStyle: React.CSSProperties = {
  padding: '4px 8px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  fontSize: 12,
};

const actionBtn: React.CSSProperties = {
  padding: '4px 12px',
  borderRadius: 6,
  border: 'none',
  background: '#0f172a',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};
