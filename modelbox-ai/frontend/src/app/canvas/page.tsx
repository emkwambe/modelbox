'use client';

/**
 * Canvas page — full-viewport ERD workspace with export panel + model actions.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { AUTH_BADGE_RESERVE } from '@/components/auth/AuthBadge';
import { color, semantic } from '@/styles/tokens';
import ERDCanvas from '@/components/canvas/ERDCanvas';
import ColumnSemanticEditor from '@/components/canvas/ColumnSemanticEditor';
import EntitySettingsEditor from '@/components/canvas/EntitySettingsEditor';
import DiffPanel from '@/components/migration/DiffPanel';
import ExportPanel from '@/components/editor/ExportPanel';
import { deleteModel, saveGraph, updateModel } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { StatusText, toneColor, toneTint } from '@/components/ui';
import { useCanvasStore } from '@/store/canvasStore';

export default function CanvasPage() {
  const router = useRouter();
  const paradigm = useCanvasStore((s) => s.paradigm);
  const entityCount = useCanvasStore((s) => s.nodes.length);
  const modelId = useCanvasStore((s) => s.modelId);
  const sourcePrompt = useCanvasStore((s) => s.sourcePrompt);
  const validation = useCanvasStore((s) => s.validation);
  const reset = useCanvasStore((s) => s.reset);
  const setValidation = useCanvasStore((s) => s.setValidation);
  const getGraphPayload = useCanvasStore((s) => s.getGraphPayload);
  const [showExport, setShowExport] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // A graph on the canvas with no model behind it: the library's "Load canvas"
  // path. Every header action is gated on `modelId`, so without saying so the
  // page reads as five broken buttons.
  const isReferenceModel = entityCount > 0 && !modelId;

  const issueCount = validation?.issues.length ?? 0;
  // The header is a white bar, so the on-light variants apply. `#16a34a` — the
  // value this used before — measures 3.30:1 on white and failed the contrast
  // floor while looking, to a sighted reviewer on a good monitor, entirely fine.
  const validStatus = validation
    ? validation.is_valid
      ? { label: '✓ Valid', color: semantic.validated.onLight }
      : {
          label: `⚠ ${issueCount} issue${issueCount === 1 ? '' : 's'}`,
          color: semantic.breaking.onLight,
        }
    : null;

  /*
   * All three of these were `try`/`finally` with no `catch`, so a failed save
   * threw into an unhandled rejection: the spinner stopped, nothing appeared,
   * and the user was left looking at a canvas they believed was saved. Delete
   * was worse in a quieter way — it caught the error only to call
   * `setBusy(false)`, which is a failure deliberately discarded.
   *
   * The remedy is the same in each: say so. `errMessage` prefers the server's
   * `detail`, which for a save is usually the validation reason.
   */
  async function handleSave() {
    if (!modelId) return;
    setBusy(true);
    setSaved(false);
    setActionError(null);
    try {
      const report = await saveGraph(modelId, getGraphPayload());
      setValidation(report);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setActionError(errMessage(e, 'The model could not be saved.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleRename() {
    if (!modelId) return;
    const title = window.prompt('New model title:');
    if (!title) return;
    setBusy(true);
    setActionError(null);
    try {
      await updateModel(modelId, { title });
    } catch (e) {
      setActionError(errMessage(e, 'The model could not be renamed.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!modelId) return;
    if (!window.confirm('Delete this model? This cannot be undone.')) return;
    setBusy(true);
    setActionError(null);
    try {
      await deleteModel(modelId);
      reset();
      router.push('/');
    } catch (e) {
      setActionError(errMessage(e, 'The model could not be deleted.'));
    } finally {
      setBusy(false);
    }
  }

  // The parameter was named `color`, which shadowed the token module the
  // moment this file started importing it — `color.white` silently resolved to
  // a property of the string parameter. `tsc` caught it; nothing else would
  // have, because the shadowed name is still a valid expression.
  const actionBtn = (accent: string): React.CSSProperties => ({
    padding: '6px 12px',
    borderRadius: 6,
    border: `1px solid ${accent}`,
    background: color.white,
    color: accent,
    fontSize: 13,
    fontWeight: 600,
    cursor: modelId && !busy ? 'pointer' : 'default',
    opacity: modelId && !busy ? 1 : 0.5,
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          // Reserve space on the right for the fixed AuthBadge overlay. The
          // badge declares how much it needs; do not restate the number here.
          paddingRight: AUTH_BADGE_RESERVE,
          borderBottom: `1px solid ${color.neutral[200]}`,
          background: color.white,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <Link
            href="/"
            style={{ fontWeight: 700, textDecoration: 'none', color: color.neutral[900] }}
          >
            ModelBox AI
          </Link>
          <span style={{ color: color.neutral[500], fontSize: 13 }}>
            {paradigm ?? 'No model'} · {entityCount} entities
          </span>
          {validStatus && (
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: validStatus.color,
                border: `1px solid ${validStatus.color}33`,
                borderRadius: 12,
                padding: '2px 8px',
              }}
            >
              {validStatus.label}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/*
            Announced, not just shown. `StatusText` derives `role="alert"` from
            the tone, so a save that fails while the user is looking elsewhere
            on the canvas still reaches them.
          */}
          {actionError && <StatusText tone="breaking">{actionError}</StatusText>}
          {saved && (
            <span
              style={{
                color: semantic.validated.onLight,
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              ✓ Saved
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!modelId || busy}
            style={actionBtn(semantic.validated.onLight)}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={handleRename}
            disabled={!modelId || busy}
            style={actionBtn(color.neutral[700])}
          >
            Rename
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={!modelId || busy}
            style={actionBtn(semantic.breaking.onLight)}
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => {
              setShowDiff((v) => !v);
              setShowExport(false);
            }}
            disabled={!modelId}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: '1px solid #7c3aed',
              background: showDiff ? '#7c3aed' : color.white,
              color: showDiff ? color.white : '#7c3aed',
              fontSize: 13,
              fontWeight: 600,
              cursor: modelId ? 'pointer' : 'default',
              opacity: modelId ? 1 : 0.5,
            }}
          >
            {showDiff ? 'Hide diff' : 'Diff & migrate'}
          </button>
          <button
            type="button"
            onClick={() => {
              setShowExport((v) => !v);
              setShowDiff(false);
            }}
            disabled={!modelId}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: `1px solid ${color.blue}`,
              background: showExport ? color.blue : color.white,
              color: showExport ? color.white : color.blue,
              fontSize: 13,
              fontWeight: 600,
              cursor: modelId ? 'pointer' : 'default',
              opacity: modelId ? 1 : 0.5,
            }}
          >
            {showExport ? 'Hide export' : 'Export artifacts'}
          </button>
        </div>
      </header>

      {isReferenceModel && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            padding: '8px 16px',
            background: toneTint('preview', 'light'),
            borderBottom: `1px solid ${toneColor('preview', 'light')}`,
            color: toneColor('preview', 'light'),
            fontSize: 13,
          }}
        >
          <strong style={{ fontWeight: 700 }}>Reference model</strong>
          <span>
            Loaded from the library, so it does not exist in your workspace
            yet. Saving, diffing and exporting act on stored models.
          </span>
          {sourcePrompt && (
            <Link
              href="/"
              style={{
                marginLeft: 'auto',
                padding: '4px 12px',
                borderRadius: 6,
                border: `1px solid ${semantic.preview.onLight}`,
                color: toneColor('preview', 'light'),
                fontWeight: 600,
                textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              Synthesize this model →
            </Link>
          )}
        </div>
      )}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
          <ERDCanvas />
          <ColumnSemanticEditor />
          <EntitySettingsEditor />
        </div>
        {showDiff && (
          <div style={{ width: '45%', minWidth: 380, maxWidth: 720 }}>
            <DiffPanel onClose={() => setShowDiff(false)} />
          </div>
        )}
        {showExport && (
          <div style={{ width: '45%', minWidth: 380, maxWidth: 720 }}>
            <ExportPanel onClose={() => setShowExport(false)} />
          </div>
        )}
      </div>
    </div>
  );
}
