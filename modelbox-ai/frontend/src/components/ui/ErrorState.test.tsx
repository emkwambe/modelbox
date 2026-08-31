/**
 * F2 — the states a surface can be in other than "showing content".
 *
 * The assertion that carries the most weight here is the *negative* one: a
 * permission failure offers no retry. `lib/api.ts` clears the session on 401
 * and lets 403 fall through to the generic error path, so a user whose
 * workspace does not permit an action is currently told "something went wrong"
 * and given a button that is guaranteed to fail. Deriving both the wording and
 * the retry from `kind` is what makes that unforgettable at the call site.
 *
 * Mutation, 2026-08-31: changing `canRetry` to `Boolean(onRetry)` — dropping
 * the kind check, which is the obvious simplification — fails exactly one test,
 * `offers no retry on a permission failure`.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ErrorState from './ErrorState';
import LoadingState from './LoadingState';
import type { ErrorKind } from './ErrorState';

const KINDS: ErrorKind[] = ['error', 'denied', 'missing'];

describe('ErrorState', () => {
  it('announces the failure with its detail, not just its heading', () => {
    render(<ErrorState>The backend is unreachable.</ErrorState>);

    // The role is on the region, not the heading. A heading-only alert reads
    // "Something went wrong" and stops before the sentence that says what to do.
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Something went wrong');
    expect(alert).toHaveTextContent('The backend is unreachable.');
  });

  it('has more than one kind to distinguish', () => {
    // Precondition: with a single kind the parameterised test below would prove
    // nothing about the distinction it exists to check.
    expect(KINDS.length).toBeGreaterThan(1);
  });

  it.each(KINDS)('gives %s its own wording', (kind) => {
    render(<ErrorState kind={kind} />);
    expect(screen.getByRole('alert')).not.toBeEmptyDOMElement();
  });

  it('words a permission failure as a permission failure', () => {
    render(<ErrorState kind="denied" />);
    // Not "something went wrong": nothing went wrong, the answer was no.
    expect(screen.getByRole('alert')).toHaveTextContent(/does not permit/i);
  });

  it('gives each kind wording of its own', () => {
    // The parameterised test above only proves each kind says *something*. This
    // is the half that proves they differ — without it, a `TITLES` map whose
    // three entries were identical would pass everything else here.
    const titles = KINDS.map((kind) => {
      const { unmount } = render(<ErrorState kind={kind} />);
      const text = screen.getByRole('alert').textContent ?? '';
      unmount();
      return text;
    });
    expect(new Set(titles).size).toBe(KINDS.length);
  });

  it('retries when retrying could work', async () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry}>Timed out.</ErrorState>);

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('offers no retry on a permission failure', () => {
    // A retry button here is a button guaranteed to fail. The handler is
    // supplied on purpose: the component has to refuse it, not merely omit a
    // button nobody asked for.
    render(<ErrorState kind="denied" onRetry={vi.fn()} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('offers no retry when there is nothing to call', () => {
    render(<ErrorState />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('LoadingState', () => {
  it('announces itself politely, and is not an alert', () => {
    render(<LoadingState />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Loading…');
    expect(status).toHaveAttribute('aria-live', 'polite');
    // A page still loading is not an emergency; interrupting for every one of
    // them is its own accessibility defect.
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('says what is being waited for when told', () => {
    render(<LoadingState label="Loading documentation…" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading documentation…');
  });
});
