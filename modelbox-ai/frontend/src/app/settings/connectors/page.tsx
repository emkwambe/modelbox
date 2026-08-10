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
  introspectConnection,
  listConnections,
} from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import type { ConnectionEngine, ConnectionInfo } from '@/types/schema';

const ENGINES: { value: ConnectionEngine; label: string; enabled: boolean }[] = [
  { value: 'POSTGRESQL', label: 'PostgreSQL', enabled: true },
  { value: 'SNOWFLAKE', label: 'Snowflake', enabled: true },
  { value: 'BIGQUERY', label: 'BigQuery (coming soon)', enabled: false },
  { value: 'MYSQL', label: 'MySQL (coming soon)', enabled: false },
];

export default function ConnectorsPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const loadModel = useCanvasStore((s) => s.loadModel);

  const [mounted, setMounted] = useState(false);
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [name, setName] = useState('');
  const [engine, setEngine] = useState<ConnectionEngine>('POSTGRESQL');
  const [uri, setUri] = useState('');
  const [busy, setBusy] = useState(false);
  const [introspectingId, setIntrospectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);
  const signedIn = mounted && Boolean(token);

  const refresh = useCallback(async () => {
    try {
      setConnections(await listConnections());
    } catch (e) {
      setError(errMessage(e));
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
          style={{ color: '#2563eb', fontWeight: 600, textDecoration: 'none' }}
        >
          ← ModelBox AI
        </Link>
      </div>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>
        Database Connectors
      </h1>
      <p style={{ color: '#475569', marginTop: 4 }}>
        Register an encrypted connection, then reverse-engineer its schema
        directly onto the canvas. Connection URIs are stored AES-256-GCM
        encrypted and never shown in the clear.
      </p>

      {!signedIn && (
        <div style={panelStyle}>
          <p style={{ margin: 0, color: '#475569' }}>
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
          {connections.length === 0 ? (
            <p style={{ color: '#94a3b8' }}>No connections yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {connections.map((conn) => (
                <div key={conn.connection_id} style={rowStyle}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600 }}>{conn.name}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>
                      {conn.engine} · {conn.uri_masked ?? 'postgresql://***'}
                    </div>
                  </div>
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
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {error && (
        <p style={{ color: '#dc2626', marginTop: 16, fontSize: 13 }}>{error}</p>
      )}
    </main>
  );
}

function errMessage(e: unknown): string {
  if (
    typeof e === 'object' &&
    e !== null &&
    'response' in e &&
    typeof (e as { response?: unknown }).response === 'object'
  ) {
    const detail = (
      e as { response?: { data?: { detail?: unknown } } }
    ).response?.data?.detail;
    if (typeof detail === 'string') return detail;
  }
  return e instanceof Error ? e.message : 'Request failed.';
}

const panelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  marginTop: 20,
  padding: 16,
  border: '1px solid #e2e8f0',
  borderRadius: 8,
  background: '#f8fafc',
};

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '12px 14px',
  border: '1px solid #e2e8f0',
  borderRadius: 8,
  background: '#ffffff',
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
  alignSelf: 'flex-start',
};
