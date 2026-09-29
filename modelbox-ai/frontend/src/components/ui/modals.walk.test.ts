/**
 * F2 breadth — no file hand-rolls a dialog again.
 *
 * `Modal.test.tsx` proves the dialog properties hold for a `Modal`, and the
 * three per-site suites prove each existing modal is one. Neither can say
 * anything about the *next* modal someone writes, and the way this frontend
 * acquired three modals with no focus trap was not a decision — it was a
 * `position: fixed` div being the obvious thing to type.
 *
 * So the gate is a source walk, and it is turned on only now that all three
 * call sites are converted and the allowlist is therefore empty. A gate landed
 * earlier would have needed an allowlist that grew before it shrank, and an
 * allowlist with entries in it is a burn-down nobody reads.
 *
 * **What this does and does not catch.** It bans the *shape* — a full-viewport
 * fixed overlay — which is what every one of the three modals was built from.
 * It cannot catch a dialog built some other way: `position: absolute` inside a
 * full-height wrapper, a `<dialog>` element, or an overlay whose `inset` is
 * spelled as four separate properties. It is a tripwire on the path people
 * actually take, not a proof that no dialog can be hand-rolled.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = join(__dirname, '..', '..');

/**
 * The one file allowed to own an overlay. Everything else reaches it through
 * `ui/Modal`, which is what makes the focus trap and Escape unforgettable.
 */
const OWNS_THE_OVERLAY = join('styles', 'ui.css');

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return walk(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

describe('the frontend has one way to build a dialog', () => {
  const sources = walk(SRC);

  it('found sources to check', () => {
    // Precondition. A walk that returned nothing — a renamed directory, a
    // changed extension — would iterate an empty list and report green having
    // read no files at all. This repository has shipped that shape four times.
    expect(sources.length).toBeGreaterThan(20);
  });

  it('has the file it is checking for a rewrite of', () => {
    // The second precondition: the test is only meaningful while `ui/Modal`
    // exists to be the alternative. If it were deleted, every assertion below
    // would still pass on a codebase with no dialog implementation at all.
    expect(sources.some((p) => p.endsWith(join('components', 'ui', 'Modal.tsx')))).toBe(
      true,
    );
  });

  it('builds no full-viewport overlay outside the stylesheet', () => {
    // Mutation, 2026-08-31: restoring the `overlay` constant deleted from
    // `TemplateLibraryModal` fails this and nothing else.
    const offenders = sources.filter((path) => {
      if (path.endsWith(OWNS_THE_OVERLAY)) return false;
      const text = readFileSync(path, 'utf-8');
      // Both halves together: `position: fixed` alone is legitimate — the auth
      // badge is a fixed overlay that is not a dialog — and it is the pairing
      // with a full-viewport `inset` that makes it a scrim.
      return /position:\s*'fixed'/.test(text) && /inset:\s*0/.test(text);
    });

    expect(offenders.map((p) => p.slice(SRC.length + 1))).toEqual([]);
  });

  it('routes every modal component through the primitive', () => {
    // Discovered by filename rather than listed: a fourth `*Modal.tsx` is
    // covered the day it is added, which a list of three would not be.
    const modals = sources.filter(
      (path) => /Modal\.tsx$/.test(path) && !/ui[\\/]Modal\.tsx$/.test(path),
    );

    expect(modals.length, 'no modal components found').toBeGreaterThan(0);

    const notUsingIt = modals.filter((path) => {
      const text = readFileSync(path, 'utf-8');
      // Both the import and the element: a file that imports the barrel for
      // `Button` and still renders its own overlay would satisfy either half
      // alone.
      //
      // The barrel and the direct path are both accepted. The house convention
      // is the barrel, but a direct import still routes through the primitive,
      // and a gate that failed it would be enforcing something other than what
      // this test is named for.
      return (
        !/from '@\/components\/ui(\/Modal)?'/.test(text) ||
        !/<Modal[\s>]/.test(text)
      );
    });
    expect(notUsingIt.map((p) => p.slice(SRC.length + 1))).toEqual([]);
  });
});
