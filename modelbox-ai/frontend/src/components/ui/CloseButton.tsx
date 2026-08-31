'use client';

/**
 * The dismiss button on modals, panels and popovers.
 *
 * Not a different style from `Button` — a different *default*. Five `closeBtn`
 * constants existed, differing only in `fontSize` (18, 18, 15, 15, 16), and
 * three of the seven close buttons in the app had no accessible name at all, so
 * a screen reader announced "button" with no indication of what it did.
 *
 * The label is defaulted rather than required so that forgetting it produces a
 * correct control instead of an unlabelled one.
 */

import type { ComponentProps } from 'react';

import Button from './Button';

type CloseButtonProps = Omit<
  ComponentProps<typeof Button>,
  'iconOnly' | 'children' | 'variant'
> & {
  label?: string;
};

export default function CloseButton({
  label = 'Close',
  ...rest
}: CloseButtonProps) {
  return (
    <Button {...rest} variant="ghost" iconOnly aria-label={label}>
      {/* The glyph is decorative: the accessible name comes from aria-label,
          and leaving this readable would announce the character too. */}
      <span aria-hidden="true">✕</span>
    </Button>
  );
}
