/**
 * F2 — the stylesheet resolves, and every interactive class shows a focus ring.
 *
 * Two failures this catches, both of which are invisible at runtime:
 *
 * 1. **A typo'd variable name.** `var(--mb-color-blu)` is not an error in CSS.
 *    The declaration is simply dropped and the element renders unstyled, which
 *    looks like a layout bug somewhere else entirely. Nothing else in the
 *    toolchain checks this: TypeScript never sees the stylesheet, and the
 *    stylesheet never sees TypeScript.
 *
 * 2. **A missing focus ring.** This frontend shipped with *zero* `:focus`,
 *    `:focus-visible` or `outline` declarations, so keyboard users navigated on
 *    the user-agent default or on nothing. Fixing it once is not enough — the
 *    next primitive added has to be covered on arrival, so the check discovers
 *    the interactive classes by parsing the stylesheet rather than listing
 *    them here.
 *
 * Both tests assert what they discovered is non-empty first: a regex that
 * matches nothing would otherwise iterate an empty list and report green,
 * having verified nothing at all.
 *
 * jsdom limit, stated rather than implied: this proves the *rule exists and
 * names the token*. jsdom does not match `:focus-visible` in
 * `getComputedStyle`, so nothing here proves a ring is painted. That claim
 * rests on the manual pass over the routes, and must not be read off this file.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { tokensToCssVariables } from './cssVars';

const css = readFileSync(join(__dirname, 'ui.css'), 'utf-8');

/** Selectors carrying a bare class with no pseudo-class or attribute on it. */
function baseClasses(): string[] {
  const found = new Set<string>();
  for (const match of css.matchAll(/^\.(mb-[a-z-]+)\s*(?:,|\{)/gm)) {
    if (match[1]) found.add(match[1]);
  }
  return [...found];
}

describe('ui.css', () => {
  it('references only variables the token module emits', () => {
    const emitted = new Set(Object.keys(tokensToCssVariables()));
    const referenced = [...css.matchAll(/var\((--mb-[a-z0-9-]+)\)/g)].map(
      (m) => m[1],
    );

    expect(referenced.length, 'no variable references found').toBeGreaterThan(20);

    const undeclared = [...new Set(referenced)].filter(
      (name) => name && !emitted.has(name),
    );
    expect(undeclared).toEqual([]);
  });

  it('states its colours, type and metrics as variables, never as literals', () => {
    // The reason the indirection exists. A hex or a `px` radius written here
    // would be a second source of truth for a value `tokens.ts` already owns,
    // and no other test could see it.
    //
    // Declarations are checked, not the comment block: the header explains the
    // rule and legitimately contains hex-like prose.
    const body = css.replace(/\/\*[\s\S]*?\*\//g, '');
    expect(body).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(body).not.toMatch(/border-radius:\s*\d/);
    expect(body).not.toMatch(/font-size:\s*\d/);
  });

  it('gives every interactive class a focus ring drawn from the token', () => {
    // Mutation, 2026-08-31: deleting the `.mb-btn:focus-visible` block fails
    // this test and nothing else in the suite.
    const interactive = baseClasses().filter((c) =>
      ['mb-btn', 'mb-control'].some((prefix) => c === prefix),
    );
    expect(interactive.length, 'no interactive base classes found').toBeGreaterThan(
      0,
    );

    for (const cls of interactive) {
      const rule = new RegExp(
        `\\.${cls}:focus-visible\\s*\\{[^}]*outline:\\s*var\\(--mb-focus-outline\\)`,
      );
      expect(rule.test(css), `${cls} has no focus-visible outline`).toBe(true);
    }
  });

  it('never lights a disabled control up on hover', () => {
    // A disabled control that responds to hover reads as interactive when it is
    // not. Every hover rule has to exclude the disabled state, and this is a
    // property of the file rather than of one class, so it is checked over all
    // of them.
    const hoverRules = [...css.matchAll(/^\.(mb-[a-z-]+[^\s{,]*):hover([^\s{,]*)/gm)];
    expect(hoverRules.length, 'no hover rules found').toBeGreaterThan(0);

    for (const rule of hoverRules) {
      expect(rule[2], `${rule[1]}:hover is not scoped away from :disabled`).toBe(
        ':not(:disabled)',
      );
    }
  });
});
