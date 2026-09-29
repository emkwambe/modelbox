'use client';

/**
 * ExportPanel — generates and displays artifacts for the current model in the
 * Monaco CodeEditor. Tabs cover core artifacts (SQL DDL / dbt / Cube.js),
 * synthetic seed data (FR-2.4), governance data contracts (FR-2.3), and BI
 * semantic layers (FR-2.3).
 */

import { useEffect, useState } from 'react';

import CodeEditor from '@/components/editor/CodeEditor';
import { StatusText } from '@/components/ui';
import {
  downloadExportZip,
  exportArtifact,
  exportContract,
  exportDictionary,
  exportSemantic,
  exportSyntheticData,
  listArtifactStatus,
} from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { useCanvasStore } from '@/store/canvasStore';
import { color, semantic, surface } from '@/styles/tokens';
import type {
  ArtifactStatusInfo,
  ContractFormat,
  DictionaryFormat,
  ExportFormat,
  SeedFormat,
  SemanticEngine,
} from '@/types/schema';

type Kind = 'artifact' | 'seed' | 'contract' | 'semantic' | 'dictionary';

const KINDS: { value: Kind; label: string }[] = [
  { value: 'artifact', label: 'Artifacts' },
  { value: 'seed', label: 'Seed data' },
  { value: 'contract', label: 'Contracts' },
  { value: 'semantic', label: 'Semantic' },
  { value: 'dictionary', label: 'Dictionary' },
];

const FORMATS: { value: ExportFormat; label: string }[] = [
  { value: 'ddl', label: 'SQL DDL' },
  { value: 'dbt', label: 'dbt' },
  { value: 'cube', label: 'Cube.js' },
];

/**
 * Verification status comes from `GET /export/status`, never from this file.
 *
 * These lists used to be written here as literals, and a test in the fidelity
 * harness read this source as *text* to check they still matched what the
 * harness verified. The label therefore reached the user by being retyped, and
 * the check ran backwards: the harness verified the UI's source code.
 *
 * The status is shown before the user commits to an export — a warning
 * discovered afterwards is not a warning.
 */
const STATUS_LABEL: Record<string, string> = {
  CERTIFIED: 'Certified',
  PREVIEW: 'Preview',
  UNVERIFIED: 'Unverified',
};

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

const DICTIONARY_FORMATS: { value: DictionaryFormat; label: string }[] = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
  { value: 'json', label: 'JSON' },
];

/** Pick a Monaco language id from a file path. */
function languageFor(path: string | null): string {
  if (!path) return 'plaintext';
  if (path.endsWith('.sql')) return 'sql';
  if (path.endsWith('.yml') || path.endsWith('.yaml')) return 'yaml';
  if (path.endsWith('.js')) return 'javascript';
  if (path.endsWith('.json') || path.endsWith('.avsc')) return 'json';
  if (path.endsWith('.md')) return 'markdown';
  if (path.endsWith('.html')) return 'html';
  return 'plaintext';
}

