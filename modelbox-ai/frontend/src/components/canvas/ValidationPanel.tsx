'use client';

/**
 * ValidationPanel — bottom-left overlay listing graph lint issues (FR-2.3).
 *
 * Shows the current ValidationReport, a "Re-validate" trigger, and lets the
 * user click an issue to select + centre the offending entity node.
 */

import { Panel, useReactFlow } from '@xyflow/react';

import { useCanvasStore } from '@/store/canvasStore';
import { semantic } from '@/styles/tokens';

// The panel sits on a white card, so both take the on-light variants. The
// brand's Amber measures 2.15:1 on white — as a warning colour it would be
// decoration rather than a signal.
const SEVERITY_COLOR: Record<string, string> = {
  error: semantic.breaking.onLight,
  warning: semantic.preview.onLight,
};

export default function ValidationPanel() {
  const validation = useCanvasStore((s) => s.validation);
  const validating = useCanvasStore((s) => s.validating);
  const validateModel = useCanvasStore((s) => s.validateModel);
  const modelId = useCanvasStore((s) => s.modelId);
  const nodes = useCanvasStore((s) => s.nodes);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const reactFlow = useReactFlow();

  if (!validation) return null;

  const { is_valid: isValid, issues } = validation;

  function focusEntity(entityName: string) {
    selectNode(entityName);
    const node = nodes.find((n) => n.id === entityName);
    if (node) {
      reactFlow.setCenter(node.position.x + 120, node.position.y + 90, {
        zoom: 1.2,
        duration: 400,
      });
    }
  }

  return (
    <Panel
      position="bottom-left"
      style={{
        width: 340,
        maxHeight: 260,
        display: 'flex',
        flexDirection: 'column',
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        boxShadow: '0 4px 12px #0000001a',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 10px',
          borderBottom: '1px solid #f1f5f9',
        }}
      >
        <strong style={{ fontSize: 13, color: isValid ? '#16a34a' : '#dc2626' }}>
          {isValid ? '✓ Graph valid' : `⚠ ${issues.length} issue(s)`}
        </strong>
        <button
          type="button"
          onClick={() => void validateModel()}
          disabled={validating || !modelId}
          style={{
            padding: '3px 10px',
            fontSize: 12,
            border: '1px solid #cbd5e1',
            borderRadius: 6,
            background: '#fff',
            cursor: validating || !modelId ? 'default' : 'pointer',
          }}
        >
          {validating ? 'Checking…' : 'Re-validate'}
        </button>
      </div>

      <ul
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          overflowY: 'auto',
        }}
      >
        {issues.length === 0 && (
          <li style={{ padding: '10px', color: '#64748b', fontSize: 12 }}>
            No issues detected.
          </li>
        )}
        {issues.map((issue, idx) => {
          const color = SEVERITY_COLOR[issue.severity] ?? '#64748b';
          const target = issue.entities[0];
          return (
            <li
              key={`${issue.code}-${idx}`}
              onClick={() => target && focusEntity(target)}
              style={{
                padding: '6px 10px',
                borderBottom: '1px solid #f8fafc',
                cursor: target ? 'pointer' : 'default',
                fontSize: 12,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  background: color,
                  color: '#fff',
                  borderRadius: 4,
                  padding: '0 6px',
                  fontSize: 10,
                  fontWeight: 700,
                  marginRight: 6,
                }}
              >
                {issue.code}
              </span>
              <span style={{ color: '#334155' }}>{issue.message}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
