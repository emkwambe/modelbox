'use client';

/**
 * Canvas page — full-viewport ERD workspace.
 */

import Link from 'next/link';

import ERDCanvas from '@/components/canvas/ERDCanvas';
import { useCanvasStore } from '@/store/canvasStore';

export default function CanvasPage() {
  const paradigm = useCanvasStore((s) => s.paradigm);
  const entityCount = useCanvasStore((s) => s.nodes.length);

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
          <Link href="/" style={{ fontWeight: 700, textDecoration: 'none', color: '#0f172a' }}>
            ModelBox AI
          </Link>
          <span style={{ color: '#64748b', fontSize: 13 }}>
            {paradigm ?? 'No model'} · {entityCount} entities
          </span>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ERDCanvas />
      </div>
    </div>
  );
}