export default function ExportPanel({ onClose }: { onClose: () => void }) {
  const modelId = useCanvasStore((s) => s.modelId);

  const [kind, setKind] = useState<Kind>('artifact');
  const [format, setFormat] = useState<ExportFormat>('ddl');
  // Empty until the manifest arrives, then the first certified dialect. Naming
  // one here would be the same defect in miniature: a dialect the UI asserts
  // exists, unchecked against the appliance that has to emit it.
  const [dialect, setDialect] = useState('');
  const [seedFormat, setSeedFormat] = useState<SeedFormat>('sql_insert');
  const [rowCount, setRowCount] = useState(50);
  const [contractFormat, setContractFormat] =
    useState<ContractFormat>('opendatacontract');
  const [semanticEngine, setSemanticEngine] = useState<SemanticEngine>('cube');
  const [dictionaryFormat, setDictionaryFormat] =
    useState<DictionaryFormat>('markdown');

  const [files, setFiles] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<ArtifactStatusInfo[] | null>(null);

  // Fetched once. A failure leaves `statuses` null and every badge simply
  // absent — the panel keeps working, and it says nothing it cannot support
  // rather than defaulting a variant to "certified" because the fetch failed.
  useEffect(() => {
    let cancelled = false;
    listArtifactStatus()
      .then((rows) => {
        if (cancelled) return;
        setStatuses(rows);
        const firstCertified = rows.find(
          (r) => r.family === 'ddl' && r.status === 'CERTIFIED',
        );
        if (firstCertified) setDialect((d) => d || firstCertified.variant);
      })
      .catch(() => {
        if (!cancelled) setStatuses([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const statusFor = (variant: string): ArtifactStatusInfo | undefined =>
    statuses?.find((s) => s.variant === variant);

  const certifiedDialects = (statuses ?? []).filter(
    (s) => s.family === 'ddl' && s.status === 'CERTIFIED',
  );
  const previewDialects = (statuses ?? []).filter(
    (s) => s.family === 'ddl' && s.status !== 'CERTIFIED',
  );

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
      } else if (kind === 'dictionary') {
        result = await exportDictionary(modelId, dictionaryFormat);
      } else {
        result = await exportArtifact(modelId, format, dialect);
      }
      setFiles(result.files);
      setActiveFile(Object.keys(result.files)[0] ?? null);
    } catch (err) {
      setError(errMessage(err, 'Export failed.'));
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
      setError(errMessage(err, 'Export failed.'));
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

  // What the user has actually selected, whatever kind they are on. The status
  // badge previously reached only DDL and seed, because it was gated on
  // `dialectRelevant` — the one control that happens to be a dialect picker.
  const selectedVariant =
    kind === 'artifact'
      ? format === 'ddl'
        ? dialect
        : format
      : kind === 'seed'
        ? seedFormat
        : kind === 'contract'
          ? contractFormat
          : kind === 'semantic'
            ? semanticEngine
            : dictionaryFormat;
  const selectedStatus = statusFor(selectedVariant);

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
              background: kind === k.value ? color.blue : 'transparent',
              color: kind === k.value ? color.white : color.neutral[400],
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
            <label style={{ color: color.neutral[400], fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              Rows
              <input
                type="range"
                min={1}
                max={500}
                value={rowCount}
                onChange={(e) => setRowCount(Number(e.target.value))}
              />
              <span style={{ color: color.neutral[200], width: 30 }}>{rowCount}</span>
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
        {kind === 'dictionary' && (
          <select
            value={dictionaryFormat}
            onChange={(e) => setDictionaryFormat(e.target.value as DictionaryFormat)}
            style={selectStyle}
          >
            {DICTIONARY_FORMATS.map((f) => (
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
            <optgroup label="Certified — deployment-verified">
              {certifiedDialects.map((d) => (
                <option key={d.variant} value={d.variant}>
                  {d.variant}
                </option>
              ))}
            </optgroup>
            <optgroup label="Preview — not deployment-verified">
              {previewDialects.map((d) => (
                <option key={d.variant} value={d.variant}>
                  {d.variant} (preview)
                </option>
              ))}
            </optgroup>
          </select>
        )}
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading || !modelId}
          style={{
            ...actionBtn,
            background: loading ? color.neutral[500] : color.blue,
            color: color.white,
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
            style={{ ...actionBtn, border: `1px solid ${color.neutral[700]}`, color: color.neutral[200] }}
          >
            {downloading ? 'Zipping…' : '.ZIP'}
          </button>
        )}
        {activeFile && (
          <button
            type="button"
            onClick={handleDownloadFile}
            title="Download the current file"
            style={{ ...actionBtn, border: `1px solid ${color.neutral[700]}`, color: color.neutral[200] }}
          >
            Download
          </button>
        )}
      </div>

      {/* Every artifact carries its status, not only the SQL dialects. Seven
          families — dbt, Cube, LookML, MetricFlow, ODCS, Avro, Protobuf — plus
          the three dictionary formats previously showed nothing at all, so a
          user could not tell a contract verified by protoc from a dictionary
          nothing has ever checked. */}
      {selectedStatus && selectedStatus.status !== 'CERTIFIED' && (
        <div style={statusBanner(selectedStatus.status)} role="status">
          <strong>{selectedVariant}</strong> is{' '}
          <strong>{STATUS_LABEL[selectedStatus.status]}</strong>.{' '}
          {selectedStatus.reason}
        </div>
      )}

      {fileNames.length > 1 && (
        <select
          value={activeFile ?? ''}
          onChange={(e) => setActiveFile(e.target.value)}
          style={{ ...selectStyle, margin: 8, background: color.neutral[800], color: color.neutral[200] }}
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
          /*
            `#f87171` is Tailwind's red-400. Stated plainly because it is the
            uncomfortable direction: measured on this panel it is **6.45:1**,
            and the `breaking.onDark` token replacing it is **4.86:1**. The
            conversion *lowers* contrast here.
            Both clear the 4.5:1 body floor, and the reason to take the token
            anyway is that a product with two reds has no red — the panel would
            otherwise disagree with every other failure in the product about
            what failure looks like. Where that trade is not available, the
            floor wins and the token moves; that is what `neutral-400` ->
            `neutral-500` did inside `EntityNode`.
          */
          <div style={{ padding: 12 }}>
            <StatusText tone="breaking" on="dark">
              {error}
            </StatusText>
          </div>
        ) : !modelId ? (
          <p style={{ color: color.neutral[400], padding: 12 }}>
            Synthesize or introspect a model first to export.
          </p>
        ) : fileNames.length === 0 ? (
          <p style={{ color: color.neutral[400], padding: 12 }}>
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

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  borderLeft: `1px solid ${color.neutral[200]}`,
  background: surface.panel,
};

const tabRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: '6px 8px',
  background: color.neutral[800],
};

const tabBtn: React.CSSProperties = {
  padding: '4px 12px',
  borderRadius: 6,
  border: 'none',
  background: 'transparent',
  color: color.neutral[400],
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const controlRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 12px',
  background: color.neutral[800],
  color: color.neutral[200],
  flexWrap: 'wrap',
  borderTop: `1px solid ${surface.panel}`,
};

/**
 * The panel sits on a dark ground, so these take the `onDark` variants.
 *
 * Preview and Unverified are deliberately different colours. "We checked and it
 * is not deployment-verified" and "nothing has ever checked this" are different
 * statements, and giving them one badge would let the second hide inside the
 * first — which is exactly how three dictionary formats came to sit beside
 * protoc-verified contracts looking equally reviewed.
 */
const statusBanner = (status: string): React.CSSProperties => {
  const accent =
    status === 'UNVERIFIED' ? semantic.breaking.onDark : semantic.preview.onDark;
  return {
    margin: '0 8px 8px',
    padding: '8px 10px',
    borderRadius: 6,
    background: surface.panel,
    border: `1px solid ${accent}`,
    color: accent,
    fontSize: 12,
    lineHeight: 1.45,
  };
};

const selectStyle: React.CSSProperties = {
  padding: '4px 8px',
  borderRadius: 6,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: 12,
};

const actionBtn: React.CSSProperties = {
  padding: '4px 12px',
  borderRadius: 6,
  border: 'none',
  background: surface.panel,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};
