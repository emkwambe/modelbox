/**
 * F1 — the grounds and greys inside a node come from tokens.
 *
 * `status-colour.test.tsx` covers the *foregrounds* an issue paints, which is
 * F3. This covers what those foregrounds sit on and the grey beside them, which
 * is where `EntityNode`'s remaining literals were: `#fef2f2`, `#fffbeb` and
 * `#dbeafe` for the three row states, and `#94a3b8` for the physical data type.
 *
 * None of the four was in the ramp, and the last one is not merely off-brand —
 * `neutral-400` measures 2.56:1 on the white node body, which fails the body
 * floor at the 12px it is rendered at. So the conversion moved it to
 * `neutral-500` rather than to the token it matched; a contrast failure behind
 * a token name is worse than one in a literal, because it looks decided.
 *
 * These assertions render rather than read the source, for the reason F3's do:
 * a source check would be satisfied by a constant that is token-derived and
 * then never used, and two of the four literals were in a nested ternary where
 * exactly that is easy to do.
 */

import { ReactFlowProvider } from '@xyflow/react';
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { toneColor, toneTint } from '@/components/ui';
import { useCanvasStore } from '@/store/canvasStore';
import { color, contrastRatio, surface } from '@/styles/tokens';
import type { ValidationIssue } from '@/types/schema';

import EntityNode from './EntityNode';

const ENTITY = 'fact_transaction';

const column = (name: string, overrides: Record<string, unknown> = {}) => ({
  name,
  data_type: 'VARCHAR(255)',
  is_primary_key: false,
  is_foreign_key: false,
  is_pii: false,
  pii_type: null,
  is_metric: false,
  ...overrides,
});

const props = () =>
  ({
    id: 'n1',
    type: 'entity',
    position: { x: 0, y: 0 },
    selected: false,
    data: {
      entity_name: ENTITY,
      entity_type: 'FACT',
      description: null,
      grain: null,
      tier: null,
      freshness_sla: null,
      agg_time_column: null,
      columns: [
        column('customer_id', { is_foreign_key: true }),
        column('email_address'),
      ],
      issues: [],
    },
  }) as unknown as ComponentProps<typeof EntityNode>;

const issue = (
  code: string,
  severity: string,
  columnName: string,
): ValidationIssue =>
  ({
    code,
    severity,
    message: `${code} on ${columnName}`,
    entities: [ENTITY],
    entity_name: ENTITY,
    column_name: columnName,
  }) as ValidationIssue;

/**
 * The row states are driven by the store's validation report, not by the node's
 * own `data.issues` — the component reads `useCanvasStore`. A test that seeded
 * `data.issues` instead would render a node with no rows tinted at all and pass
 * every assertion below against `undefined`.
 */
function renderNode(issues: ValidationIssue[] = []) {
  useCanvasStore.getState().setValidation(
    issues.length ? { is_valid: false, issues } : null,
  );
  return render(
    // `Handle` reads React Flow's store, so the node needs its provider.
    <ReactFlowProvider>
      <EntityNode {...props()} />
    </ReactFlowProvider>,
  );
}

const DANGLING_ROW = 'Foreign key references a missing entity.';
const PII_ROW = 'Looks like PII but is not classified (set is_pii/pii_type).';

describe('EntityNode grounds', () => {
  beforeEach(() => {
    useCanvasStore.getState().setValidation(null);
  });

  it('tints a dangling row with the breaking tone, not red-50', () => {
    // Mutation: restoring `#fef2f2` fails here and nowhere else.
    renderNode([issue('DANGLING_REF', 'error', 'customer_id')]);
    expect(screen.getByTitle(DANGLING_ROW)).toHaveStyle({
      background: toneTint('breaking', 'light'),
      color: toneColor('breaking', 'light'),
    });
  });

  it('tints an unclassified-PII row with the preview tone, not amber-50', () => {
    // Mutation: restoring `#fffbeb` fails here and nowhere else.
    renderNode([issue('PII_EXPOSURE', 'warning', 'email_address')]);
    expect(screen.getByTitle(PII_ROW)).toHaveStyle({
      background: toneTint('preview', 'light'),
    });
  });

  it('derives every row tint from the foreground it is read against', () => {
    // The property that matters more than any single value: a tint is the
    // foreground at low alpha, so the two cannot drift apart the way a second
    // hand-picked palette does. This is what `#fef2f2` next to `#BE123C` was —
    // a ground and a foreground nobody had measured together.
    for (const tone of ['breaking', 'preview', 'accent'] as const) {
      const fg = toneColor(tone, 'light');
      expect(toneTint(tone, 'light').startsWith(fg)).toBe(true);
    }
  });

  it('renders the data type at a legible grey', () => {
    // Two assertions, because either alone would pass on a defect. The rendered
    // colour catches a call site that never adopted the token; the ratio
    // catches the token itself being changed to something unreadable, which is
    // how `#94a3b8` got here in the first place.
    renderNode();
    const [type] = screen.getAllByText('VARCHAR(255)');
    expect(type).toHaveStyle({ color: color.neutral[500] });
    expect(
      contrastRatio(color.neutral[500], surface.card),
      'data type on the node body',
    ).toBeGreaterThanOrEqual(4.5);
  });

  it('would have failed on the colour it replaced', () => {
    // The precondition for the test above: `neutral-400` is a real failure and
    // not a value chosen to make a threshold look meaningful. Without this, a
    // floor that everything passes reads as a gate and is a formality.
    expect(contrastRatio(color.neutral[400], surface.card)).toBeLessThan(4.5);
  });
});
