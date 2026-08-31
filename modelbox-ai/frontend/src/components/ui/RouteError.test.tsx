/**
 * What a segment renders when it throws.
 *
 * The boundary itself is Next.js's to invoke, and `boundaries.walk.test.ts`
 * checks every segment has one. This is the other half: what the user meets
 * once it is invoked.
 *
 * The console assertion is the one that would otherwise go missing. A boundary
 * that renders a tidy message and swallows the cause turns every subsequent
 * report into guesswork — the failure is gone from the console *and* from the
 * screen — and it is invisible in review because the page looks correct.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RouteError from './RouteError';

afterEach(() => {
  vi.restoreAllMocks();
});

/** Silences the boundary's own logging while keeping it observable. */
function captureConsole() {
  return vi.spyOn(console, 'error').mockImplementation(() => {});
}

describe('RouteError', () => {
  it('names the surface that failed', () => {
    captureConsole();
    render(
      <RouteError
        error={new Error('boom')}
        reset={() => {}}
        surface="The canvas"
      />,
    );
    // Not "something went wrong" over an app with seven surfaces: naming the
    // one that failed is the entire reason these boundaries are per-segment.
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The canvas could not be displayed',
    );
  });

  it('shows the message rather than hiding it', () => {
    captureConsole();
    render(
      <RouteError
        error={new Error('Network request failed')}
        reset={() => {}}
        surface="The trainer"
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Network request failed');
  });

  it('includes the digest when Next.js supplies one', () => {
    captureConsole();
    const error = Object.assign(new Error('boom'), { digest: 'abc123' });
    render(<RouteError error={error} reset={() => {}} surface="The canvas" />);

    // The identifier a server-side log can be searched by. Without it a user
    // reporting the failure has nothing to quote.
    expect(screen.getByRole('alert')).toHaveTextContent('abc123');
  });

  it('says something even when the error does not', () => {
    captureConsole();
    render(<RouteError error={new Error('')} reset={() => {}} surface="The canvas" />);
    // An empty `message` is common for thrown non-Errors. Falling through to a
    // blank detail line would leave the user with a heading and no sentence.
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The page stopped while it was being rendered.',
    );
  });

  it('retries the segment', async () => {
    captureConsole();
    const reset = vi.fn();
    render(<RouteError error={new Error('boom')} reset={reset} surface="The canvas" />);

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it('logs the cause instead of swallowing it', () => {
    const spy = captureConsole();
    const error = new Error('boom');
    render(<RouteError error={error} reset={() => {}} surface="The canvas" />);

    // The error object itself, not a string built from it: a log that stringifies
    // the message loses the stack, which is the part worth having.
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining('The canvas'),
      error,
    );
  });
});
