/**
 * F6 on component output rather than on the palette.
 *
 * `tokens.test.ts` proves the declared pairs meet their floors. That is a
 * statement about the token table; it says nothing about what a component
 * actually renders. `Badge` composes a translucent tint from its own
 * foreground, so the background it produces is not in `PAIRS` at all — it is
 * computed at render time, and it is the thing a user reads text against.
 *
 * So the tint is composited over the surface here and the ratio recomputed,
 * parameterised over every tone × ground × variant. A tone added to the union
 * without a readable pair on some ground fails on arrival.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CONTRAST_FLOOR, color, contrastRatio, surface } from '@/styles/tokens';

import Badge, { toneColor, toneTint } from './Badge';
import type { BadgeTone, BadgeVariant, Ground } from './Badge';

const TONES: BadgeTone[] = [
  'neutral',
  'validated',
  'breaking',
  'preview',
  'accent',
];
const GROUNDS: Ground[] = ['light', 'dark'];
const VARIANTS: BadgeVariant[] = ['tint', 'outline', 'solid'];

/** The page colour a badge of this ground sits on. */
const groundColor = (on: Ground): string =>
  on === 'dark' ? surface.dark : surface.card;

/**
 * Composite `#RRGGBBAA` over an opaque background.
 *
 * Without this the test would measure the badge's text against the *page*
 * rather than against the tint it actually sits on, and would pass on a tint
 * strong enough to swallow its own label.
 */
function composite(rgba: string, bg: string): string {
  const hex = rgba.replace('#', '');
  const alpha = parseInt(hex.slice(6, 8), 16) / 255;
  const base = bg.replace('#', '');

  const channel = (i: number): string => {
    const fg = parseInt(hex.slice(i, i + 2), 16);
    const under = parseInt(base.slice(i, i + 2), 16);
    return Math.round(fg * alpha + under * (1 - alpha))
      .toString(16)
      .padStart(2, '0');
  };

  return `#${channel(0)}${channel(2)}${channel(4)}`;
}

describe('Badge contrast', () => {
  it('has combinations to check', () => {
    expect(TONES.length * GROUNDS.length * VARIANTS.length).toBeGreaterThan(10);
  });

  const cases = TONES.flatMap((tone) =>
    GROUNDS.flatMap((on) => VARIANTS.map((variant) => ({ tone, on, variant }))),
  );

  it.each(cases)('$variant $tone on $on is readable', ({ tone, on, variant }) => {
    const fg = toneColor(tone, on);
    const ground = groundColor(on);

    const [text, background] =
      variant === 'solid'
        ? [on === 'dark' ? color.navy : color.white, fg]
        : variant === 'outline'
          ? [fg, ground]
          : [fg, composite(toneTint(tone, on), ground)];

    // Badge text is small, so it is held to the body floor, not the large one.
    expect(contrastRatio(text, background)).toBeGreaterThanOrEqual(
      CONTRAST_FLOOR.body,
    );
  });

  it('composites a tint rather than measuring against the bare page', () => {
    // Fixture sanity for the maths above. A `composite` that ignored alpha
    // would return the foreground and make every tint case a 1:1 comparison
    // against itself — which would fail loudly — but one that returned the
    // background unchanged would silently make the tint cases identical to the
    // outline cases and prove nothing about the tint at all.
    const tint = composite(toneTint('breaking', 'light'), surface.card);
    expect(tint).not.toBe(surface.card);
    expect(tint.toUpperCase()).not.toBe(toneColor('breaking', 'light'));
  });
});

describe('Badge', () => {
  it('reaches a colour only through the ground it sits on', () => {
    // The API rule from the token module, restated at the component boundary:
    // the on-dark values measure under 2.6:1 on white. Same tone, two grounds,
    // two different colours — if they ever agree, one of them is unreadable.
    for (const tone of TONES) {
      expect(toneColor(tone, 'light')).not.toBe(toneColor(tone, 'dark'));
    }
  });

  it('renders its content', () => {
    render(<Badge tone="validated">CERTIFIED</Badge>);
    expect(screen.getByText('CERTIFIED')).toBeInTheDocument();
  });
});
