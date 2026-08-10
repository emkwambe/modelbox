'use client';

/**
 * Home / Prompt Studio — enter business requirements, synthesize a model, and
 * jump to the canvas.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import TemplateLibraryModal from '@/components/TemplateLibraryModal';
import { enqueueSynthesis, getJob, getModel } from '@/lib/api';
import type { Template } from '@/lib/templates';
import { useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import type { Paradigm, SynthesizeResponse } from '@/types/schema';

const PARADIGMS: Paradigm[] = ['3NF', 'KIMBALL', 'DATA_VAULT', 'OBT'];

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 150; // ~5 minutes

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function HomePage() {
  const router = useRouter();
  const loadModel = useCanvasStore((s) => s.loadModel);
  const loadGraph = useCanvasStore((s) => s.loadGraph);
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const [content, setContent] = useState('');
  const [paradigm, setParadigm] = useState<Paradigm>('KIMBALL');
  const [dialect, setDialect] = useState('snowflake');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);

  function handleUsePrompt(t: Template) {
    setContent(t.rawPrompt);
    setParadigm(t.paradigm);
    setShowLibrary(false);
  }

  function handleLoadGraph(t: Template) {
    loadGraph(t.entities, t.relationships, t.paradigm);
    setShowLibrary(false);
    router.push('/canvas');
  }

  // Auth state is only known client-side (persisted). Gate auth-dependent UI
  // behind mount to avoid an SSR/CSR hydration mismatch.
  useEffect(() => setMounted(true), []);
  const signedIn = mounted && Boolean(token);

  /** Poll a job to completion and return the finished model. */
  async function pollJob(jobId: string): Promise<SynthesizeResponse> {
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      const job = await getJob(jobId);
      if (job.status === 'COMPLETED' && job.result_model_id) {
        return getModel(job.result_model_id);
      }
      if (job.status === 'FAILED') {
        throw new Error(job.error ?? 'Synthesis failed.');
      }
      setProgress(job.status === 'PROCESSING' ? 'Synthesizing…' : 'Queued…');
      await sleep(POLL_INTERVAL_MS);
    }
    throw new Error('Timed out waiting for synthesis.');
  }

  async function handleSynthesize() {
    if (!token) {
      openModal();
      return;
    }
    setLoading(true);
    setError(null);
    setProgress('Queued…');
    try {
      const { job_id } = await enqueueSynthesis({
        source_type: 'natural_language',
        content,
        target_paradigm: paradigm,
        dialect,
        workspace_id: activeWorkspaceId,
      });
      const model = await pollJob(job_id);
      loadModel(model);
      router.push('/canvas');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Synthesis failed.');
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }

  return (
    <main style={{ maxWidth: 820, margin: '0 auto', padding: '48px 24px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>ModelBox AI</h1>
      <p style={{ color: '#475569', marginTop: 4 }}>
        Describe your business requirements and synthesize a data model.{' '}
        <Link href="/trainer" style={{ color: '#2563eb', fontWeight: 600 }}>
          Or open ModelBox Trainer →
        </Link>{' '}
        <Link
          href="/settings/connectors"
          style={{ color: '#2563eb', fontWeight: 600 }}
        >
          Connect a database →
        </Link>{' '}
        <Link
          href="/settings/api-keys"
          style={{ color: '#2563eb', fontWeight: 600 }}
        >
          API keys →
        </Link>
      </p>

      <button
        type="button"
        onClick={() => setShowLibrary(true)}
        style={{
          marginTop: 12,
          padding: '8px 14px',
          borderRadius: 8,
          border: '1px solid #7c3aed',
          background: '#f5f3ff',
          color: '#7c3aed',
          fontSize: 13,
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        📚 Explore Requirements Library
      </button>

      {showLibrary && (
        <TemplateLibraryModal
          onClose={() => setShowLibrary(false)}
          onUsePrompt={handleUsePrompt}
          onLoadGraph={handleLoadGraph}
        />
      )}

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
            ? (progress ?? 'Synthesizing…')
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
          {progress ?? 'Working…'} — runs as a background job, so it won't time
          out (up to a couple of minutes).
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
