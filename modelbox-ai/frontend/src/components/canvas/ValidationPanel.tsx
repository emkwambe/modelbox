'use client';

/**
 * ValidationPanel — bottom-left overlay listing graph lint issues (FR-2.3).
 *
 * Shows the current ValidationReport, a "Re-validate" trigger, and lets the
 * user click an issue to select + centre the offending entity node.
 */

import { Panel, useReactFlow } from '@xyflow/react';

import { useCanvasStore } from '@/store/canvasStore';
import { color, semantic, surface } from '@/styles/tokens';

// The panel sits on a white card, so both take the on-light variants. The
// brand's Amber measures 2.15:1 on white — as a warning colour it would be
// decoration rather than a signal.
const SEVERITY_COLOR: Record<string, string> = {
  error: semantic.breaking.onLight,
  warning: semantic.preview.onLight,
};

/**
 * A severity this panel has no colour for.
 *
 * `neutral-500` rather than `neutral-400`: the fallback is the ground of a
 * solid white-on-colour pill, and white on `neutral-400` measures 2.56:1. An
 * unknown severity is the case nobody looks at, which is exactly where an
 * unreadable default survives.
 */
const UNKNOWN_SEVERITY = color.neutral[500];

/**
 * The panel's elevation. `#0000001a` was pure black at 10%; this is
 * `neutral-900` at the same alpha, matching the node shadows on the canvas
 * behind it. Three files now spell an elevation locally — if a fourth appears
 * it has earned a token rather than another copy.
 */
const SHADOW = `0 4px 12px ${color.neutral[900]}1A`;

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
        background: color.white,
        border: `1px solid ${color.neutral[200]}`,
        borderRadius: 8,
        boxShadow: SHADOW,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 10px',
          borderBottom: `1px solid ${color.neutral[100]}`,
        }}
      >
        <strong
          style={{
            fontSize: 13,
            // `#16a34a` and `#dc2626` — the two retired values named in
            // `status-colour.test.tsx`, and the reason this panel was worth
            // taking before the larger files. The green measured 3.30:1 on
            // white, so the headline that says the graph is valid was the one
            // line here that failed the contrast floor.
            color: isValid ? semantic.validated.onLight : semantic.breaking.onLight,
          }}
        >
          {isValid ? '✓ Graph valid' : `⚠ ${issues.length} issue(s)`}
        </strong>
        <button
          type="button"
          onClick={() => void validateModel()}
          disabled={validating || !modelId}
          style={{
            padding: '3px 10px',
            fontSize: 12,
            border: `1px solid ${color.neutral[300]}`,
            borderRadius: 6,
            background: color.white,
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
          <li style={{ padding: '10px', color: color.neutral[500], fontSize: 12 }}>
            No issues detected.
          </li>
        )}
        {issues.map((issue, idx) => {
          // Renamed off `color`, which now shadows the token module inside this
          // callback — the kind of collision that reads as a missing token
          // rather than as a scope bug.
          const severityColor = SEVERITY_COLOR[issue.severity] ?? UNKNOWN_SEVERITY;
          const target = issue.entities[0];
          return (
            <li
              key={`${issue.code}-${idx}`}
              onClick={() => target && focusEntity(target)}
              style={{
                padding: '6px 10px',
                borderBottom: `1px solid ${surface.page}`,
                cursor: target ? 'pointer' : 'default',
                fontSize: 12,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  background: severityColor,
                  color: color.white,
                  borderRadius: 4,
                  padding: '0 6px',
                  fontSize: 10,
                  fontWeight: 700,
                  marginRight: 6,
                }}
              >
                {issue.code}
              </span>
              <span style={{ color: color.neutral[700] }}>{issue.message}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
