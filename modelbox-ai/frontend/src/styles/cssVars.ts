/**
 * The token module, projected into CSS custom properties.
 *
 * **Why this file exists at all.** Hover, focus-visible and disabled cannot be
 * expressed in an inline `style` object, and the frontend is 100% inline
 * styles — which is exactly why it has zero focus declarations today. Those
 * states have to live in a stylesheet. But CSS cannot import TypeScript, so a
 * hand-written stylesheet would restate `#2563EB` and `6px` as literals: a
 * second source of truth for precisely the values `tokens.test.ts` and
 * `theme.test.ts` exist to keep single.
 *
 * So the stylesheet reads `var(--mb-…)` and nothing else, and this function
 * derives those variables from `tokens.ts`. `ui.css.test.ts` asserts every
 * variable the stylesheet references is one this function emits — a typo'd var
 * name otherwise renders an unstyled element with no error anywhere.
 *
 * **Component padding is composed here, not tokenised.** Padding is compound
 * (`6px 12px`) and belongs to a component and a size, not to a call site; the
 * frontend spells it 48 different ways across 141 uses today. Exposing a
 * padding token would let each call site keep inventing one.
 */

import {
  color,
  entityAccent,
  focusRing,
  fontFamily,
  radius,
  semantic,
  space,
  surface,
  type,
} from './tokens';

/**
 * `bodySmall` → `body-small`, `uiXSmall` → `ui-x-small`.
 *
 * Two passes, because one is not enough: splitting only on a lowercase→
 * uppercase boundary leaves `uiXSmall` as `ui-xsmall`, running the single-letter
 * `X` into the word after it. Exported so the tests can check a name without
 * reimplementing this rule and agreeing with a bug.
 */
export function tokenNameToCssName(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
    .toLowerCase();
}

const kebab = tokenNameToCssName;

/**
 * Every CSS custom property the stylesheet may reference, derived.
 *
 * Returned rather than written to a constant so the test can compare against a
 * fresh derivation; a frozen literal that happened to match today would pass a
 * value comparison while no longer being derived from anything.
 */
export function tokensToCssVariables(): Record<string, string> {
  const vars: Record<string, string> = {};

  // --- palette -------------------------------------------------------------
  vars['--mb-color-navy'] = color.navy;
  vars['--mb-color-blue'] = color.blue;
  vars['--mb-color-cyan'] = color.cyan;
  vars['--mb-color-white'] = color.white;
  for (const [step, value] of Object.entries(color.neutral)) {
    vars[`--mb-color-neutral-${step}`] = value;
  }

  // --- grounds -------------------------------------------------------------
  for (const [name, value] of Object.entries(surface)) {
    vars[`--mb-surface-${kebab(name)}`] = value;
  }

  // Status colour is reached through the ground it sits on, never on its own —
  // the on-dark values measure 2.15:1 to 2.54:1 on white and are invisible as
  // text there. The variable names carry the ground for the same reason the
  // TypeScript API does.
  for (const [role, grounds] of Object.entries(semantic)) {
    vars[`--mb-${kebab(role)}-on-light`] = grounds.onLight;
    vars[`--mb-${kebab(role)}-on-dark`] = grounds.onDark;
  }

  for (const [entity, accent] of Object.entries(entityAccent)) {
    vars[`--mb-entity-${kebab(entity)}`] = accent;
  }

  // --- type ----------------------------------------------------------------
  vars['--mb-font-sans'] = fontFamily.sans;
  vars['--mb-font-mono'] = fontFamily.mono;
  for (const [name, scale] of Object.entries(type)) {
    const prefix = `--mb-type-${kebab(name)}`;
    vars[`${prefix}-size`] = scale.size;
    vars[`${prefix}-weight`] = String(scale.weight);
    vars[`${prefix}-line-height`] = String(scale.lineHeight);
    vars[`${prefix}-tracking`] = scale.tracking;
  }

  // --- metrics -------------------------------------------------------------
  for (const [step, value] of Object.entries(space)) {
    vars[`--mb-space-${step}`] = `${value}px`;
  }
  for (const [step, value] of Object.entries(radius)) {
    vars[`--mb-radius-${step}`] = `${value}px`;
  }

  vars['--mb-focus-outline'] = focusRing.outline;
  vars['--mb-focus-offset'] = focusRing.outlineOffset;

  // --- component metrics ---------------------------------------------------
  // These are the shapes the frontend ships today: `6px 12px` on the compact
  // buttons, `8px 14px` on the settings-page buttons, `8px 10px` on every
  // field. They are written literally rather than composed from `space`
  // because 6px, 14px and 10px are not steps in that ramp — rounding them onto
  // it would grow every button by 4px, which is a visual change this layer
  // exists to avoid. Three declarations here replace 19 spellings at call
  // sites; that is the win, not arithmetic purity.
  vars['--mb-btn-pad-sm'] = '6px 12px';
  vars['--mb-btn-pad-md'] = '8px 14px';
  vars['--mb-field-pad'] = '8px 10px';
  vars['--mb-panel-pad'] = `${space.lg}px`;
  vars['--mb-modal-head-pad'] = '16px 20px';
  vars['--mb-modal-pad'] = '20px';

  /*
   * The dialog scrim. The three modals spelled it two ways — `rgba(15, 23,
   * 42, 0.55)` and `#0f172a99` (0.6) — both Tailwind's slate-900 rather than
   * the brand navy, and at two different alphas nobody chose. Derived here so
   * the scrim is one colour and it is the brand's.
   *
   * `8C` is 0.55 in eighths of a byte; the stronger of the two alphas is the
   * one dropped, because the scrim sits under content that must stay legible.
   */
  vars['--mb-scrim'] = `${color.navy}8C`;

  // Not a design token and not pretending to be one: the elevation shadow is a
  // single shape used by a single component. It lives here rather than in
  // `ui.css` only so the stylesheet keeps its rule that every value it states
  // is a variable — one place to look, whether or not the value is a token.
  vars['--mb-shadow-modal'] = '0 20px 60px rgba(0, 0, 0, 0.3)';

  return vars;
}

/** The `:root` block, ready to be emitted into the document. */
export function cssVariableBlock(): string {
  const declarations = Object.entries(tokensToCssVariables())
    .map(([name, value]) => `  ${name}: ${value};`)
    .join('\n');
  return `:root {\n${declarations}\n}`;
}
