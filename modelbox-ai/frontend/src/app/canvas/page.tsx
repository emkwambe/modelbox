'use client';

/**
 * Canvas page — full-viewport ERD workspace with a collapsible export panel.
 */

import { useState } from 'react';
import Link from 'next/link';

import ERDCanvas from '@/components/canvas/ERDCanvas';
import ExportPanel from '@/components/editor/ExportPanel';
import { useCanvasStore } from '@/store/canvasStore';

export default function CanvasPage() {
  const paradigm = useCanvasStore((s) => s.paradigm);
  const entityCount = useCanvasStore((s) => s.nodes.length);
  const modelId = useCanvasStore((s) => s.modelId);
  const [showExport, setShowExport] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
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
        </div>
        <button
          type="button"
          onClick={() => setShowExport((v) => !v)}
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
      </header>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <ERDCanvas />
        </div>
        {showExport && (
          <div style={{ width: '45%', minWidth: 380, maxWidth: 720 }}>
            <ExportPanel onClose={() => setShowExport(false)} />
          </div>
        )}
      </div>
    </div>
  );
}
