/**
 * F2 — no page restates the width of the fixed AuthBadge overlay.
 *
 * The badge is `position: fixed` in the top-right corner, so every page that
 * puts content up there has to reserve room for it. `AUTH_BADGE_RESERVE` exists
 * so that reservation is declared once, by the component that knows how wide it
 * actually is.
 *
 * It was restated anyway. `/canvas` and `/trainer` imported the constant; the
 * home page and `/docs` hard-coded `220` against a real reserve of 424, so the
 * badge sat over 192px of their navs — a shipped, visible defect, and the same
 * one already fixed on the other two routes. Two correct call sites did not
 * stop the number being retyped, which is why this is a walk over the routes
 * rather than a fix to two files.
 *
 * Written as a source walk, not a list of pages: a route added next sprint is
 * covered when it is created, not when someone remembers this file. The walk
 * asserts it found something first — a glob that matches nothing would make
 * every assertion below vacuous and report green.
 *
 * Mutation proof: restore `paddingRight: 220` at either call site and this test
 * fails and nothing else does.
 *
 * Limit, stated rather than implied: this bans a *numeric* `paddingRight` in
 * the route tree. It does not ban `'220px'` as a string, and it says nothing
 * about the other padding properties. The general ban on ad-hoc spacing is F1's
 * job in the token sweep; this is the guard for the one number that has already
 * been wrong twice.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { AUTH_BADGE_RESERVE, AUTH_BADGE_WIDTH } from './AuthBadge';

const APP_DIR = join(__dirname, '..', '..', 'app');

/** Every `.tsx` under the App Router tree, at any depth. */
function routeSources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return routeSources(path);
    return entry.name.endsWith('.tsx') ? [path] : [];
  });
}

describe('AuthBadge overlay reservation', () => {
  const sources = routeSources(APP_DIR);

  it('walks a route tree that actually has files in it', () => {
    // Precondition. Without this, a wrong APP_DIR makes the assertion below
    // pass over an empty list.
    expect(sources.length).toBeGreaterThan(3);
  });

  it('reserves more room than the badge occupies', () => {
    // The constant is the badge's own statement about itself; a reserve no
    // wider than the badge would leave it overlapping by construction.
    expect(AUTH_BADGE_RESERVE).toBeGreaterThan(AUTH_BADGE_WIDTH);
  });

  it('is never restated as a number by a page', () => {
    const offenders = sources.flatMap((path) => {
      const text = readFileSync(path, 'utf8');
      const hits = text.match(/paddingRight:\s*\d+/g) ?? [];
      return hits.map((hit) => `${path}: ${hit}`);
    });

    expect(offenders).toEqual([]);
  });
});
