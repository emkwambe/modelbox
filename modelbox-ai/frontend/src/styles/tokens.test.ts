/**
 * F6 — contrast meets the brand system's own WCAG standard.
 *
 * The standard now lives in `docs/ModelBox_AI_Design_Tokens.md` rather than in
 * `docs/research/`, because criterion E5 quarantines research as "cannot be
 * read as specification" while F1 and F6 cited a research document as the
 * standard. Promoting it was not bookkeeping: measuring the research
 * document's contrast table found three published ratios wrong, one of them in
 * the unsafe direction — Rose on white was claimed at 5.3:1 and measures
 * 3.67:1, failing the document's own 4.5:1 floor.
 *
 * These tests exist so that cannot happen twice. The second one recomputes
 * every ratio the specification publishes, so the document's own numbers are
 * checkable rather than asserted.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  CONTRAST_FLOOR,
  PAIRS,
  color,
  contrastRatio,
  entityAccent,
  relativeLuminance,
  semantic,
  surface,
} from './tokens';

const SPEC = join(__dirname, '..', '..', '..', 'docs', 'ModelBox_AI_Design_Tokens.md');

const readSpec = (): string => readFileSync(SPEC, 'utf-8');

describe('contrast', () => {
  it('has pairs to check', () => {
    // Standard 12: a comparison against an empty collection passes vacuously.
    // An emptied PAIRS table would make every assertion below succeed while
    // checking nothing at all.
    expect(PAIRS.length).toBeGreaterThan(15);
  });

  it.each(PAIRS)('$name meets its floor', ({ fg, bg, role }) => {
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(CONTRAST_FLOOR[role]);
  });

  it('computes the ratios a reference implementation would', () => {
    // Fixture sanity for the maths itself. Black on white is exactly 21:1 and
    // any colour against itself is exactly 1:1; a broken luminance function
    // that returned a constant would pass every pair above and fail here.
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 5);
    expect(contrastRatio('#2563EB', '#2563EB')).toBeCloseTo(1, 5);
    expect(relativeLuminance('#FFFFFF')).toBeCloseTo(1, 5);
    expect(relativeLuminance('#000000')).toBeCloseTo(0, 5);
  });

  it('rejects the semantic colours on the ground they fail on', () => {
    // The reason on-light variants exist. These are the brand's own Emerald and
    // Amber, measured against the surface that makes up the whole product
    // except the canvas — 2.54:1 and 2.15:1. If a future edit points
    // `onLight` back at them, the per-pair assertions above catch it; this
    // states plainly *why* they are separate, so the split is not tidied away
    // by someone who reads two variants as duplication.
    expect(contrastRatio(semantic.validated.onDark, surface.card)).toBeLessThan(4.5);
    expect(contrastRatio(semantic.preview.onDark, surface.card)).toBeLessThan(4.5);
    expect(contrastRatio(semantic.breaking.onDark, surface.card)).toBeLessThan(4.5);
  });

  it('keeps every on-light semantic variant distinct from its on-dark twin', () => {
    for (const role of Object.values(semantic)) {
      expect(role.onLight).not.toBe(role.onDark);
    }
  });
});

describe('the specification and the token module agree', () => {
  it('publishes every semantic value the code uses', () => {
    const spec = readSpec().toUpperCase();
    for (const [name, role] of Object.entries(semantic)) {
      expect(spec, `${name}.onLight missing from the spec`).toContain(
        role.onLight.toUpperCase(),
      );
      expect(spec, `${name}.onDark missing from the spec`).toContain(
        role.onDark.toUpperCase(),
      );
    }
  });

  it('publishes every entity accent', () => {
    const spec = readSpec().toUpperCase();
    for (const [entity, accent] of Object.entries(entityAccent)) {
      expect(spec, `${entity} accent missing from the spec`).toContain(
        accent.toUpperCase(),
      );
    }
  });

  it('publishes every neutral in the ramp', () => {
    const spec = readSpec().toUpperCase();
    for (const value of Object.values(color.neutral)) {
      expect(spec).toContain(value.toUpperCase());
    }
  });

  it('states ratios that recompute to what it claims', () => {
    // The test that would have caught the research document's error. Every
    // "N.NN:1" the specification publishes beside a hex pair is recomputed;
    // a number typed rather than measured fails here.
    //
    // Mutation, 2026-08-29: restoring the research document's original claim
    // for Rose on white — 5.30:1 where it measures 3.67:1 — fails this test and
    // only this test. The historical error is the mutant.
    const spec = readSpec();
    const claims = [
      ...spec.matchAll(/`(#[0-9A-Fa-f]{6})`[^|]*\|[^|]*\|\s*\*{0,2}(\d+\.\d+):1/g),
    ];
    expect(claims.length, 'no published ratios found to check').toBeGreaterThan(0);

    for (const match of claims) {
      const hex = match[1];
      const claimed = match[2];
      if (!hex || !claimed) continue;

      // The ground is not stated machine-readably in the prose table, so every
      // surface the product actually has is a candidate and one of them must
      // match. That is deliberately permissive about *which* pair a row means
      // and exact about the arithmetic: a ratio no surface produces is a number
      // that was typed rather than measured.
      const alternatives = [
        contrastRatio(hex, surface.card),
        contrastRatio(hex, surface.page),
        contrastRatio(hex, surface.dark),
        contrastRatio(hex, color.neutral[900]),
      ];
      const claimedValue = Number(claimed);
      const matches = alternatives.some((r) => Math.abs(r - claimedValue) < 0.05);
      expect(
        matches,
        `spec claims ${claimed}:1 for ${hex}; measured ${alternatives
          .map((r) => r.toFixed(2))
          .join(' / ')}`,
      ).toBe(true);
    }
  });
});
