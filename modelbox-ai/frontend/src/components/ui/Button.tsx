'use client';

/**
 * The button.
 *
 * Replaces 14 named style constants and roughly 58 inline button styles, which
 * between them spelled padding 19 ways, radius 3 ways and "this toggle is
 * active" 4 ways. `primaryBtn` was byte-identical in three files and
 * `dangerBtn` in two.
 *
 * What it adds beyond deduplication is the part that could not be written
 * before: hover, focus-visible and disabled live in `ui.css`, because an inline
 * style cannot express a pseudo-class. Every button in the app was previously
 * unfocusable-looking for keyboard users.
 */

import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

interface ButtonBase extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /**
   * Accent colour. Applied as a CSS variable rather than as an inline
   * background so the hover and focus rules keep applying — an inline
   * background would win over the stylesheet and take the hover state with it.
   */
  tone?: string;
  /** A toggle that is currently on. Renders `aria-pressed`, so it is announced. */
  pressed?: boolean;
  /** Work in flight: disables the control and marks it `aria-busy`. */
  loading?: boolean;
  /**
   * Defaults to `button`. The HTML default is `submit`, which makes any button
   * inside a form submit it — a live footgun rather than a style choice.
   */
  type?: 'button' | 'submit' | 'reset';
  children?: ReactNode;
}

/**
 * An icon-only button must carry an accessible name. Three of the seven close
 * buttons in the app had none, so screen readers announced "button". The
 * discriminated union makes that a compile error rather than a review comment.
 */
type ButtonProps =
  | (ButtonBase & { iconOnly: true; 'aria-label': string })
  | (ButtonBase & { iconOnly?: false });

export default function Button({
  variant = 'secondary',
  size = 'md',
  tone,
  pressed,
  loading = false,
  iconOnly = false,
  type = 'button',
  className,
  style,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    'mb-btn',
    `mb-btn--${variant}`,
    size === 'sm' ? 'mb-btn--sm' : null,
    iconOnly ? 'mb-btn--icon' : null,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      {...rest}
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      aria-pressed={pressed}
      data-pressed={pressed ? 'true' : undefined}
      style={
        tone ? ({ ...style, '--mb-btn-tone': tone } as CSSProperties) : style
      }
    >
      {children}
    </button>
  );
}
