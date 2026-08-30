/**
 * F3 — pass/fail state uses semantic colour consistently.
 *
 * "Consistently" is the load-bearing word, and it is why this test renders
 * components rather than grepping for hex values. Before Sprint 6 the product
 * used `#dc2626` for error in 22 places and `#16a34a` for success in 11 — both
 * Tailwind defaults, neither the brand's colour, and `#16a34a` measures 3.30:1
 * on white, which fails the contrast floor while looking perfectly fine to a
 * sighted reviewer on a good monitor.
 *
 * A grep would have said "one value, used consistently" and been satisfied.
 * What matters is that the value is *the semantic token for the surface the
 * status sits on*, so this asserts against `semantic.*.onLight` directly.
 *
 * Mutation, 2026-08-29: setting `ERROR_COLOR` in `EntityNode` back to
 * `#dc2626` fails the rendered PII-marker assertion and nothing else — the
 * literal is caught where it is used, not merely where it is declared.
 */

import { ReactFlowProvider } from '@xyflow/react';
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it } from 'vitest';

import { contrastRatio, semantic, surface } from '@/styles/tokens';
import type { ValidationIssue } from '@/types/schema';

import EntityNode from './EntityNode';
import { ENTITY_ACCENT } from './EntityNode';

const issue = (code: string, severity: string, entity: string): ValidationIssue =>
  ({
    code,
    severity,
    message: `${code} on ${entity}`,
    entities: [entity],
    entity_name: entity,
  }) as ValidationIssue;

describe('semantic colour', () => {
  it('never uses the pre-Sprint-6 status values', () => {
    // The specific values that were wrong, named so a revert is loud. Both are
    // Tailwind defaults rather than brand colours, and the green one fails the
    // contrast floor outright.
    const retired = ['#dc2626', '#16a34a', '#f59e0b'];
    for (const role of Object.values(semantic)) {
      expect(retired).not.toContain(role.onLight.toLowerCase());
    }
  });

  it('uses colours that are legible on the surface they sit on', () => {
    for (const [name, role] of Object.entries(semantic)) {
      expect(
        contrastRatio(role.onLight, surface.card),
        `${name}.onLight on a card`,
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrastRatio(role.onDark, surface.dark),
        `${name}.onDark on the canvas ground`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps entity accents legible behind white text', () => {
    // Accents are a ground, not a foreground: white sits on them. They are held
    // to the 3:1 non-text floor rather than 4.5:1.
    for (const [entity, accent] of Object.entries(ENTITY_ACCENT)) {
      expect(contrastRatio('#FFFFFF', accent), `white on ${entity}`).toBeGreaterThanOrEqual(3);
    }
  });
});

describe('EntityNode status markers', () => {
  const node = (issues: ValidationIssue[]) => ({
    id: 'n1',
    type: 'entity' as const,
    position: { x: 0, y: 0 },
    data: {
      entity_name: 'fact_transaction',
      entity_type: 'FACT' as const,
      description: null,
      grain: 'One row per transaction leg.',
      tier: null,
      freshness_sla: null,
      agg_time_column: null,
      columns: [
        {
          name: 'email_address',
          data_type: 'VARCHAR(255)',
          is_primary_key: false,
          is_foreign_key: false,
          is_pii: true,
          pii_type: 'EMAIL' as const,
          is_metric: false,
        },
      ],
      issues,
    },
  });

  it('marks PII with the breaking token, not a raw literal', () => {
    const props = { ...node([]), selected: false } as unknown as ComponentProps<
      typeof EntityNode
    >;
    render(
      // `Handle` reads React Flow's store, so the node needs its provider even
      // though nothing here is a flow.
      <ReactFlowProvider>
        <EntityNode {...props} />
      </ReactFlowProvider>,
    );
    const marker = screen.getByTitle('EMAIL');
    expect(marker).toHaveStyle({ color: semantic.breaking.onLight });
  });
});
