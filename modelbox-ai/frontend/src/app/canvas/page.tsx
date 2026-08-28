'use client';

/**
 * Canvas page — full-viewport ERD workspace with export panel + model actions.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { AUTH_BADGE_RESERVE } from '@/components/auth/AuthBadge';
import ERDCanvas from '@/components/canvas/ERDCanvas';
import ColumnSemanticEditor from '@/components/canvas/ColumnSemanticEditor';
import EntitySettingsEditor from '@/components/canvas/EntitySettingsEditor';
import DiffPanel from '@/components/migration/DiffPanel';
import ExportPanel from '@/components/editor/ExportPanel';
import { deleteModel, saveGraph, updateModel } from '@/lib/api';
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

  // A graph on the canvas with no model behind it: the library's "Load canvas"
  // path. Every header action is gated on `modelId`, so without saying so the
  // page reads as five broken buttons.
  const isReferenceModel = entityCount > 0 && !modelId;

  const issueCount = validation?.issues.length ?? 0;
  const validStatus = validation
    ? validation.is_valid
      ? { label: '✓ Valid', color: '#16a34a' }
      : {
          label: `⚠ ${issueCount} issue${issueCount === 1 ? '' : 's'}`,
          color: '#dc2626',
        }
    : null;

  async function handleSave() {
    if (!modelId) return;
    setBusy(true);
    setSaved(false);
    try {
      const report = await saveGraph(modelId, getGraphPayload());
      setValidation(report);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setBusy(false);
    }
  }

  async function handleRename() {
    if (!modelId) return;
    const title = window.prompt('New model title:');
    if (!title) return;
    setBusy(true);
    try {
      await updateModel(modelId, { title });
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!modelId) return;
    if (!window.confirm('Delete this model? This cannot be undone.')) return;
    setBusy(true);
    try {
      await deleteModel(modelId);
      reset();
      router.push('/');
    } catch {
      setBusy(false);
    }
  }

  const actionBtn = (color: string): React.CSSProperties => ({
    padding: '6px 12px',
    borderRadius: 6,
    border: `1px solid ${color}`,
    background: '#ffffff',
    color,
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
          borderBottom: '1px solid #e2e8f0',
          background: '#ffffff',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <Link
            href="/"
            style={{ fontWeight: 700, textDecoration: 'none', color: '#0f172a' }}
          >
            ModelBox AI
          </Link>
          <span style={{ color: '#64748b', fontSize: 13 }}>
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
          {saved && (
            <span style={{ color: '#16a34a', fontSize: 12, fontWeight: 600 }}>
              ✓ Saved
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!modelId || busy}
            style={actionBtn('#16a34a')}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={handleRename}
            disabled={!modelId || busy}
            style={actionBtn('#334155')}
          >
            Rename
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={!modelId || busy}
            style={actionBtn('#dc2626')}
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
              background: showDiff ? '#7c3aed' : '#ffffff',
              color: showDiff ? '#ffffff' : '#7c3aed',
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
              border: '1px solid #2563eb',
              background: showExport ? '#2563eb' : '#ffffff',
              color: showExport ? '#ffffff' : '#2563eb',
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
            background: '#fffbeb',
            borderBottom: '1px solid #fde68a',
            color: '#92400e',
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
                border: '1px solid #b45309',
                color: '#92400e',
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
