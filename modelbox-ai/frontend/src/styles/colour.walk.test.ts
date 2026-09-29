/**
 * F1 breadth — no screen invents a colour.
 *
 * `tokens.ts` and `theme.test.ts` keep the *token layer* single-sourced, and
 * `ui.css.test.ts` keeps the stylesheet reading variables rather than values.
 * None of them can say anything about a call site that never reached for a
 * token at all, and that is where the frontend actually is: this gate landed
 * on 358 colour literals across 20 files, written before the token layer
 * existed, and the ceiling below comes down as they are converted. `#dc2626`
 * appeared 22 times and `#16a34a` eleven — Tailwind's defaults, neither of
 * them the brand's, and the second measures 3.30:1 on white.
 *
 * So this is the burn-down, and it is a **budget rather than an allowlist**.
 * A file listed here declares exactly how many literals it still has, and the
 * assertion is equality, not a ceiling: converting three of `trainer/page.tsx`'s
 * 65 turns this test red until the number is lowered to 62. That is deliberate
 * and it is the same rule as a `strict=True` xfail — a burn-down that tolerates
 * being beaten silently stops being a measurement of what is left. The count
 * can only be edited downwards; a rise fails the same assertion.
 *
 * **Why a test rather than an ESLint rule.** `no-restricted-syntax` can match
 * these, but it has one verdict per site, so the 358 that exist today would
 * each need an `eslint-disable` comment — 358 edits that *permit* the literal
 * rather than count it, and no number anywhere saying how much is left. The
 * budget lives in one place here and reads as a burn-down.
 *
 * **What this catches and what it does not.** It matches hex literals and
 * `rgb()`/`rgba()` in code, which is how every one of the 358 is written. It
 * does not match a CSS named colour (`'white'`, `'red'`), because the false
 * positives are prose and identifiers; a call site determined to hard-code a
 * colour can still do it that way. It is a tripwire on the path people take,
 * not a proof that no literal can exist — the same claim `modals.walk.test.ts`
 * makes about hand-rolled dialogs.
 *
 * **Colour only.** F1 is colour *and* type, and type is gated by
 * `type.walk.test.ts` — its twin, which shares this file's walk and comment
 * stripper through `@/test/sourceWalk`. Until that landed this paragraph read
 * "type is not gated here… a stated gap, not an implied clean bill", and it
 * also said the frontend spells **158** font sizes as bare numbers. The
 * measured figure is **147**, an over-count of eleven, and it had not moved
 * since this gate opened. Both are corrected there and here in the same commit.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  OWNS_THE_VALUES,
  SRC,
  relative,
  sources,
  stripComments,
  walk,
} from '@/test/sourceWalk';

/**
 * Every file with colour literals left in it, and how many.
 *
 * Lower a number when you convert a call site; delete the entry when it reaches
 * zero. Do not raise one — a new literal is what this exists to stop.
 */
const BUDGET: Readonly<Record<string, number>> = {
  // **The one file where an unreachable token is the right call**, and it says
  // so itself: `global-error.tsx` catches a throw in the root layout, which is
  // the case where `ui.css` — imported by that layout — may never have loaded.
  // A boundary that depends on the thing that broke is not a boundary. Held at
  // exactly 6 rather than removed, so the exemption stays visible and bounded.
  'app/global-error.tsx': 6,

  // **Violet, and it needs a design decision rather than a conversion.**
  // `#7c3aed` with its `#f5f3ff` tint and `#ddd6fe` border is the Requirements
  // Library accent, and the palette contains no violet. `entityAccent.HUB` is
  // `#9333EA`, but that is an *entity type* accent — spending it on a library
  // button would conflate two vocabularies that happen to be the same hue.
  // Recorded per file so the shape of the decision is visible: it is one
  // colour, one tint and one border, in five places.
  'app/canvas/page.tsx': 3,
  'app/page.tsx': 3,
  'app/trainer/page.tsx': 3,
  'components/migration/DiffPanel.tsx': 3,
  'components/TemplateLibraryModal.tsx': 3,
  // The tier label, flagged at the burn-down's own opening and still open.
  'components/canvas/EntityNode.tsx': 1,
};

