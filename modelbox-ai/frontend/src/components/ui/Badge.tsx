'use client';

/**
 * A status pill.
 *
 * Eleven badge declarations existed across the app in three real shapes. `chip`
 * and `difficultyBadge` were identical but for `fontWeight`; the egress page had
 * its own local `Pill`.
 *
 * **The `on` axis is the point.** `ExportPanel`'s `statusBanner(status)` was
 * already the best-written style function in the codebase — token-backed and
 * aware of the ground it sits on — and this generalises it rather than
 * replacing it. A status colour is only reachable through its surface because
 * the on-dark values measure 2.15:1 to 2.54:1 on white: picking the wrong one
 * is not a style slip, it is an unreadable status message.
 */

import type { ReactNode } from 'react';

import { color, semantic } from '@/styles/tokens';

export type BadgeVariant = 'tint' | 'outline' | 'solid';
export type BadgeTone =
  | 'neutral'
  | 'validated'
  | 'breaking'
  | 'preview'
  | 'accent';
export type Ground = 'light' | 'dark';

interface BadgeProps {
  variant?: BadgeVariant;
  tone?: BadgeTone;
  on?: Ground;
  children: ReactNode;
  title?: string;
}

/** The foreground for a tone on a ground. Never a colour without its ground. */
export function toneColor(tone: BadgeTone, on: Ground): string {
  if (tone === 'neutral') {
    return on === 'dark' ? color.neutral[300] : color.neutral[600];
  }
  if (tone === 'accent') {
    return on === 'dark' ? color.cyan : color.blue;
  }
  return on === 'dark' ? semantic[tone].onDark : semantic[tone].onLight;
}

/**
 * The tint behind a tone. Expressed as the foreground at low alpha rather than
 * as a second palette, so a tone can never drift from its own background.
 *
 * **The alpha is a contrast decision, not a taste one.** A tint darkens the
 * ground the label is read against, so it spends contrast the foreground has
 * already only just earned. At the 10%/18% that looked right, `Badge.test.tsx`
 * measured breaking-on-dark at 4.18:1, preview-on-light at 4.35:1 and
 * accent-on-light at 4.49:1 — all under the 4.5:1 floor, and the last of them
 * under by 0.01. These values are the strongest tint that clears it; raising
 * them is a WCAG regression the badge contrast test will catch.
 */
export function toneTint(tone: BadgeTone, on: Ground): string {
  return `${toneColor(tone, on)}${on === 'dark' ? '17' : '0D'}`;
}

export default function Badge({
  variant = 'tint',
  tone = 'neutral',
  on = 'light',
  children,
  title,
}: BadgeProps) {
  const fg = toneColor(tone, on);

  const style =
    variant === 'solid'
      ? { background: fg, color: on === 'dark' ? color.navy : color.white }
      : variant === 'outline'
        ? { background: 'transparent', color: fg, borderColor: fg }
        : { background: toneTint(tone, on), color: fg };

  return (
    <span className="mb-badge" style={style} title={title}>
      {children}
    </span>
  );
}
