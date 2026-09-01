/**
 * F1's other half — type. The colour walk's twin, and the gate that was missing.
 *
 * `colour.walk.test.ts` opens by admitting this: *"F1 is colour **and** type,
 * and type is not gated here… leaving it out is a stated gap, not an implied
 * clean bill."* This closes the gap. Until it landed, F1 had a burn-down on one
 * of its two halves and nothing at all on the other, so a run could report
 * progress on a criterion while half of it was unmeasured.
 *
 * **Four properties, not one.** A `type` token is a group — size, weight, line
 * height and tracking arrive together, and `styles/tokens.ts` declares them
 * that way. Counting only `fontSize` would let a converted call site keep a
 * hand-written `fontWeight: 600` beside a tokenised size and still read as
 * done, which is the same defect as a colour token beside a hex literal. The
 * spread is 147 sizes, 94 weights, 19 line heights and 4 tracking values.
 *
 * **The header's count was wrong, and this file is where that was found.**
 * `colour.walk.test.ts` states "158 font sizes"; the measured figure is **147**,
 * an over-count of eleven, and it has not moved since the burn-down opened.
 * Corrected there in the same commit as this file.
 *
 * **What this does not catch**, stated for the same reason the colour walk
 * states its gaps:
 *
 * - `font-size` in `.css` files (20 declarations). `ui.css` is the stylesheet
 *   that *supplies* the tokens as custom properties, and `ui.css.test.ts`
 *   already asserts it holds no raw values — but a new `.css` file would be
 *   invisible here.
 * - A size written as a string (`fontSize: '13px'`). The frontend does not
 *   currently contain one; the detector is pinned against that form below so
 *   the omission is a decision rather than an accident.
 * - Tailwind type classes. There are none in the call sites this budget covers,
 *   and `theme.test.ts` holds the config side.
 *
 * Like its twin this is a tripwire on the path people take, not a proof that no
 * hand-written type can exist.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { SRC, relative, sources, stripComments } from '@/test/sourceWalk';

/**
 * Every file with hand-written type left in it, and how many declarations.
 *
 * Lower a number when you convert a call site; delete the entry when it reaches
 * zero. Do not raise one. The rule is the colour budget's: **equality, not a
 * ceiling**, so converting three of `trainer/page.tsx`'s 36 turns this red until
 * the number says 33.
 */
const BUDGET: Readonly<Record<string, number>> = {
  'app/trainer/page.tsx': 36,
  'app/page.tsx': 27,
  'components/canvas/ColumnSemanticEditor.tsx': 25,
  'app/settings/api-keys/page.tsx': 19,
  'components/migration/DiffPanel.tsx': 18,
  'app/settings/egress/page.tsx': 17,
  'app/settings/connectors/page.tsx': 16,
  'components/TemplateLibraryModal.tsx': 15,
  'app/canvas/page.tsx': 15,
  'components/canvas/EntityNode.tsx': 11,
  'components/trainer/LabModal.tsx': 10,
  'components/canvas/EntitySettingsEditor.tsx': 10,
  'components/editor/ExportPanel.tsx': 8,
  'app/docs/page.tsx': 7,
  'components/canvas/ValidationPanel.tsx': 6,
  'app/global-error.tsx': 5,
  'components/auth/AuthModal.tsx': 4,
  'components/auth/AuthBadge.tsx': 3,
  'components/editor/CodeEditor.tsx': 1,
  'components/canvas/ControlPanel.tsx': 1,
};

/** The burn-down as one number, so a run says how much of F1's type half is left. */
const BUDGET_TOTAL = Object.values(BUDGET).reduce((a, b) => a + b, 0);

/**
 * What the gate opened at. A constant, so the total assertion below compares
 * against something that does not move when a budget entry is lowered — the
 * failure the colour walk's headline has, where the number in the test's own
 * name goes stale as work lands and nothing says so.
 */
const OPENED_AT = 254;

const DECLARATION = /(?:fontSize|fontWeight|lineHeight|letterSpacing): *-?[0-9.]+/g;

/** Hand-written type declarations in code, comments excluded. */
export function countTypeDeclarations(source: string): number {
  return (stripComments(source).match(DECLARATION) || []).length;
}

describe('type comes from tokens', () => {
  it('found sources to check', () => {
    // Precondition, shared with the colour walk: an empty walk would report
    // every file at zero and read as a fully converted frontend.
    expect(sources.length).toBeGreaterThan(20);
  });

  it('detects each of the four properties it claims to', () => {
    // The detector is the whole gate. One that matched nothing would put every
    // file at zero, and this budget would then be a list of lies that passes.
    expect(countTypeDeclarations('fontSize: 13')).toBe(1);
    expect(countTypeDeclarations('fontWeight: 600')).toBe(1);
    expect(countTypeDeclarations('lineHeight: 1.45')).toBe(1);
    expect(countTypeDeclarations('letterSpacing: -0.01')).toBe(1);
    expect(countTypeDeclarations('fontSize: 13, fontWeight: 700')).toBe(2);
  });

  it('ignores the forms that are already tokenised', () => {
    // The discriminating half. A detector that matched a token spread would
    // count converted call sites as debt, so converting a file would not lower
    // its number and the burn-down could never reach zero.
    expect(countTypeDeclarations('...type.bodySmall')).toBe(0);
    expect(countTypeDeclarations("fontSize: 'var(--mb-type-body-size)'")).toBe(0);
    expect(countTypeDeclarations('fontSize: type.caption.fontSize')).toBe(0);
    // Documented gap, pinned so it stays a decision: a string size is not
    // matched. The frontend contains none today.
    expect(countTypeDeclarations("fontSize: '13px'")).toBe(0);
  });

  it('reads comments out and code in', () => {
    expect(countTypeDeclarations('/** was fontSize: 13 */')).toBe(0);
    expect(countTypeDeclarations('// fontWeight: 700 before the ramp')).toBe(0);
    expect(
      countTypeDeclarations("const u = 'https://x'; const s = { fontSize: 12 };"),
    ).toBe(1);
  });

  it.each(Object.entries(BUDGET))(
    '%s has exactly its budgeted %i type declarations',
    (path, budgeted) => {
      const actual = countTypeDeclarations(readFileSync(join(SRC, path), 'utf-8'));
      expect(
        actual,
        actual < budgeted
          ? `${path} is down to ${actual}; lower its BUDGET entry to match`
          : `${path} gained a hand-written type value — reach for \`type\` in styles/tokens.ts`,
      ).toBe(budgeted);
    },
  );

  it('has no hand-written type outside the budget', () => {
    const unbudgeted = sources
      .map((path) => ({
        path: relative(path),
        n: countTypeDeclarations(readFileSync(path, 'utf-8')),
      }))
      .filter(({ path, n }) => n > 0 && !(path in BUDGET));

    expect(unbudgeted.map(({ path, n }) => `${path} (${n})`)).toEqual([]);
  });

  it('never has more type declarations than the budget opened with', () => {
    // Deliberately compared against a fixed `OPENED_AT` rather than against a
    // number written into this test's name. A budget entry edited upwards to
    // silence the per-file assertion fails here too, and the assertion stays
    // true — rather than stale — as conversions land.
    expect(BUDGET_TOTAL).toBeLessThanOrEqual(OPENED_AT);
  });
});
