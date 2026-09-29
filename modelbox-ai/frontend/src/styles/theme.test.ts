/**
 * F1 — the Tailwind theme is derived from the token module, not restated in it.
 *
 * The two files previously held the same six entity accents independently:
 * `theme.extend.colors.entity` in `tailwind.config.ts` and `ENTITY_ACCENT` in
 * `EntityNode.tsx`. Six hex values maintained in two places is the arrangement
 * that guarantees one of them is eventually wrong, and nothing would have
 * reported it — the canvas would simply have drawn a colour the config did not
 * know about.
 *
 * Asserting identity rather than equality of values: a copy that happens to
 * match today passes a value comparison and fails this.
 */

import { describe, expect, it } from 'vitest';

import config from '../../tailwind.config';
import { color, entityAccent, fontFamily, semantic } from './tokens';

describe('tailwind theme', () => {
  const colors = config.theme?.extend?.colors as Record<string, unknown>;

  it('takes its entity accents from the token module by reference', () => {
    expect(colors.entity).toBe(entityAccent);
  });

  it('takes its semantic roles from the token module by reference', () => {
    expect(colors.validated).toBe(semantic.validated);
    expect(colors.breaking).toBe(semantic.breaking);
    expect(colors.preview).toBe(semantic.preview);
  });

  it('takes its neutral ramp from the token module by reference', () => {
    expect(colors.neutral).toBe(color.neutral);
  });

  it('declares the brand typefaces', () => {
    const families = config.theme?.extend?.fontFamily as Record<string, string[]>;
    expect(families.sans).toEqual([fontFamily.sans]);
    expect(families.mono).toEqual([fontFamily.mono]);
    expect(fontFamily.sans).toContain('Inter');
    expect(fontFamily.mono).toContain('JetBrains Mono');
  });

  it('still scans the directories the components live in', () => {
    // Fixture sanity: a content glob that matches nothing makes every utility
    // class silently absent from the build, which looks like a styling bug
    // rather than a config one.
    expect(config.content).toContain('./src/app/**/*.{ts,tsx}');
    expect(config.content).toContain('./src/components/**/*.{ts,tsx}');
  });
});
