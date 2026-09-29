/**
 * F2 breadth — every route segment has somewhere to fail.
 *
 * Next.js uses an `error.tsx` if the segment has one and otherwise unmounts the
 * tree, so before this sprint the absence *was* the behaviour: a render-time
 * throw anywhere in the app left a blank page with the cause visible only in
 * the console. Fixing the seven that exist today is not the interesting part —
 * the eighth route is, and nobody adding it will remember.
 *
 * So the segments are discovered by walking `src/app` for `page.tsx`. A route
 * added tomorrow is covered on arrival, and a route deleted takes its
 * requirement with it. A written list of seven would do neither, and this
 * repository has shipped four tests that pinned a count and quietly stopped
 * covering what they named.
 *
 * **What this cannot say.** It checks the files exist and that each error
 * boundary routes through `RouteError`. It does not render them — Next.js owns
 * when a boundary is invoked, and that is not reproducible in jsdom. The
 * behaviour inside the boundary is `RouteError`'s, and it is tested there.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const APP = __dirname;

/** Every directory under `src/app` that renders a route. */
function routeSegments(dir: string = APP): string[] {
  const here = existsSync(join(dir, 'page.tsx')) ? [dir] : [];
  const below = readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .flatMap((entry) => routeSegments(join(dir, entry.name)));
  return [...here, ...below];
}

const segments = routeSegments();
const relative = (path: string): string => path.slice(APP.length) || '/';

describe('route boundaries', () => {
  it('found route segments to check', () => {
    // Precondition. A walk that returned nothing — a moved directory, a
    // `page.jsx`, an `app/` that became `src/pages/` — would iterate an empty
    // list and report green having checked no routes at all.
    expect(segments.length).toBeGreaterThan(3);
  });

  it.each(segments.map(relative))('%s has an error boundary', (segment) => {
    expect(existsSync(join(APP, segment === '/' ? '' : segment, 'error.tsx'))).toBe(
      true,
    );
  });

  it.each(segments.map(relative))('%s has a loading state', (segment) => {
    expect(
      existsSync(join(APP, segment === '/' ? '' : segment, 'loading.tsx')),
    ).toBe(true);
  });

  it('has a boundary for the root layout itself', () => {
    // `global-error.tsx` is the only boundary that can catch a throw in the
    // root layout: if the layout is what failed, there is no layout left for an
    // `error.tsx` to render inside.
    expect(existsSync(join(APP, 'global-error.tsx'))).toBe(true);
  });

  it('has a 404 of its own', () => {
    expect(existsSync(join(APP, 'not-found.tsx'))).toBe(true);
  });

  it('routes every error boundary through the shared one', () => {
    // Otherwise a segment can have an `error.tsx` that satisfies the existence
    // check above while rendering nothing, logging nothing and offering no way
    // back — which is a boundary in name only.
    //
    // `global-error.tsx` is exempt and must stay so: it cannot use `RouteError`
    // or `ui.css`, because a failure in the root layout is exactly the case
    // where the stylesheet may not have loaded.
    const boundaries = segments
      .map((dir) => join(dir, 'error.tsx'))
      .filter((path) => existsSync(path));

    expect(boundaries.length, 'no error boundaries found').toBeGreaterThan(3);

    const notUsingIt = boundaries.filter(
      (path) => !/RouteError/.test(readFileSync(path, 'utf-8')),
    );
    expect(notUsingIt.map(relative)).toEqual([]);
  });
});
