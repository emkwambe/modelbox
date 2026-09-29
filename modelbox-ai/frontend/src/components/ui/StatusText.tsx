'use client';

/**
 * An inline status or error line.
 *
 * Around 24 of these are written inline across the app with no shared constant
 * at all, and **`role="alert"` appears on only 5 of the 8 error sites** — so
 * three failures are shown on screen and announced to nobody.
 *
 * The role and the live region are derived from the tone rather than passed in,
 * which is what makes adoption fix those three sites. A prop the caller can
 * pass is a prop the caller can forget, and the evidence that it gets forgotten
 * is the 5-of-8.
 */

import type { ReactNode } from 'react';

import type { BadgeTone, Ground } from './Badge';
import { toneColor } from './Badge';

interface StatusTextProps {
  tone?: BadgeTone;
  on?: Ground;
  children: ReactNode;
}

export default function StatusText({
  tone = 'neutral',
  on = 'light',
  children,
}: StatusTextProps) {
  const isError = tone === 'breaking';

  return (
    <p
      className="mb-status"
      role={isError ? 'alert' : 'status'}
      // Errors interrupt; progress and success do not. Both are announced.
      aria-live={isError ? 'assertive' : 'polite'}
      style={tone === 'neutral' ? undefined : { color: toneColor(tone, on) }}
    >
      {children}
    </p>
  );
}
