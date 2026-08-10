'use client';

/**
 * Home / Prompt Studio — enter business requirements, synthesize a model, and
 * jump to the canvas.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { synthesizeModel } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import type { Paradigm } from '@/types/schema';

const PARADIGMS: Paradigm[] = ['3NF', 'KIMBALL', 'DATA_VAULT', 'OBT'];

export default function HomePage() {
  const router = useRouter();
  const loadModel = useCanvasStore((s) => s.loadModel);
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const [content, setContent] = useState('');
  const [paradigm, setParadigm] = useState<Paradigm>('KIMBALL');
  const [dialect, setDialect] = useState('snowflake');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Auth state is only known client-side (persisted). Gate auth-dependent UI
  // behind mount to avoid an SSR/CSR hydration mismatch.
  useEffect(() => setMounted(true), []);
  const signedIn = mounted && Boolean(token);

  async function handleSynthesize() {
    if (!token) {
      openModal();
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const model = await synthesizeModel({
        source_type: 'natural_language',
        content,
        target_paradigm: paradigm,
        dialect,
      });
      loadModel(model);
      router.push('/canvas');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Synthesis failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 820, margin: '0 auto', padding: '48px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>ModelBox AI</h1>
      <p style={{ color: '#475569', marginTop: 4 }}>
        Describe your business requirements and synthesize a data model.
      </p>

      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="e.g. Track customers, orders, subscriptions, and monthly recurring revenue (MRR)…"
        rows={8}
        style={{
          width: '100%',
          marginTop: 24,
          padding: 12,
          borderRadius: 8,
          border: '1px solid #cbd5e1',
          fontFamily: 'inherit',
          fontSize: 14,
        }}
      />

      <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: 12 }}>
          Paradigm
          <select
            value={paradigm}
            onChange={(e) => setParadigm(e.target.value as Paradigm)}
            style={{ padding: 8, borderRadius: 6, border: '1px solid #cbd5e1' }}
          >
            {PARADIGMS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', fontSize: 12 }}>
          Dialect
          <input
            value={dialect}
            onChange={(e) => setDialect(e.target.value)}
            style={{ padding: 8, borderRadius: 6, border: '1px solid #cbd5e1' }}
          />
        </label>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 20 }}>
        <button
          type="button"
          onClick={handleSynthesize}
          disabled={loading || content.trim().length === 0}
          style={{
            padding: '10px 20px',
            borderRadius: 8,
            border: 'none',
            background: loading ? '#94a3b8' : '#2563eb',
            color: '#ffffff',
            fontWeight: 600,
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading
            ? 'Synthesizing…'
            : signedIn
              ? 'Synthesize model'
              : 'Sign in to synthesize'}
        </button>
        {mounted && !signedIn && (
          <button
            type="button"
            onClick={openModal}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid #2563eb',
              background: '#ffffff',
              color: '#2563eb',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            🔒 Sign in
          </button>
        )}
      </div>

      {mounted && signedIn && (
        <p style={{ color: '#16a34a', marginTop: 8, fontSize: 13 }}>
          ✓ Signed in — ready to synthesize.
        </p>
      )}

      {loading && (
        <p style={{ color: '#64748b', marginTop: 8, fontSize: 13 }}>
          Contacting the model… this can take up to a minute or two.
        </p>
      )}

      {error && (
        <p style={{ color: '#dc2626', marginTop: 12 }} role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
