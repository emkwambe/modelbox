'use client';

/**
 * ModelBox Trainer (Pillar 3) — the teaching/learning workspace.
 * Assignment selector + React Flow canvas (Spot-the-Flaw) + Socratic tutor
 * drawer + live grading. Isolated route; reuses the canvas rendering engine.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';

import { AUTH_BADGE_RESERVE } from '@/components/auth/AuthBadge';
import ERDCanvas from '@/components/canvas/ERDCanvas';
import ColumnSemanticEditor from '@/components/canvas/ColumnSemanticEditor';
import EntitySettingsEditor from '@/components/canvas/EntitySettingsEditor';
import TemplateLibraryModal from '@/components/TemplateLibraryModal';
import LabModal from '@/components/trainer/LabModal';
import { labToGraph, type Lab } from '@/content/trainer';
import {
  getAssignment,
  gradeSubmission,
  listAssignments,
  submitSocraticStep,
  validateGraph,
} from '@/lib/api';
import type { Template } from '@/lib/templates';
import { useAuthStatus, useAuthStore } from '@/store/authStore';
import { useCanvasStore } from '@/store/canvasStore';
import { toneColor, toneTint } from '@/components/ui';
import { color, semantic } from '@/styles/tokens';
import type {
  Assignment,
  GradeResult,
  SocraticMessage,
} from '@/types/trainer';

interface LabGrade {
  cleared: string[];
  remaining: string[];
  solved: boolean;
}

export default function TrainerPage() {
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const loadGraph = useCanvasStore((s) => s.loadGraph);
  const getGraphPayload = useCanvasStore((s) => s.getGraphPayload);
  const applyLayout = useCanvasStore((s) => s.applyLayout);

  const authStatus = useAuthStatus();
  const [showLabModal, setShowLabModal] = useState(false);
  const [activeLab, setActiveLab] = useState<Lab | null>(null);
  const [labGrade, setLabGrade] = useState<LabGrade | null>(null);
  const [labBusy, setLabBusy] = useState(false);

  function handleSelectLab(lab: Lab) {
    const { entities, relationships } = labToGraph(lab);
    loadGraph(entities, relationships, null);
    applyLayout('TB');
    setActiveLab(lab);
    setLabGrade(null);
    setShowLabModal(false);
  }

  async function handleSubmitLab() {
    if (!activeLab) return;
    setLabBusy(true);
    setError(null);
    try {
      const report = await validateGraph(getGraphPayload());
      const produced = new Set(report.issues.map((i) => i.code));
      const expected = activeLab.expected_flaws.map((f) => f.code);
      const remaining = expected.filter((c) => produced.has(c));
      const cleared = expected.filter((c) => !produced.has(c));
      setLabGrade({ cleared, remaining, solved: remaining.length === 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Grading failed.');
    } finally {
      setLabBusy(false);
    }
  }
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [active, setActive] = useState<Assignment | null>(null);
  const [messages, setMessages] = useState<SocraticMessage[]>([]);
  const [reply, setReply] = useState('');
  const [tutorBusy, setTutorBusy] = useState(false);
  const [grade, setGrade] = useState<GradeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLibrary, setShowLibrary] = useState(false);

  function handleLoadTemplate(t: Template) {
    loadGraph(t.entities, t.relationships, t.paradigm);
    setShowLibrary(false);
  }


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

  const signedIn = authStatus === 'signed-in';

  // Not `mounted && !signedIn`: while `mounted` was false the signed-out
  // branch was skipped and the trainer rendered to a visitor who was not
  // signed in.
  if (!signedIn) {
    return (
      <main style={{ maxWidth: 640, margin: '0 auto', padding: '64px 24px' }}>
        <h1 style={{ fontSize: 26, fontWeight: 700 }}>ModelBox Trainer</h1>
        <p style={{ color: color.neutral[600], marginTop: 8 }}>
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
            background: color.blue,
            color: color.white,
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
    ? color.neutral[500]
    : grade.score >= 80
      ? semantic.validated.onLight
      : grade.score >= 50
        ? semantic.preview.onDark
        : semantic.breaking.onLight;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          // The badge declares how much space it needs; do not restate it.
          paddingRight: AUTH_BADGE_RESERVE,
          borderBottom: `1px solid ${color.neutral[200]}`,
          background: color.white,
          flexWrap: 'wrap',
        }}
      >
        <Link
          href="/"
          style={{ fontWeight: 700, textDecoration: 'none', color: color.neutral[900] }}
        >
          ModelBox Trainer
        </Link>
        <select
          value={active?.assignment_id ?? ''}
          onChange={(e) => void selectAssignment(e.target.value)}
          style={{
            padding: '6px 8px',
            borderRadius: 6,
            border: `1px solid ${color.neutral[300]}`,
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
          onClick={() => setShowLibrary(true)}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            border: '1px solid #7c3aed',
            background: '#f5f3ff',
            color: '#7c3aed',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          📚 Library
        </button>
        <button
          type="button"
          onClick={() => setShowLabModal(true)}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            border: `1px solid ${color.blue}`,
            background: toneTint('accent', 'light'),
            color: color.blue,
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          🧪 Select Lab
        </button>
        {activeLab && (
          <button
            type="button"
            onClick={handleSubmitLab}
            disabled={labBusy}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: `1px solid ${color.blue}`,
              background: color.blue,
              color: color.white,
              fontSize: 13,
              fontWeight: 600,
              cursor: labBusy ? 'default' : 'pointer',
            }}
          >
            {labBusy ? 'Grading…' : 'Submit Lab'}
          </button>
        )}
        <button
          type="button"
          onClick={handleGrade}
          disabled={!active || busy}
          style={{
            padding: '6px 14px',
            borderRadius: 6,
            border: `1px solid ${semantic.validated.onLight}`,
            background: semantic.validated.onLight,
            color: color.white,
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
          <ColumnSemanticEditor />
          <EntitySettingsEditor />
          {activeLab && (
            <div
              style={{
                position: 'absolute',
                left: 12,
                top: 12,
                width: 340,
                maxHeight: 'calc(100% - 24px)',
                overflowY: 'auto',
                background: color.white,
                border: `1px solid ${color.neutral[200]}`,
                borderRadius: 8,
                boxShadow: `0 8px 24px ${color.neutral[900]}1F`,
                padding: 12,
                zIndex: 25,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <strong style={{ fontSize: 13 }}>🧪 {activeLab.title}</strong>
                <button
                  type="button"
                  onClick={() => {
                    setActiveLab(null);
                    setLabGrade(null);
                  }}
                  style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: color.neutral[500] }}
                  aria-label="Exit lab"
                >
                  ✕
                </button>
              </div>
              <p style={{ fontSize: 12, color: color.neutral[600], margin: '6px 0', lineHeight: 1.5 }}>
                {activeLab.brief}
              </p>

              {!labGrade && (
                <div style={{ fontSize: 12, color: color.neutral[500] }}>
                  Fix the seeded flaws, then <strong>Submit Lab</strong> to grade.
                </div>
              )}

              {labGrade && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 13,
                      color: labGrade.solved ? semantic.validated.onLight : semantic.preview.onLight,
                    }}
                  >
                    {labGrade.solved
                      ? '✓ Solved — all flaws cleared!'
                      : `${labGrade.cleared.length}/${activeLab.expected_flaws.length} flaws cleared`}
                  </div>
                  {activeLab.expected_flaws.map((f) => {
                    const done = !labGrade.remaining.includes(f.code);
                    return (
                      <div
                        key={f.code + f.target}
                        style={{
                          fontSize: 12,
                          padding: '6px 8px',
                          borderRadius: 6,
                          background: toneTint(done ? 'validated' : 'preview', 'light'),
                          border: `1px solid ${toneColor(done ? 'validated' : 'preview', 'light')}`,
                          color: toneColor(done ? 'validated' : 'preview', 'light'),
                        }}
                      >
                        {done ? '✓' : '○'} <code>{f.code}</code> · {f.target}
                        {!done && (
                          <div style={{ marginTop: 2, color: color.neutral[500] }}>{f.hint}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {grade && grade.violations.length > 0 && (
            <div
              style={{
                position: 'absolute',
                left: 12,
                bottom: 12,
                width: 360,
                background: color.white,
                border: `1px solid ${toneColor('breaking', 'light')}`,
                borderRadius: 8,
                boxShadow: `0 4px 12px ${color.neutral[900]}1A`,
                padding: 10,
                zIndex: 20,
              }}
            >
              <strong style={{ color: semantic.breaking.onLight, fontSize: 13 }}>
                {grade.violations.length} violation(s)
              </strong>
              <ul style={{ margin: '6px 0 0', paddingLeft: 0, listStyle: 'none' }}>
                {grade.violations.map((v) => {
                  const [code, ...rest] = v.split(':');
                  return (
                    <li key={v} style={{ fontSize: 12, marginTop: 4 }}>
                      <span
                        style={{
                          background: semantic.breaking.onLight,
                          color: color.white,
                          borderRadius: 4,
                          padding: '0 6px',
                          fontSize: 10,
                          fontWeight: 700,
                          marginRight: 6,
                        }}
                      >
                        {code}
                      </span>
                      <span style={{ color: color.neutral[700] }}>{rest.join(':').trim()}</span>
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
            borderLeft: `1px solid ${color.neutral[200]}`,
            display: 'flex',
            flexDirection: 'column',
            background: color.neutral[50],
          }}
        >
          <div
            style={{
              padding: '10px 12px',
              borderBottom: `1px solid ${color.neutral[200]}`,
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            🎓 Socratic Tutor
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
            {!active && (
              <p style={{ color: color.neutral[500], fontSize: 13 }}>
                Select an assignment to begin.
              </p>
            )}
            {active && messages.length === 0 && (
              <p style={{ color: color.neutral[500], fontSize: 13 }}>
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
                  background:
                    m.role === 'assistant' ? toneTint('accent', 'light') : color.white,
                  border: `1px solid ${color.neutral[200]}`,
                  color: color.neutral[900],
                }}
              >
                <strong style={{ color: m.role === 'assistant' ? color.blue : color.neutral[700] }}>
                  {m.role === 'assistant' ? 'Tutor' : 'You'}
                </strong>
                <div style={{ marginTop: 4 }}>{m.content}</div>
              </div>
            ))}
            {tutorBusy && (
              <p style={{ color: color.neutral[500], fontSize: 13, marginTop: 8 }}>
                Thinking…
              </p>
            )}
          </div>
          <div style={{ borderTop: `1px solid ${color.neutral[200]}`, padding: 10 }}>
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
                  background: active && !tutorBusy ? color.blue : color.neutral[400],
                  color: color.white,
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
                    border: `1px solid ${color.neutral[300]}`,
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
                    background: color.blue,
                    color: color.white,
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
            color: semantic.breaking.onLight,
            fontSize: 13,
            padding: '6px 16px',
            margin: 0,
          }}
          role="alert"
        >
          {error}
        </p>
      )}

      {showLibrary && (
        <TemplateLibraryModal
          onClose={() => setShowLibrary(false)}
          onLoadGraph={handleLoadTemplate}
        />
      )}

      {showLabModal && (
        <LabModal
          onClose={() => setShowLabModal(false)}
          onSelect={handleSelectLab}
        />
      )}
    </div>
  );
}
