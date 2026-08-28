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

const CAPABILITIES: { icon: string; title: string; desc: string }[] = [
  {
    icon: '🧠',
    title: 'AI Synthesis',
    desc: 'Natural language, PRDs, or DDL → validated models across 3NF, Kimball, Data Vault & OBT.',
  },
  {
    icon: '🔌',
    title: 'Brownfield Introspection',
    desc: 'Reverse-engineer live PostgreSQL, Snowflake, BigQuery & MySQL schemas onto the canvas.',
  },
  {
    icon: '🔀',
    title: 'Schema Diff & Migration',
    desc: 'Compare model versions into dialect-specific ALTER DDL with breaking-change warnings.',
  },
  {
    icon: '🛡️',
    title: 'Governance Linter',
    desc: 'Naming, grain, PII-exposure & documentation checks surfaced right on the graph.',
  },
  {
    icon: '📜',
    title: 'Data Contracts',
    desc: 'OpenDataContract YAML, Apache Avro & Protobuf — contract-driven development, ready.',
  },
  {
    icon: '📊',
    title: 'Semantic Layers',
    desc: 'dbt projects (with tests), Cube.js, LookML & dbt MetricFlow exports.',
  },
  {
    icon: '📚',
    title: 'Data Dictionary',
    desc: 'Publication-ready Markdown & HTML docs plus machine-readable JSON for AI agents.',
  },
  {
    icon: '🌱',
    title: 'Synthetic Seed',
    desc: 'Referentially-intact SQL & CSV fixtures for QA and development environments.',
  },
  {
    icon: '🔑',
    title: 'Programmatic API',
    desc: 'X-API-Key access for CI/CD pipelines and agents, with revocable workspace keys.',
  },
];

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 150; // ~5 minutes

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function HomePage() {
  const router = useRouter();
  const loadModel = useCanvasStore((s) => s.loadModel);
  const loadGraph = useCanvasStore((s) => s.loadGraph);
  const sourcePrompt = useCanvasStore((s) => s.sourcePrompt);
  const sourceParadigm = useCanvasStore((s) => s.paradigm);
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
    // Carry the prompt with the graph: the canvas offers "Synthesize this
    // model", and that is the prompt it sends the reader back here with.
    loadGraph(t.entities, t.relationships, t.paradigm, t.rawPrompt);
    setShowLibrary(false);
    router.push('/canvas');
  }

  // Auth state is only known client-side (persisted). Gate auth-dependent UI
  // behind mount to avoid an SSR/CSR hydration mismatch.
  useEffect(() => setMounted(true), []);

  // Coming back from the canvas's "Synthesize this model": start from the
  // template's own prompt. Never overwrite something already typed.
  useEffect(() => {
    if (!sourcePrompt) return;
    setContent((current) => (current.trim() ? current : sourcePrompt));
    if (sourceParadigm) setParadigm(sourceParadigm);
  }, [sourcePrompt, sourceParadigm]);

  const signedIn = mounted && Boolean(token);

  /** Poll a job to completion and return the finished model. */
  async function pollJob(jobId: string): Promise<SynthesizeResponse> {
    let lastStatus = 'PENDING';
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      const job = await getJob(jobId);
      if (job.status === 'COMPLETED' && job.result_model_id) {
        return getModel(job.result_model_id);
      }
      if (job.status === 'FAILED') {
        throw new Error(job.error ?? 'Synthesis failed.');
      }
      lastStatus = job.status;
      setProgress(job.status === 'PROCESSING' ? 'Synthesizing…' : 'Queued…');
      await sleep(POLL_INTERVAL_MS);
    }
    // A job still QUEUED at the deadline never started, which is a different
    // fault from one that started and ran long — and the status says which.
    // Reporting both as a timeout described the client's own budget rather
    // than what happened to the work, and sent people looking for a slow model
    // when nothing was consuming the queue at all.
    const minutes = Math.round((POLL_MAX_ATTEMPTS * POLL_INTERVAL_MS) / 60000);
    throw new Error(
      lastStatus === 'PENDING'
        ? `Synthesis never started — the job was still queued after ${minutes} minutes. ` +
          'Nothing is consuming the queue: check that the modelbox-worker container is running.'
        : `Synthesis is still running after ${minutes} minutes. The job has not failed; ` +
          'it may finish on its own, or the provider may be unresponsive — check the worker logs.',
    );
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
    <main style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px 64px' }}>
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
          paddingRight: 220, // clear the fixed AuthBadge overlay
        }}
      >
        <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: -0.3 }}>
          ◆ ModelBox<span style={{ color: '#2563eb' }}>AI</span>
        </span>
        <div style={{ display: 'flex', gap: 18, fontSize: 14, flexWrap: 'wrap' }}>
          <Link href="/canvas" style={navLink}>
            Canvas
          </Link>
          <Link href="/trainer" style={navLink}>
            Trainer
          </Link>
          <Link href="/settings/connectors" style={navLink}>
            Connectors
          </Link>
          <Link href="/settings/api-keys" style={navLink}>
            API keys
          </Link>
          <Link href="/docs" style={navLink}>
            Docs
          </Link>
        </div>
      </nav>

      <h1
        style={{
          fontSize: 36,
          fontWeight: 800,
          letterSpacing: -0.6,
          lineHeight: 1.12,
          marginTop: 40,
        }}
      >
        The end-to-end data modeling
        <br />
        &amp; governance mesh
      </h1>
      <p style={{ color: '#475569', marginTop: 12, fontSize: 16, maxWidth: 640 }}>
        Synthesize validated models from plain language, reverse-engineer live
        warehouses, diff &amp; migrate schemas, and ship dbt, data contracts, and
        semantic layers — with governance built in.
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
          {progress ?? 'Working…'} — runs as a background job, so it won&apos;t
          time out (up to a couple of minutes).
        </p>
      )}

      {error && (
        <p style={{ color: '#dc2626', marginTop: 12 }} role="alert">
          {error}
        </p>
      )}

      <section style={{ marginTop: 64 }}>
        <h2
          style={{
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: 0.8,
            textTransform: 'uppercase',
            color: '#64748b',
          }}
        >
          One platform · the full modeling lifecycle
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
            gap: 12,
            marginTop: 16,
          }}
        >
          {CAPABILITIES.map((cap) => (
            <div
              key={cap.title}
              style={{
                border: '1px solid #e2e8f0',
                borderRadius: 10,
                padding: 16,
                background: '#ffffff',
              }}
            >
              <div style={{ fontSize: 22 }}>{cap.icon}</div>
              <div style={{ fontWeight: 700, fontSize: 14, marginTop: 8 }}>
                {cap.title}
              </div>
              <div style={{ fontSize: 13, color: '#64748b', marginTop: 4, lineHeight: 1.5 }}>
                {cap.desc}
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

const navLink: React.CSSProperties = {
  color: '#334155',
  fontWeight: 600,
  textDecoration: 'none',
};
