'use client';

/**
 * Connectors & Introspection settings (FR-2.1).
 *
 * Manage encrypted database connections and one-click "Introspect" a live
 * schema into the canvas as a synthesized model.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  createConnection,
  deleteConnection,
  introspectConnection,
  listConnections,
} from '@/lib/api';
import { ErrorState, LoadingState, StatusText } from '@/components/ui';
import { color, semantic } from '@/styles/tokens';
import { errMessage, errorKind } from '@/lib/errors';
import type { ErrorKind } from '@/lib/errors';
import { useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import type { ConnectionEngine, ConnectionInfo } from '@/types/schema';

const ENGINES: { value: ConnectionEngine; label: string; enabled: boolean }[] = [
  { value: 'POSTGRESQL', label: 'PostgreSQL', enabled: true },
  { value: 'SNOWFLAKE', label: 'Snowflake', enabled: true },
  { value: 'BIGQUERY', label: 'BigQuery', enabled: true },
  { value: 'MYSQL', label: 'MySQL', enabled: true },
];

/**
 * A list load has three outcomes, and "empty" is not one of the first two.
 *
 * Inferring "still loading" from `items.length === 0` conflates an unfinished
 * request with a genuinely empty account, which is how this page came to tell
 * users with keys that they had none.
 */
type ListState =
  | { status: 'loading' }
  | { status: 'ready' }
  | { status: 'failed'; kind: ErrorKind; message: string };

export default function ConnectorsPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const loadModel = useCanvasStore((s) => s.loadModel);

  const [mounted, setMounted] = useState(false);
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [listState, setListState] = useState<ListState>({ status: 'loading' });
  const [name, setName] = useState('');
  const [engine, setEngine] = useState<ConnectionEngine>('POSTGRESQL');
  const [uri, setUri] = useState('');
  const [busy, setBusy] = useState(false);
  const [introspectingId, setIntrospectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);
  const signedIn = mounted && Boolean(token);

  const refresh = useCallback(async () => {
    setListState({ status: 'loading' });
    try {
      setConnections(await listConnections());
      setListState({ status: 'ready' });
    } catch (e) {
      // Separate from `error`, which belongs to create, delete and introspect.
      setListState({
        status: 'failed',
        kind: errorKind(e),
        message: errMessage(e, 'The connections could not be loaded.'),
      });
    }
  }, []);

  useEffect(() => {
    if (signedIn) void refresh();
  }, [signedIn, refresh]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !uri.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createConnection({
        name: name.trim(),
        engine,
        connection_uri: uri.trim(),
        workspace_id: activeWorkspaceId ?? null,
      });
      setName('');
      setUri('');
      await refresh();
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(conn: ConnectionInfo) {
    if (!window.confirm(`Delete connection "${conn.name}"?`)) return;
    setError(null);
    try {
      await deleteConnection(conn.connection_id);
      await refresh();
    } catch (e) {
      setError(errMessage(e));
    }
  }

  async function handleIntrospect(conn: ConnectionInfo) {
    const schema = window.prompt('Schema to introspect:', 'public');
    if (!schema) return;
    setIntrospectingId(conn.connection_id);
    setError(null);
    try {
      const model = await introspectConnection({
        connection_id: conn.connection_id,
        schema_name: schema,
      });
      loadModel(model);
      router.push('/canvas');
    } catch (e) {
      setError(errMessage(e));
      setIntrospectingId(null);
    }
  }

  if (!mounted) return null;

  return (
    <main style={{ maxWidth: 820, margin: '0 auto', padding: '48px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <Link
          href="/"
          style={{ color: color.blue, fontWeight: 600, textDecoration: 'none' }}
        >
          ← ModelBox AI
        </Link>
      </div>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>
        Database Connectors
      </h1>
      <p style={{ color: color.neutral[600], marginTop: 4 }}>
        Register an encrypted connection, then reverse-engineer its schema
        directly onto the canvas. Connection URIs are stored AES-256-GCM
        encrypted and never shown in the clear.
      </p>

      {!signedIn && (
        <div style={panelStyle}>
          <p style={{ margin: 0, color: color.neutral[600] }}>
            Sign in to manage connectors.
          </p>
          <button type="button" onClick={openModal} style={primaryBtn}>
            Sign in
          </button>
        </div>
      )}

      {signedIn && (
        <>
          <form onSubmit={handleCreate} style={panelStyle}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
              New connection
            </h2>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Name</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Prod replica"
                  style={inputStyle}
                />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Engine</span>
                <select
                  value={engine}
                  onChange={(e) => setEngine(e.target.value as ConnectionEngine)}
                  style={inputStyle}
                >
                  {ENGINES.map((opt) => (
                    <option key={opt.value} value={opt.value} disabled={!opt.enabled}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label style={{ ...fieldStyle, width: '100%' }}>
              <span style={labelStyle}>Connection URI</span>
              <input
                value={uri}
                onChange={(e) => setUri(e.target.value)}
                placeholder="postgresql://user:password@host:5432/dbname"
                autoComplete="off"
                spellCheck={false}
                style={{ ...inputStyle, fontFamily: 'monospace' }}
              />
            </label>
            <button type="submit" disabled={busy} style={primaryBtn}>
              {busy ? 'Saving…' : 'Add connection'}
            </button>
          </form>

          <h2 style={{ fontSize: 16, fontWeight: 700, marginTop: 28 }}>
            Connections
          </h2>
          {listState.status === 'loading' ? (
            <LoadingState label="Loading connections…" />
          ) : listState.status === 'failed' ? (
            <ErrorState
              kind={listState.kind}
              title="Your connections could not be loaded"
              onRetry={() => void refresh()}
            >
              {listState.message}
            </ErrorState>
          ) : connections.length === 0 ? (
            // Only reachable once the request has finished; before this the
            // empty state was shown while the first fetch was still open.
            <p style={{ color: color.neutral[500] }}>No connections yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {connections.map((conn) => (
                <div key={conn.connection_id} style={rowStyle}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600 }}>{conn.name}</div>
                    <div style={{ fontSize: 12, color: color.neutral[500] }}>
                      {conn.engine} · {conn.uri_masked ?? 'postgresql://***'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      onClick={() => handleIntrospect(conn)}
                      disabled={introspectingId !== null}
                      style={primaryBtn}
                    >
                      {introspectingId === conn.connection_id
                        ? 'Introspecting…'
                        : 'Introspect →'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(conn)}
                      disabled={introspectingId !== null}
                      title="Delete connection"
                      style={dangerBtn}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {error && (
        <div style={{ marginTop: 16 }}>
          {/* Announced as well as shown, and in the brand's error colour rather
              than Tailwind's `#dc2626`. */}
          <StatusText tone="breaking">{error}</StatusText>
        </div>
      )}
    </main>
  );
}

const panelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  marginTop: 20,
  padding: 16,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 8,
  background: color.neutral[50],
};

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '12px 14px',
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 8,
  background: color.white,
};

const fieldStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  flex: 1,
  minWidth: 200,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: color.neutral[600],
};

const inputStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderRadius: 6,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: 14,
};

const primaryBtn: React.CSSProperties = {
  padding: '8px 14px',
  borderRadius: 6,
  border: `1px solid ${color.blue}`,
  background: color.blue,
  color: color.white,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  alignSelf: 'flex-start',
};

const dangerBtn: React.CSSProperties = {
  padding: '8px 12px',
  borderRadius: 6,
  border: `1px solid ${semantic.breaking.onLight}`,
  background: color.white,
  color: semantic.breaking.onLight,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
};
