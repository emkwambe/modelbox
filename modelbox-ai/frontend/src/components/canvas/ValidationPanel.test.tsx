/**
 * F1/F3 — the validation headline says pass or fail in the brand's colours.
 *
 * This panel held the last two live uses of the pair `status-colour.test.tsx`
 * was written to ban: `#16a34a` for valid and `#dc2626` for invalid. That test
 * asserts the *tokens* are not those values, which it can do without knowing
 * whether anything uses the tokens — and here, nothing did. The headline that
 * tells a user their graph is valid was drawn at **3.30:1** on white.
 *
 * So these assertions render. A source-level check would have been satisfied by
 * `SEVERITY_COLOR` already being token-backed at the top of the file, which it
 * was, in the same file whose headline was not.
 */

import { ReactFlowProvider } from '@xyflow/react';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import { color, contrastRatio, semantic, surface } from '@/styles/tokens';
import type { ValidationIssue, ValidationReport } from '@/types/schema';

import ValidationPanel from './ValidationPanel';

const issue = (code: string, severity: string): ValidationIssue =>
  ({
    code,
    severity,
    message: `${code} needs attention`,
    entities: ['fact_transaction'],
    entity_name: 'fact_transaction',
    column_name: null,
  }) as ValidationIssue;

function renderPanel(report: ValidationReport) {
  useCanvasStore.getState().setValidation(report);
  return render(
    <ReactFlowProvider>
      <ValidationPanel />
    </ReactFlowProvider>,
  );
}

afterEach(() => {
  useCanvasStore.getState().setValidation(null);
});

describe('ValidationPanel headline', () => {
  it('says valid in the validated token, not the retired green', () => {
    // Mutation: restoring `#16a34a` fails here and nowhere else in the suite.
    renderPanel({ is_valid: true, issues: [] });
    expect(screen.getByText('✓ Graph valid')).toHaveStyle({
      color: semantic.validated.onLight,
    });
  });

  it('says invalid in the breaking token, not the retired red', () => {
    renderPanel({ is_valid: false, issues: [issue('MISSING_PK', 'error')] });
    expect(screen.getByText('⚠ 1 issue(s)')).toHaveStyle({
      color: semantic.breaking.onLight,
    });
  });

  it('draws the valid headline above the contrast floor', () => {
    // The point of the change, separate from which token was used: the old
    // value was not merely off-brand, it was unreadable. Both halves are
    // asserted because a token swap that happened to be equally illegible
    // would satisfy the test above on its own.
    expect(
      contrastRatio(semantic.validated.onLight, surface.card),
      'valid headline on the panel card',
    ).toBeGreaterThanOrEqual(4.5);
  });

  it('would have failed on the green it replaced', () => {
    // Precondition for the floor above. Without it, a threshold that everything
    // passes reads as a gate and is a formality — and this is the specific
    // value that passed visual review and failed WCAG.
    expect(contrastRatio('#16a34a', surface.card)).toBeLessThan(4.5);
  });
});

describe('ValidationPanel severity pills', () => {
  it('carries white on a ground dark enough to read it', () => {
    // The pills are solid: the severity colour is the *ground*, and the label
    // is white at 10px bold, which is not large text. Every ground the panel
    // can produce is checked, the unknown-severity fallback included — that is
    // the one nobody looks at, and where `neutral-400` would have survived.
    const grounds = {
      error: semantic.breaking.onLight,
      warning: semantic.preview.onLight,
      unknown: color.neutral[500],
    };
    for (const [name, ground] of Object.entries(grounds)) {
      expect(
        contrastRatio(color.white, ground),
        `white on the ${name} pill`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('falls back to a legible grey for a severity it has no colour for', () => {
    // `severity: 'info'` is in the schema and has no entry in `SEVERITY_COLOR`.
    // Rendered rather than asserted against the constant, because the fallback
    // is reached through a `??` that a refactor can quietly drop.
    renderPanel({ is_valid: false, issues: [issue('NAMING_HINT', 'info')] });
    expect(screen.getByText('NAMING_HINT')).toHaveStyle({
      background: color.neutral[500],
      color: color.white,
    });
  });
});
