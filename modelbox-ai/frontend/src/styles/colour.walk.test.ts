/**
 * F1 breadth — no screen invents a colour.
 *
 * `tokens.ts` and `theme.test.ts` keep the *token layer* single-sourced, and
 * `ui.css.test.ts` keeps the stylesheet reading variables rather than values.
 * None of them can say anything about a call site that never reached for a
 * token at all, and that is where the frontend actually is: 358 colour
 * literals across 20 files, written before the token layer existed. `#dc2626`
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
 * **Colour only.** F1 is colour *and* type, and type is not gated here. The
 * frontend spells 158 font sizes as bare numbers (`fontSize: 13`), which needs
 * a different detector and a budget of its own; leaving it out is a stated gap,
 * not an implied clean bill.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = join(__dirname, '..');

/**
 * The two files that own colour values. `tokens.ts` is the specification's
 * machine-readable twin, and `cssVars.ts` composes the custom properties the
 * stylesheet reads — including the one value it admits is not a token, the
 * modal shadow. Everything else reaches a colour through one of them.
 */
const OWNS_THE_VALUES = [join('styles', 'tokens.ts'), join('styles', 'cssVars.ts')];

/**
 * Every file with colour literals left in it, and how many.
 *
 * Lower a number when you convert a call site; delete the entry when it reaches
 * zero. Do not raise one — a new literal is what this exists to stop.
 */
const BUDGET: Readonly<Record<string, number>> = {
  'app/trainer/page.tsx': 65,
  'app/settings/egress/page.tsx': 30,
  'components/editor/ExportPanel.tsx': 26,
  'app/settings/api-keys/page.tsx': 25,
  'components/migration/DiffPanel.tsx': 25,
  'app/page.tsx': 22,
  'components/canvas/ColumnSemanticEditor.tsx': 22,
  'app/canvas/page.tsx': 20,
  'components/TemplateLibraryModal.tsx': 20,
  'app/settings/connectors/page.tsx': 17,
  'components/canvas/EntityNode.tsx': 14,
  'components/canvas/ValidationPanel.tsx': 13,
  'components/trainer/LabModal.tsx': 12,
  'app/docs/page.tsx': 11,
  'components/auth/AuthModal.tsx': 10,
  'components/canvas/EntitySettingsEditor.tsx': 9,
  'components/auth/AuthBadge.tsx': 8,
  'app/global-error.tsx': 6,
  'components/canvas/ControlPanel.tsx': 2,
  'components/canvas/ERDCanvas.tsx': 1,
};

/** The burn-down as one number, so a run says how much of F1 is left. */
const BUDGET_TOTAL = Object.values(BUDGET).reduce((a, b) => a + b, 0);

const LITERAL = /#[0-9a-fA-F]{3,8}\b|rgba?\(/g;

/**
 * Comments are not call sites.
 *
 * This file's own header names `#dc2626`, and `Banner.tsx` documents the amber
 * palette it no longer hard-codes. Counting those would make the burn-down
 * unreadable and would punish explaining a colour, which is the opposite of
 * what is wanted.
 *
 * The line-comment pass will not fire on a `//` preceded by `:`, `'`, `"` or a
 * backtick, so a URL in a string keeps the rest of its line. The error it can
 * still make is stripping too little — a `//` comment inside a template
 * literal — and that direction over-counts, which fails loudly rather than
 * passing quietly.
 */
export function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .map((line) => line.replace(/(^|[^:'"`])\/\/.*$/, '$1'))
    .join('\n');
}

/** Colour literals written in code, comments excluded. */
export function countColourLiterals(source: string): number {
  return (stripComments(source).match(LITERAL) || []).length;
}

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return walk(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

/**
 * Tests are exempt as a class.
 *
 * A test that asserts a token's value has to name the value, or it compares the
 * token to itself and asserts nothing — `tokens.test.ts` is exactly that check
 * against the specification document. `status-colour.test.tsx` names the three
 * retired colours in order to ban them. Both are the gate, not the debt.
 */
const isTest = (path: string): boolean => /\.test\.tsx?$/.test(path);

const relative = (path: string): string =>
  path.slice(SRC.length + 1).split(sep).join('/');

const sources = walk(SRC).filter(
  (path) => !isTest(path) && !OWNS_THE_VALUES.some((owned) => path.endsWith(owned)),
);

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

  it('has 358 colour literals left to convert', () => {
    // F1's burn-down in one number. It exists so a run reports progress rather
    // than only failure, and so a budget entry edited upwards to silence the
    // per-file assertion fails here as well.
    expect(BUDGET_TOTAL).toBeLessThanOrEqual(358);
  });
});