/** The burn-down as one number, so a run says how much of F1 is left. */
const BUDGET_TOTAL = Object.values(BUDGET).reduce((a, b) => a + b, 0);

/**
 * What this gate opened at, in `1eaaa05`. 358 literals had been converted down
 * to 332 by the time the constant was introduced; it is the ceiling the total
 * is held under, and it does not move when a budget entry is lowered.
 */
const OPENED_AT = 332;

const LITERAL = /#[0-9a-fA-F]{3,8}\b|rgba?\(/g;

/** Colour literals written in code, comments excluded. */
export function countColourLiterals(source: string): number {
  return (stripComments(source).match(LITERAL) || []).length;
}

describe('colour comes from tokens', () => {
  it('found sources to check', () => {
    // Precondition. A walk that returned nothing — a renamed directory, a
    // changed extension — would iterate an empty list and report green having
    // read no files at all. This repository has shipped that shape four times.
    expect(sources.length).toBeGreaterThan(20);
  });

  it('has the token module it is directing call sites to', () => {
    // The second precondition: this gate is only meaningful while `tokens.ts`
    // exists to be the alternative. Deleted, every assertion below still passes
    // on a frontend with no token layer at all.
    expect(walk(SRC).some((p) => p.endsWith(join('styles', 'tokens.ts')))).toBe(true);
  });

  it('detects the literal forms it claims to', () => {
    // Third precondition, and the one that matters most: a detector that
    // matched nothing would report every file at zero and read as a clean
    // frontend. Each form is one the frontend actually contains.
    expect(countColourLiterals("color: '#2563EB'")).toBe(1);
    expect(countColourLiterals("color: '#fff'")).toBe(1);
    expect(countColourLiterals("background: '#0f172a99'")).toBe(1);
    expect(countColourLiterals('background: rgba(15, 23, 42, 0.55)')).toBe(1);
  });

  it('reads comments out and code in', () => {
    // The stripper is the one part of this that can silently under-count, so
    // both directions are pinned. The third case is the regression that would
    // matter: a `//` inside a string must not take the rest of the line with
    // it, or a literal after any URL becomes invisible to the gate.
    expect(countColourLiterals('/** the #dc2626 we removed */')).toBe(0);
    expect(countColourLiterals('// was #16a34a')).toBe(0);
    expect(countColourLiterals("const u = 'https://x'; const c = '#2563EB';")).toBe(1);
  });

  it.each(Object.entries(BUDGET))(
    '%s has exactly its budgeted %i colour literals',
    (path, budgeted) => {
      const actual = countColourLiterals(readFileSync(join(SRC, path), 'utf-8'));
      expect(
        actual,
        actual < budgeted
          ? `${path} is down to ${actual}; lower its BUDGET entry to match`
          : `${path} gained a colour literal — reach for a token in styles/tokens.ts`,
      ).toBe(budgeted);
    },
  );

  it('has no colour literals outside the budget', () => {
    // The budget names the files that had literals when the gate landed. A file
    // written tomorrow is covered on arrival, which a list of twenty would not
    // be — and a file that reaches zero and is deleted from the budget is held
    // there by this assertion rather than quietly allowed to regress.
    const unbudgeted = sources
      .map((path) => ({ path: relative(path), n: countColourLiterals(readFileSync(path, 'utf-8')) }))
      .filter(({ path, n }) => n > 0 && !(path in BUDGET));

    expect(unbudgeted.map(({ path, n }) => `${path} (${n})`)).toEqual([]);
  });

  it('never has more colour literals than the budget opened with', () => {
    // F1's burn-down in one number. It exists so a run reports progress rather
    // than only failure, and so a budget entry edited upwards to silence the
    // per-file assertion fails here as well.
    //
    // The comparison is against a fixed `OPENED_AT` rather than a number in
    // this test's name. It used to read "has 332 colour literals left", which
    // was true when written and becomes false with the first conversion — the
    // assertion still passes, so nothing reports that the headline has rotted.
    // A test whose name states a number the assertion does not enforce will
    // eventually state a wrong one.
    expect(BUDGET_TOTAL).toBeLessThanOrEqual(OPENED_AT);
  });
});
