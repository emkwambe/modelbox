'use client';

/**
 * ControlPanel — overlay canvas controls for layout + undo/redo history.
 */

import { Panel } from '@xyflow/react';

import { useCanvasStore } from '@/store/canvasStore';
import { color } from '@/styles/tokens';

const buttonStyle: React.CSSProperties = {
  padding: '4px 10px',
  fontSize: 12,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 6,
  background: color.white,
  cursor: 'pointer',
};

export default function ControlPanel() {
  const applyLayout = useCanvasStore((s) => s.applyLayout);
  const undo = useCanvasStore((s) => s.undo);
  const redo = useCanvasStore((s) => s.redo);
  const canUndo = useCanvasStore((s) => s.past.length > 0);
  const canRedo = useCanvasStore((s) => s.future.length > 0);

  return (
    <Panel position="top-right" style={{ display: 'flex', gap: 6 }}>
      <button type="button" style={buttonStyle} onClick={() => applyLayout('TB')}>
        Auto-layout ↓
      </button>
      <button type="button" style={buttonStyle} onClick={() => applyLayout('LR')}>
        Auto-layout →
      </button>
      <button
        type="button"
        style={{ ...buttonStyle, opacity: canUndo ? 1 : 0.4 }}
        disabled={!canUndo}
        onClick={undo}
      >
        Undo
      </button>
      <button
        type="button"
        style={{ ...buttonStyle, opacity: canRedo ? 1 : 0.4 }}
        disabled={!canRedo}
        onClick={redo}
      >
        Redo
      </button>
    </Panel>
  );
}
