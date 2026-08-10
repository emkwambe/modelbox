'use client';

/**
 * ModelBox Trainer (Pillar 3) — the teaching/learning workspace.
 * Assignment selector + React Flow canvas (Spot-the-Flaw) + Socratic tutor
 * drawer + live grading. Isolated route; reuses the canvas rendering engine.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';

import ERDCanvas from '@/components/canvas/ERDCanvas';
import {
  getAssignment,
  gradeSubmission,
  listAssignments,
  submitSocraticStep,
} from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import type {
  Assignment,
  GradeResult,
  SocraticMessage,
} from '@/types/trainer';

export default function TrainerPage() {
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const loadGraph = useCanvasStore((s) => s.loadGraph);
  const getGraphPayload = useCanvasStore((s) => s.getGraphPayload);

  const [mounted, setMounted] = useState(false);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [active, setActive] = useState<Assignment | null>(null);
  const [messages, setMessages] = useState<SocraticMessage[]>([]);
  const [reply, setReply] = useState('');
  const [tutorBusy, setTutorBusy] = useState(false);
  const [grade, setGrade] = useState<GradeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!token) return;
    listAssignments()
      .then(setAssignments)
      .catch(() => undefined);
  }, [token]);

  async function selectAssignment(id: string) {
    setError(null);
    setGrade(null);
    setMessages([]);
    if (!id) {
      setActive(null);
      return;
    }
    try {
      const assignment = await getAssignment(id);
      setActive(assignment);
      if (assignment.flawed_graph_json) {
        loadGraph(
          assignment.flawed_graph_json.entities,
          assignment.flawed_graph_json.relationships,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load assignment.');
    }
  }

  async function handleGrade() {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const result = await gradeSubmission({
        assignment_id: active.assignment_id,
        submitted_graph: getGraphPayload(),
      });
      setGrade(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Grading failed.');
    } finally {
      setBusy(false);
    }
  }

  async function askTutor(userMessage?: string) {
    if (!active) return;
    const history: SocraticMessage[] = userMessage
      ? [...messages, { role: 'user', content: userMessage }]
      : messages;
    setMessages(history);
    setReply('');
    setTutorBusy(true);
    try {
      const step = await submitSocraticStep({
        assignment_id: active.assignment_id,
        conversation_history: history,
        current_graph: getGraphPayload(),
      });
      const content =
        step.next_question +
        (step.hints.length
          ? '\n\nHints:\n' + step.hints.map((h) => `• ${h}`).join('\n')
          : '');
      setMessages([...history, { role: 'assistant', content }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tutor is unavailable.');
    } finally {
      setTutorBusy(false);
    }
  }

  const signedIn = mounted && Boolean(token);

  if (mounted && !signedIn) {
    return (
      <main style={{ maxWidth: 640, margin: '0 auto', padding: '64px 24px' }}>
        <h1 style={{ fontSize: 26, fontWeight: 700 }}>ModelBox Trainer</h1>
        <p style={{ color: '#475569', marginTop: 8 }}>
          Sign in to work through data-modeling challenges with the Socratic tutor.
        </p>
        <button
          type="button"
          onClick={openModal}
          style={{
            marginTop: 16,
            padding: '10px 18px',
            borderRadius: 8,
            border: 'none',
            background: '#2563eb',
            color: '#fff',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          🔒 Sign in
        </button>
      </main>
    );
  }

  const scoreColor = !grade
    ? '#64748b'
    : grade.score >= 80
      ? '#16a34a'
      : grade.score >= 50
        ? '#f59e0b'
        : '#dc2626';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          paddingRight: 320,
          borderBottom: '1px solid #e2e8f0',
          background: '#ffffff',
          flexWrap: 'wrap',
        }}
      >
        <Link
          href="/"
          style={{ fontWeight: 700, textDecoration: 'none', color: '#0f172a' }}
        >
          ModelBox Trainer
        </Link>
        <select
          value={active?.assignment_id ?? ''}
          onChange={(e) => void selectAssignment(e.target.value)}
          style={{
            padding: '6px 8px',
            borderRadius: 6,
            border: '1px solid #cbd5e1',
            fontSize: 13,
          }}
        >
          <option value="">Select an assignment…</option>
          {assignments.map((a) => (
            <option key={a.assignment_id} value={a.assignment_id}>
              {a.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleGrade}
          disabled={!active || busy}
          style={{
            padding: '6px 14px',
            borderRadius: 6,
            border: '1px solid #16a34a',
            background: '#16a34a',
            color: '#fff',
            fontSize: 13,
            fontWeight: 600,
            cursor: active && !busy ? 'pointer' : 'default',
            opacity: active && !busy ? 1 : 0.5,
          }}
        >
          {busy ? 'Grading…' : 'Grade Assignment'}
        </button>
        {grade && (
          <span style={{ fontSize: 14, fontWeight: 700, color: scoreColor }}>
            Score: {grade.score}
          </span>
        )}
      </header>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
          <ERDCanvas />
          {grade && grade.violations.length > 0 && (
            <div
              style={{
                position: 'absolute',
                left: 12,
                bottom: 12,
                width: 360,
                background: '#fff',
                border: '1px solid #fecaca',
                borderRadius: 8,
                boxShadow: '0 4px 12px #0000001a',
                padding: 10,
                zIndex: 20,
              }}
            >
              <strong style={{ color: '#dc2626', fontSize: 13 }}>
                {grade.violations.length} violation(s)
              </strong>
              <ul style={{ margin: '6px 0 0', paddingLeft: 0, listStyle: 'none' }}>
                {grade.violations.map((v) => {
                  const [code, ...rest] = v.split(':');
                  return (
                    <li key={v} style={{ fontSize: 12, marginTop: 4 }}>
                      <span
                        style={{
                          background: '#dc2626',
                          color: '#fff',
                          borderRadius: 4,
                          padding: '0 6px',
                          fontSize: 10,
                          fontWeight: 700,
                          marginRight: 6,
                        }}
                      >
                        {code}
                      </span>
                      <span style={{ color: '#334155' }}>{rest.join(':').trim()}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        {/* Socratic tutor drawer */}
        <div
          style={{
            width: 360,
            borderLeft: '1px solid #e2e8f0',
            display: 'flex',
            flexDirection: 'column',
            background: '#f8fafc',
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              borderBottom: '1px solid #e2e8f0',
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            🎓 Socratic Tutor
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
            {!active && (
              <p style={{ color: '#64748b', fontSize: 13 }}>
                Select an assignment to begin.
              </p>
            )}
            {active && messages.length === 0 && (
              <p style={{ color: '#64748b', fontSize: 13 }}>
                {active.description}
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  marginTop: 8,
                  padding: '8px 10px',
                  borderRadius: 8,
                  fontSize: 13,
                  whiteSpace: 'pre-wrap',
                  background: m.role === 'assistant' ? '#eff6ff' : '#ffffff',
                  border: '1px solid #e2e8f0',
                  color: '#0f172a',
                }}
              >
                <strong style={{ color: m.role === 'assistant' ? '#2563eb' : '#334155' }}>
                  {m.role === 'assistant' ? 'Tutor' : 'You'}
                </strong>
                <div style={{ marginTop: 4 }}>{m.content}</div>
              </div>
            ))}
            {tutorBusy && (
              <p style={{ color: '#64748b', fontSize: 13, marginTop: 8 }}>
                Thinking…
              </p>
            )}
          </div>
          <div style={{ borderTop: '1px solid #e2e8f0', padding: 10 }}>
            {messages.length === 0 ? (
              <button
                type="button"
                onClick={() => void askTutor()}
                disabled={!active || tutorBusy}
                style={{
                  width: '100%',
                  padding: 10,
                  borderRadius: 8,
                  border: 'none',
                  background: active && !tutorBusy ? '#2563eb' : '#94a3b8',
                  color: '#fff',
                  fontWeight: 600,
                  cursor: active && !tutorBusy ? 'pointer' : 'default',
                }}
              >
                Ask the tutor
              </button>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (reply.trim()) void askTutor(reply.trim());
                }}
                style={{ display: 'flex', gap: 6 }}
              >
                <input
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="Reply to the tutor…"
                  style={{
                    flex: 1,
                    padding: 8,
                    borderRadius: 6,
                    border: '1px solid #cbd5e1',
                    fontSize: 13,
                  }}
                />
                <button
                  type="submit"
                  disabled={tutorBusy || !reply.trim()}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: 'none',
                    background: '#2563eb',
                    color: '#fff',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Send
                </button>
              </form>
            )}
          </div>
        </div>
      </div>

      {error && (
        <p
          style={{
            color: '#dc2626',
            fontSize: 13,
            padding: '6px 16px',
            margin: 0,
          }}
          role="alert"
        >
          {error}
        </p>
      )}
    </div>
  );
}
