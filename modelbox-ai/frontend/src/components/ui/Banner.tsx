'use client';

/**
 * A block-level status message.
 *
 * The amber warning palette — `#fffbeb` ground, `#fde68a` border, `#92400e`
 * text — appears four times in the app, written out independently each time,
 * and **none of those three values is in the token ramp.** They are the only
 * reason this component exists as well as `Badge`: four copies of a colour
 * scheme nothing owns.
 *
 * `role` is derived from the tone rather than passed in. A breaking message is
 * an alert; everything else is a status. Deriving it means the 3 error sites in
 * the app that currently render no role at all are fixed by adoption, not by
 * someone remembering at each one.
 */

import type { ReactNode } from 'react';

import { color } from '@/styles/tokens';

import type { BadgeTone, Ground } from './Badge';
import { toneColor, toneTint } from './Badge';

interface BannerProps {
  tone?: BadgeTone;
  on?: Ground;
  title?: ReactNode;
  children: ReactNode;
}

export default function Banner({
  tone = 'neutral',
  on = 'light',
  title,
  children,
}: BannerProps) {
  const fg = toneColor(tone, on);

  return (
    <div
      className="mb-banner"
      role={tone === 'breaking' ? 'alert' : 'status'}
      style={{
        background: toneTint(tone, on),
        borderColor: fg,
        color: on === 'dark' ? color.neutral[100] : color.neutral[800],
      }}
    >
      <div>
        {title ? (
          <strong style={{ color: fg, display: 'block' }}>{title}</strong>
        ) : null}
        {children}
      </div>
    </div>
  );
}
