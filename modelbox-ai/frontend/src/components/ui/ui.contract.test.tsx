/**
 * Properties every primitive must hold, checked over whatever the barrel
 * exports rather than over a written list.
 *
 * A list in a test file is a list someone has to remember to extend, and this
 * codebase has already been bitten four times by tests that pinned a count or
 * enumerated their own fixtures and then silently stopped covering what they
 * named. So the components are discovered from `index.ts`, and the fixture map
 * is asserted to match that set exactly — adding a primitive without a fixture
 * fails here, and so does removing one from the barrel while a fixture remains.
 */

import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ReactElement } from 'react';

import * as UI from './index';

/**
 * Minimal renderable props per primitive. Kept minimal on purpose: these check
 * the component stands up at all, not what it does — the behaviour each one
 * exists for is asserted in its own file.
 */
const FIXTURES: Record<string, ReactElement> = {
  Badge: <UI.Badge>certified</UI.Badge>,
  Banner: <UI.Banner tone="preview">Preview dialect.</UI.Banner>,
  Button: <UI.Button>Save</UI.Button>,
  CloseButton: <UI.CloseButton />,
  Field: (
    <UI.Field label="Workspace">
      <UI.Input />
    </UI.Field>
  ),
  Input: <UI.Input aria-label="input" />,
  Select: <UI.Select aria-label="select" />,
  StatusText: <UI.StatusText>Saved.</UI.StatusText>,
  Textarea: <UI.Textarea aria-label="textarea" />,
};

/** Exported components, by the convention that a component is capitalised. */
function exportedComponents(): string[] {
  return Object.entries(UI)
    .filter(([name, value]) => typeof value === 'function' && /^[A-Z]/.test(name))
    .map(([name]) => name)
    .sort();
}

describe('the ui barrel', () => {
  it('exports components', () => {
    // Precondition. An empty barrel would make every assertion below iterate
    // nothing and pass, which is the exact shape of a gate that verifies
    // nothing while reporting green.
    expect(exportedComponents().length).toBeGreaterThan(5);
  });

  it('has a fixture for every component it exports, and no others', () => {
    expect(Object.keys(FIXTURES).sort()).toEqual(exportedComponents());
  });

  it.each(Object.keys(FIXTURES))('%s renders and is styled by the layer', (name) => {
    const fixture = FIXTURES[name];
    expect(fixture).toBeDefined();

    const { container } = render(fixture as ReactElement);
    const root = container.firstElementChild;

    expect(root, `${name} rendered nothing`).not.toBeNull();
    // Every primitive takes its shape from `ui.css`. A root with no `mb-` class
    // is a component that fell back to inline styles and therefore has no
    // hover, focus-visible or disabled state — the defect this layer exists to
    // fix, reintroduced.
    expect(
      [...(root?.classList ?? [])].some((c) => c.startsWith('mb-')),
      `${name} root carries no mb- class`,
    ).toBe(true);
  });

  it.each(Object.keys(FIXTURES))('%s sets no inline padding or radius', (name) => {
    // During adoption an inline style beats the stylesheet. That is deliberate
    // — it is how a half-converted call site keeps its existing look — but it
    // means the primitives themselves must stay silent, or the class could
    // never win. Colour is exempt: `Badge`, `Banner` and `StatusText` compute a
    // tone against a ground, which is their whole purpose.
    const { container } = render(FIXTURES[name] as ReactElement);
    const root = container.firstElementChild as HTMLElement;

    expect(root.style.padding, `${name} padding`).toBe('');
    expect(root.style.borderRadius, `${name} borderRadius`).toBe('');
    expect(root.style.fontSize, `${name} fontSize`).toBe('');
  });
});
