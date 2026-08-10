'use client';

/**
 * API Key management (/settings/api-keys).
 *
 * Generate programmatic keys for CI/CD pipelines and agents. The plaintext
 * secret is shown exactly once, at creation, then only its prefix remains.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

import { createApiKey, listApiKeys, revokeApiKey } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import type { ApiKeyInfo } from '@/types/schema';

export default function ApiKeysPage() {
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);

  const [mounted, setMounted] = useState(false);
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The one-time plaintext secret, shown only right after creation.
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => setMounted(true), []);
  const signedIn = mounted && Boolean(token);

  const refresh = useCallback(async () => {
    try {
      setKeys(await listApiKeys());
    } catch (e) {
      setError(errMessage(e));
    }
  }, []);

  useEffect(() => {
    if (signedIn) void refresh();
  }, [signedIn, refresh]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    setNewSecret(null);
    try {
      const created = await createApiKey({ name: name.trim() });
      setNewSecret(created.api_key);
      setName('');
      await refresh();
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(key: ApiKeyInfo) {
    if (!window.confirm(`Revoke API key "${key.name}"? This cannot be undone.`))
      return;
    setError(null);
    try {
      await revokeApiKey(key.api_key_id);
      await refresh();
    } catch (e) {
      setError(errMessage(e));
    }
  }

  function copySecret() {
    if (!newSecret) return;
    void navigator.clipboard?.writeText(newSecret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!mounted) return null;

  return (
    <main style={{ maxWidth: 820, margin: '0 auto', padding: '48px 24px' }}>
      <Link
        href="/"
        style={{ color: '#2563eb', fontWeight: 600, textDecoration: 'none' }}
      >
        ← ModelBox AI
      </Link>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>API Keys</h1>
      <p style={{ color: '#475569', marginTop: 4 }}>
        Programmatic access for CI/CD pipelines and agents. Send the key as an{' '}
        <code>X-API-Key</code> header. The secret is shown once — store it safely.
      </p>

      {!signedIn && (
        <div style={panelStyle}>
          <p style={{ margin: 0, color: '#475569' }}>Sign in to manage API keys.</p>
          <button type="button" onClick={openModal} style={primaryBtn}>
            Sign in
          </button>
        </div>
      )}

      {signedIn && (
        <>
          {newSecret && (
            <div style={secretPanel}>
              <div style={{ fontWeight: 700, color: '#0f172a' }}>
                Your new API key — copy it now
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                You won&apos;t be able to see this secret again.
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <code style={secretCode}>{newSecret}</code>
                <button type="button" onClick={copySecret} style={primaryBtn}>
                  {copied ? 'Copied ✓' : 'Copy'}
                </button>
              </div>
              <button
                type="button"
                onClick={() => setNewSecret(null)}
                style={{ ...ghostBtn, marginTop: 8, alignSelf: 'flex-start' }}
              >
                Dismiss
              </button>
            </div>
          )}

          <form onSubmit={handleCreate} style={panelStyle}>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
              Generate a new key
            </h2>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. CI pipeline"
                style={{ ...inputStyle, flex: 1, minWidth: 220 }}
              />
              <button type="submit" disabled={busy} style={primaryBtn}>
                {busy ? 'Generating…' : 'Generate key'}
              </button>
            </div>
          </form>

          <h2 style={{ fontSize: 16, fontWeight: 700, marginTop: 28 }}>
            Active keys
          </h2>
          {keys.length === 0 ? (
            <p style={{ color: '#94a3b8' }}>No API keys yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {keys.map((key) => (
                <div key={key.api_key_id} style={rowStyle}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600 }}>{key.name}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>
                      <code>{key.key_prefix}…</code> · created{' '}
                      {fmtDate(key.created_at)}
                      {key.last_used_at
                        ? ` · last used ${fmtDate(key.last_used_at)}`
                        : ' · never used'}
                      {key.expires_at ? ` · expires ${fmtDate(key.expires_at)}` : ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRevoke(key)}
                    style={dangerBtn}
                  >
                    Revoke
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

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
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

const secretPanel: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  marginTop: 20,
  padding: 16,
  border: '1px solid #fde68a',
  borderRadius: 8,
  background: '#fffbeb',
};

const secretCode: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  overflowX: 'auto',
  whiteSpace: 'nowrap',
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid #e2e8f0',
  background: '#ffffff',
  fontFamily: 'monospace',
  fontSize: 13,
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

const ghostBtn: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  background: '#ffffff',
  color: '#334155',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerBtn: React.CSSProperties = {
  padding: '8px 12px',
  borderRadius: 6,
  border: '1px solid #dc2626',
  background: '#ffffff',
  color: '#dc2626',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
};
