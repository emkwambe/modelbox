'use client';

/**
 * Import a DDL file (Sprint 8).
 *
 * The consultant's front door: a client's exported DDL, uploaded as a file,
 * becomes a model on the canvas with a reconciliation report beside it.
 * Nothing connects to the client's systems — the file is read on this
 * appliance. The dialects offered, and the evidence behind each, come from
 * `GET /import/dialects`; this page keeps no list of its own.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  getImportReport,
  getModel,
  importDdl,
  listImportDialects,
  listWorkspaces,
} from '@/lib/api';
import {
  Button,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
  StatusText,
} from '@/components/ui';
import { errMessage, errorKind } from '@/lib/errors';
import type { ErrorKind } from '@/lib/errors';
import { color, radius, space, type as typeScale } from '@/styles/tokens';
import { useAuthStatus, useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import type { ImportDialectInfo, ImportResponse, WorkspaceInfo } from '@/types/schema';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready' }
  | { status: 'failed'; kind: ErrorKind; message: string };

const COUNT_ROWS: [string, string][] = [
  ['count', 'Tables'],
  ['columns', 'Columns'],
  ['primary_keys', 'Primary keys'],
  ['foreign_keys', 'Foreign keys'],
  ['unique_constraints', 'UNIQUE constraints'],
  ['check_constraints', 'CHECK constraints'],
  ['table_descriptions', 'Table descriptions'],
  ['column_descriptions', 'Column descriptions'],
];

export default function ImportPage() {
  const router = useRouter();
  const openModal = useAuthStore((s) => s.openModal);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const loadModel = useCanvasStore((s) => s.loadModel);
  const authStatus = useAuthStatus();
  const signedIn = authStatus === 'signed-in';

  const [dialects, setDialects] = useState<ImportDialectInfo[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ status: 'loading' });
  const [dialect, setDialect] = useState('');
  const [workspaceId, setWorkspaceId] = useState('');
  const [title, setTitle] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResponse | null>(null);

  const load = useCallback(async () => {
    setLoadState({ status: 'loading' });
    try {
      const [found, spaces] = await Promise.all([listImportDialects(), listWorkspaces()]);
      setDialects(found);
      setWorkspaces(spaces);
      setDialect((current) => current || found[0]?.dialect || '');
      setWorkspaceId((current) => current || activeWorkspaceId || spaces[0]?.workspace_id || '');
      setLoadState({ status: 'ready' });
    } catch (e) {
      setLoadState({
        status: 'failed',
        kind: errorKind(e),
        message: errMessage(e, 'The import options could not be loaded.'),
      });
    }
  }, [activeWorkspaceId]);

  useEffect(() => {
    if (signedIn) void load();
  }, [signedIn, load]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !dialect || !workspaceId) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await importDdl({ workspaceId, file, dialect, title: title.trim() || undefined }),
      );
    } catch (err) {
      setError(errMessage(err, 'The file could not be imported.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpen(modelId: string) {
    try {
      loadModel(await getModel(modelId));
      router.push('/canvas');
    } catch (err) {
      setError(errMessage(err, 'The model could not be opened.'));
    }
  }

  async function handleDownload(modelId: string, format: 'markdown' | 'json') {
    try {
      const body = await getImportReport(modelId, format);
      const blob = new Blob([body], {
        type: format === 'json' ? 'application/json' : 'text/markdown',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `import-report.${format === 'json' ? 'json' : 'md'}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errMessage(err, 'The report could not be downloaded.'));
    }
  }

  const chosen = dialects.find((d) => d.dialect === dialect);

  if (authStatus === 'unknown') {
    return (
      <main style={pageStyle}>
        <h1 style={headingStyle}>Import a DDL file</h1>
        <LoadingState label="Checking your session…" />
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <Link href="/" style={backLink}>
        ← ModelBox AI
      </Link>
      <h1 style={headingStyle}>Import a DDL file</h1>
      <p style={leadStyle}>
        Upload a schema exported from a client&apos;s database. It is read on this
        appliance: nothing connects to the client&apos;s systems. Every import is
        reconciled against counts taken from the file itself, and the report says
        exactly what matched.
      </p>

      {!signedIn && (
        <div style={panelStyle}>
          <p style={{ margin: 0, color: color.neutral[600] }}>Sign in to import a file.</p>
          <Button variant="primary" onClick={openModal}>
            Sign in
          </Button>
        </div>
      )}

      {signedIn && loadState.status === 'loading' && (
        <LoadingState label="Loading import options…" />
      )}
      {signedIn && loadState.status === 'failed' && (
        <ErrorState
          kind={loadState.kind}
          title="The import options could not be loaded"
          onRetry={() => void load()}
        >
          {loadState.message}
        </ErrorState>
      )}

      {signedIn && loadState.status === 'ready' && (
        <form onSubmit={handleSubmit} style={panelStyle}>
          <Field label="Workspace" required>
            <Select value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)}>
              {workspaces.map((w) => (
                <option key={w.workspace_id} value={w.workspace_id}>
                  {w.name} ({w.role})
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Dialect of the file"
            required
            description={chosen ? `${chosen.tool}. Tested against: ${chosen.evidence}.` : undefined}
          >
            <Select value={dialect} onChange={(e) => setDialect(e.target.value)}>
              {dialects.map((d) => (
                <option key={d.dialect} value={d.dialect}>
                  {d.label} ({d.evidence})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Model title" description="Defaults to the file's name.">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} />
          </Field>
          <Field label="DDL file" required description="UTF-8 or UTF-16, with or without a BOM.">
            <Input
              type="file"
              accept=".sql,.ddl,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Field>
          <Button type="submit" variant="primary" loading={busy} disabled={!file || !dialect || !workspaceId}>
            {busy ? 'Importing…' : 'Import'}
          </Button>
        </form>
      )}

      {error && (
        <div style={{ marginTop: space.lg }}>
          <StatusText tone="breaking">{error}</StatusText>
        </div>
      )}

      {result && (
        <section style={panelStyle} aria-label="Import result">
          <h2 style={subheadingStyle}>{result.title}</h2>
          <StatusText tone={result.status === 'reconciled' ? 'validated' : 'breaking'}>
            {result.status === 'reconciled'
              ? `Reconciled: ${result.entities} tables and ${result.relationships} relationships, every count matching the file.`
              : 'Unreconciled: the import has gaps or failures, listed below. No dictionary built from it may call itself verified.'}
          </StatusText>

          {result.report.reconciliation && (
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={cellStyle} scope="col" />
                  <th style={cellStyle} scope="col">Tables: file</th>
                  <th style={cellStyle} scope="col">Tables: imported</th>
                  <th style={cellStyle} scope="col">Partitions: file</th>
                  <th style={cellStyle} scope="col">Partitions: imported</th>
                </tr>
              </thead>
              <tbody>
                {COUNT_ROWS.map(([key, label]) => {
                  const { source, imported } = result.report.reconciliation!;
                  return (
                    <tr key={key}>
                      <th style={cellStyle} scope="row">{label}</th>
                      <td style={cellStyle}>{source.tables[key]}</td>
                      <td style={cellStyle}>{imported.tables[key]}</td>
                      <td style={cellStyle}>{source.partitions[key]}</td>
                      <td style={cellStyle}>{imported.partitions[key]}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {(result.report.reconciliation?.gaps.length ?? 0) > 0 && (
            <>
              <h3 style={minorHeadingStyle}>Gaps</h3>
              <ul>
                {result.report.reconciliation!.gaps.map((gap) => (
                  <li key={`${gap.table}-${gap.kind}`}>
                    {gap.table}, {gap.kind}: file {gap.source}, imported {gap.imported}
                    {gap.statements[0] ? ` (statement ${gap.statements[0].index}, line ${gap.statements[0].line})` : ''}
                  </li>
                ))}
              </ul>
            </>
          )}
          {result.report.failures.length > 0 && (
            <>
              <h3 style={minorHeadingStyle}>Failures</h3>
              <ul>
                {result.report.failures.map((f, i) => (
                  <li key={`${f.statement ?? 'file'}-${i}`}>
                    {f.statement ? `Statement ${f.statement} (line ${f.line})` : 'The file'}
                    {f.head ? `, ${f.head}` : ''}: {f.reason}
                  </li>
                ))}
              </ul>
            </>
          )}

          <div style={{ display: 'flex', gap: space.sm, flexWrap: 'wrap' }}>
            <Button variant="primary" onClick={() => void handleOpen(result.model_id)}>
              Open on the canvas →
            </Button>
            <Button onClick={() => void handleDownload(result.model_id, 'markdown')}>
              Report (Markdown)
            </Button>
            <Button onClick={() => void handleDownload(result.model_id, 'json')}>
              Report (JSON)
            </Button>
          </div>
        </section>
      )}
    </main>
  );
}

const pageStyle: React.CSSProperties = { maxWidth: 820, margin: '0 auto', padding: '48px 24px' };

const headingStyle: React.CSSProperties = {
  fontSize: typeScale.h2.size,
  fontWeight: typeScale.h2.weight,
  lineHeight: typeScale.h2.lineHeight,
  marginTop: space.sm,
};

const subheadingStyle: React.CSSProperties = {
  fontSize: typeScale.h3.size,
  fontWeight: typeScale.h3.weight,
  lineHeight: typeScale.h3.lineHeight,
  margin: 0,
};

const minorHeadingStyle: React.CSSProperties = {
  fontSize: typeScale.bodySmall.size,
  fontWeight: typeScale.h3.weight,
  margin: `${space.sm}px 0 0`,
};

const leadStyle: React.CSSProperties = { color: color.neutral[600], marginTop: space.xs };

const backLink: React.CSSProperties = { color: color.blue, textDecoration: 'none' };

const panelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.md,
  marginTop: space.xl,
  padding: space.lg,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: radius.lg,
  background: color.neutral[50],
};

const tableStyle: React.CSSProperties = {
  borderCollapse: 'collapse',
  fontSize: typeScale.uiSmall.size,
  background: color.white,
};

const cellStyle: React.CSSProperties = {
  border: `1px solid ${color.neutral[200]}`,
  padding: `${space.xs}px ${space.sm}px`,
  textAlign: 'left',
};
