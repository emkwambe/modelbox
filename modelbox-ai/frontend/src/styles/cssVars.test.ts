/**
 * F1 — the CSS variables are derived from the token module, not restated.
 *
 * Same shape as `theme.test.ts`, and for the same reason: a hand-written copy
 * that happens to match today passes a value comparison and only diverges once
 * someone edits one of the two. These assertions read the value out of
 * `tokens.ts` and compare, so there is no literal here to keep in step either.
 *
 * Mutation, 2026-08-31: hardcoding `'#2563EB'` for `--mb-color-blue` in
 * `cssVars.ts` — the value it currently produces — fails the identity
 * assertions below and nothing else, because they compare against the imported
 * token rather than against a written-out hex.
 */

import { describe, expect, it } from 'vitest';

import {
  cssVariableBlock,
  tokenNameToCssName,
  tokensToCssVariables,
} from './cssVars';
import {
  color,
  focusRing,
  fontFamily,
  radius,
  semantic,
  space,
  surface,
  type,
} from './tokens';

describe('css variables', () => {
  const vars = tokensToCssVariables();

  it('emits something', () => {
    // Precondition. An empty map would satisfy every "each emitted var is
    // well-formed" assertion below by having nothing to check.
    expect(Object.keys(vars).length).toBeGreaterThan(40);
  });

  it('namespaces every variable it emits', () => {
    // A variable outside the `--mb-` namespace could collide with Tailwind's
    // preflight or with `globals.css`, and the stylesheet test discovers
    // references by that prefix — an unprefixed one would be invisible to it.
    for (const name of Object.keys(vars)) {
      expect(name).toMatch(/^--mb-[a-z0-9-]+$/);
    }
  });

  it('takes its palette from the token module', () => {
    expect(vars['--mb-color-blue']).toBe(color.blue);
    expect(vars['--mb-color-navy']).toBe(color.navy);
    expect(vars['--mb-color-neutral-300']).toBe(color.neutral[300]);
    expect(vars['--mb-surface-page']).toBe(surface.page);
    expect(vars['--mb-surface-dark']).toBe(surface.dark);
  });

  it('carries the ground in the name of every semantic variable', () => {
    // The API rule the token module exists to enforce: a status colour is only
    // reachable through the surface it sits on, because the on-dark values
    // measure under 2.6:1 on white and are invisible as text there. A bare
    // `--mb-breaking` would make the unreadable combination reachable again.
    for (const [role, grounds] of Object.entries(semantic)) {
      expect(vars[`--mb-${role}-on-light`]).toBe(grounds.onLight);
      expect(vars[`--mb-${role}-on-dark`]).toBe(grounds.onDark);
      expect(vars[`--mb-${role}`]).toBeUndefined();
    }
  });

  it('names a multi-word token the way the stylesheet spells it', () => {
    // Written out rather than derived. Reusing `tokenNameToCssName` to build
    // the expectation would make this agree with whatever the function does,
    // including the bug it had: `uiXSmall` first came out as `ui-xsmall`,
    // running the single-letter `X` into the word after it, and the stylesheet
    // referenced a variable that was never emitted. In CSS that is not an
    // error — the declaration is dropped and the element renders unstyled.
    expect(tokenNameToCssName('uiXSmall')).toBe('ui-x-small');
    expect(tokenNameToCssName('bodySmall')).toBe('body-small');
    expect(tokenNameToCssName('body')).toBe('body');
    expect(vars['--mb-type-ui-x-small-size']).toBe(type.uiXSmall.size);
    expect(vars['--mb-type-body-small-size']).toBe(type.bodySmall.size);
  });

  it('emits four properties for every step of the type ramp', () => {
    for (const [name, scale] of Object.entries(type)) {
      const prefix = `--mb-type-${tokenNameToCssName(name)}`;
      expect(vars[`${prefix}-size`], `${name} size`).toBe(scale.size);
      expect(vars[`${prefix}-weight`]).toBe(String(scale.weight));
      expect(vars[`${prefix}-line-height`]).toBe(String(scale.lineHeight));
      expect(vars[`${prefix}-tracking`]).toBe(scale.tracking);
    }
  });

  it('emits every spacing and radius step with a unit', () => {
    // A unitless `12` is invalid in `padding` and silently drops the
    // declaration; the ramps are numbers in TypeScript and must not reach CSS
    // that way.
    for (const [step, value] of Object.entries(space)) {
      expect(vars[`--mb-space-${step}`]).toBe(`${value}px`);
    }
    for (const [step, value] of Object.entries(radius)) {
      expect(vars[`--mb-radius-${step}`]).toBe(`${value}px`);
    }
  });

  it('takes the focus ring from the token module', () => {
    expect(vars['--mb-focus-outline']).toBe(focusRing.outline);
    expect(vars['--mb-focus-offset']).toBe(focusRing.outlineOffset);
  });

  it('declares the typefaces', () => {
    expect(vars['--mb-font-sans']).toBe(fontFamily.sans);
    expect(vars['--mb-font-mono']).toBe(fontFamily.mono);
  });

  it('declares a component padding for each shape the frontend ships', () => {
    // Deliberately literal, and asserted as such: these are the shapes in use
    // today (`6px 12px`, `8px 14px`, `8px 10px`) rather than steps of the
    // spacing ramp, because rounding them onto it would grow every button by
    // 4px. Compare with the ramp instead and this test would be endorsing that
    // change rather than catching it.
    expect(vars['--mb-btn-pad-sm']).toBe('6px 12px');
    expect(vars['--mb-btn-pad-md']).toBe('8px 14px');
    expect(vars['--mb-field-pad']).toBe('8px 10px');
    expect(vars['--mb-panel-pad']).toBe(`${space.lg}px`);
  });
});

describe('the :root block', () => {
  it('renders every variable as a declaration', () => {
    const block = cssVariableBlock();
    const vars = tokensToCssVariables();

    expect(Object.keys(vars).length).toBeGreaterThan(0);
    for (const [name, value] of Object.entries(vars)) {
      expect(block).toContain(`${name}: ${value};`);
    }
    expect(block.startsWith(':root {')).toBe(true);
    expect(block.trimEnd().endsWith('}')).toBe(true);
  });
});
