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
  radius,
  relativeLuminance,
  semantic,
  space,
  surface,
  type,
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

  it('declares every semantic role against every surface in the product', () => {
    // **The hole this closes was live until 2026-09-01.** `ExportPanel` sits on
    // `neutral-900` and had already been converted to the `onDark` semantic
    // variants — a pair the token API is meant to make unreachable, and one no
    // assertion covered, so the status colours on the one dark surface a user
    // reads paragraphs on were unmeasured while looking fully tokenised.
    //
    // Declaring `surface.panel` fixed that instance. This fixes the *class*:
    // adding a surface now fails until its pairs are declared, which is the
    // difference between a defect corrected and a defect prevented.
    //
    // Light or dark is derived from the surface's own luminance rather than
    // from a hand-kept list, so a new ground cannot be classified wrongly by
    // someone adding it in a hurry.
    for (const [name, bg] of Object.entries(surface)) {
      const onLight = relativeLuminance(bg) > 0.5;
      for (const role of ['validated', 'breaking', 'preview'] as const) {
        const fg = onLight ? semantic[role].onLight : semantic[role].onDark;
        expect(
          PAIRS.some((pair) => pair.fg === fg && pair.bg === bg),
          `${role} on surface.${name} is used by the product but not declared in PAIRS`,
        ).toBe(true);
      }
    }
  });

  it('has surfaces of both kinds, or the rule above tests one branch', () => {
    // The discriminating half. If every surface were light, the `onDark` arm
    // would never execute and the loop would assert half of what it claims.
    const luminances = Object.values(surface).map(relativeLuminance);
    expect(luminances.some((l) => l > 0.5)).toBe(true);
    expect(luminances.some((l) => l <= 0.5)).toBe(true);
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

  it('publishes the type ramp the code exports, exactly', () => {
    // The colour assertions above check only that a hex appears *somewhere* in
    // the document. The type scale is a table with four values per row, so it
    // can be checked properly: every row is parsed and compared field by field,
    // and the row count must equal the number of exported tokens — so a token
    // added to the code without the document fails, and so does one left in the
    // document after the code drops it.
    const spec = readSpec();
    const rows = [
      ...spec.matchAll(
        /^\|\s*`(\w+)`\s*\|\s*([\d.]+rem)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*(\S+)\s*\|/gm,
      ),
    ];
    expect(rows.length, 'no type rows found to check').toBe(
      Object.keys(type).length,
    );

    const published = Object.fromEntries(
      rows.map((r) => [
        r[1],
        { size: r[2], weight: Number(r[3]), lineHeight: Number(r[4]), tracking: r[5] },
      ]),
    );
    expect(published).toEqual(type);
  });

  it('publishes the spacing and radius steps the code exports', () => {
    // One table, two ramps: `space` on the left, `radius` on the right, with
    // the right cell empty where the ramps differ in length.
    const spec = readSpec();
    const rows = [
      ...spec.matchAll(
        /^\|\s*`(\w+)`\s*\|\s*(\d+)px\s*\|\s*\|\s*(?:`(\w+)`\s*\|\s*(\d+)px\s*)?\|/gm,
      ),
    ];
    expect(rows.length, 'no spacing rows found to check').toBeGreaterThan(0);

    const publishedSpace: Record<string, number> = {};
    const publishedRadius: Record<string, number> = {};
    for (const row of rows) {
      if (row[1] && row[2]) publishedSpace[row[1]] = Number(row[2]);
      if (row[3] && row[4]) publishedRadius[row[3]] = Number(row[4]);
    }

    expect(publishedSpace).toEqual(space);
    expect(publishedRadius).toEqual(radius);
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
