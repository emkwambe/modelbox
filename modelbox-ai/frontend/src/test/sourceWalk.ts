/**
 * The source walk both F1 burn-downs read from.
 *
 * `colour.walk.test.ts` owned this outright until `type.walk.test.ts` needed the
 * same three things — the file list, the path normaliser, and the comment
 * stripper. Copying them would have put **two hand-maintained versions of the
 * comment stripper** in the tree, which is the arrangement `EntityNode`'s accent
 * palette comment describes as guaranteeing that one of them is eventually
 * wrong. It is also the piece most able to fail silently: a stripper that eats
 * too much makes both burn-downs under-count, and an under-count reads as
 * progress.
 *
 * So it lives here once, and both gates pin its behaviour against their own
 * literal forms.
 */

import { readdirSync } from 'node:fs';
import { join, sep } from 'node:path';

/** `frontend/src`. */
export const SRC = join(__dirname, '..');

/**
 * The two files that own design values. `tokens.ts` is the specification's
 * machine-readable twin, and `cssVars.ts` composes the custom properties the
 * stylesheet reads — including the one value it admits is not a token, the
 * modal shadow. Everything else reaches a colour or a type step through one of
 * them, so neither can be counted as debt.
 */
export const OWNS_THE_VALUES = [
  join('styles', 'tokens.ts'),
  join('styles', 'cssVars.ts'),
];

/**
 * Comments are not call sites.
 *
 * The burn-down headers name the literals they removed, and `Banner.tsx`
 * documents the amber palette it no longer hard-codes. Counting those would
 * make the burn-downs unreadable and would punish explaining a value, which is
 * the opposite of what is wanted.
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

export function walk(dir: string): string[] {
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
export const isTest = (path: string): boolean => /\.test\.tsx?$/.test(path);

export const relative = (path: string): string =>
  path.slice(SRC.length + 1).split(sep).join('/');

/** Every non-test source file that does not own design values. */
export const sources = walk(SRC).filter(
  (path) => !isTest(path) && !OWNS_THE_VALUES.some((owned) => path.endsWith(owned)),
);
