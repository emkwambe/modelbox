/**
 * StatusText and Banner — the announcement, which is what was missing.
 *
 * `role="alert"` is on 5 of the 8 error sites in this app. The other three
 * display a failure and tell nobody. Both components derive the role from the
 * tone instead of taking it as a prop, so adopting them fixes those three
 * rather than relying on whoever converts the file to notice.
 *
 * Mutation: making `role` a passthrough prop on either component — the obvious
 * "more flexible" API — fails every assertion below that names a role, and
 * nothing else.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Banner from './Banner';
import StatusText from './StatusText';
import type { BadgeTone } from './Badge';

const NON_ERROR: BadgeTone[] = ['neutral', 'validated', 'preview', 'accent'];

describe('StatusText', () => {
  it('announces an error assertively', () => {
    render(<StatusText tone="breaking">Save failed.</StatusText>);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Save failed.');
    expect(alert).toHaveAttribute('aria-live', 'assertive');
  });

  it('has non-error tones to check', () => {
    expect(NON_ERROR.length).toBeGreaterThan(1);
  });

  it.each(NON_ERROR)('announces %s politely, not as an alert', (tone) => {
    // An interruption for every progress message is its own accessibility
    // defect; the distinction has to survive.
    render(<StatusText tone={tone}>Synthesizing…</StatusText>);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('Banner', () => {
  it('announces a breaking banner as an alert', () => {
    render(<Banner tone="breaking">The backend is unreachable.</Banner>);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The backend is unreachable.',
    );
  });

  it.each(NON_ERROR)('announces a %s banner as a status', (tone) => {
    render(<Banner tone={tone}>Preview dialect.</Banner>);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders a title alongside its body', () => {
    render(
      <Banner tone="preview" title="Not deployment-verified">
        Transpiles, but needs an ENGINE clause.
      </Banner>,
    );
    expect(screen.getByText('Not deployment-verified')).toBeInTheDocument();
    expect(
      screen.getByText('Transpiles, but needs an ENGINE clause.'),
    ).toBeInTheDocument();
  });
});
