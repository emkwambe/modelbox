/**
 * The session has three states, and the third one is the defect (F2).
 *
 * Found by previewing the app rather than by testing it: `/settings/api-keys`
 * screenshotted as a **completely blank page**, and `/settings/egress` rendered
 * the *ledger* — signed-in content — to a visitor who was not signed in. Both
 * came from the same mistake in two directions.
 *
 * Every screen used a local `mounted` flag as a proxy for "the persisted token
 * is known". They correlate by accident of ordering and are not the same
 * question, so:
 *
 *   `if (!mounted) return null`      -> nothing at all is drawn
 *   `if (mounted && !token)`         -> the signed-out branch is skipped, so
 *                                        the signed-in UI renders instead
 *
 * The second is the worse one: a blank page looks like a slow app, while a
 * flash of authenticated UI shows a stranger something and then takes it away.
 *
 * `useAuthStatus` answers the real question via zustand's own
 * `persist.hasHydrated()`, and makes `unknown` a state with a rendering rather
 * than an absence collapsed into one of the other two.
 *
 * **These tests drive the hook rather than a page**, because the bug is in the
 * concept, not in any one screen — five files had it, and a per-page test would
 * have to be written five times and would still miss the sixth.
 */

import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStatus, useAuthStore } from './authStore';

function Probe() {
  const status = useAuthStatus();
  return <span data-testid="status">{status}</span>;
}

const status = () => screen.getByTestId('status').textContent;

describe('useAuthStatus', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, email: null });
    vi.restoreAllMocks();
  });

  it('reports signed-out once hydration has finished with no token', () => {
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(true);
    render(<Probe />);
    expect(status()).toBe('signed-out');
  });

  it('reports signed-in once hydration has finished with a token', () => {
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(true);
    useAuthStore.setState({ token: 'jwt', email: 'a@example.com' });
    render(<Probe />);
    expect(status()).toBe('signed-in');
  });

  it('reports unknown before hydration, never signed-out', () => {
    // The assertion the whole change exists for. Reporting `signed-out` here is
    // what made pages render a sign-in prompt to a user who *was* signed in;
    // reporting `signed-in` is what flashed the ledger at a stranger.
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(false);
    vi.spyOn(useAuthStore.persist, 'onFinishHydration').mockReturnValue(
      () => undefined,
    );
    render(<Probe />);
    expect(status()).toBe('unknown');
  });

  it('leaves unknown when hydration finishes, without a remount', () => {
    let finish: () => void = () => undefined;
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(false);
    vi.spyOn(useAuthStore.persist, 'onFinishHydration').mockImplementation(
      // The listener is typed to receive the hydrated state; this hook ignores
      // it, so the cast keeps the test honest about the real signature rather
      // than widening the hook's.
      ((cb: (state: unknown) => void) => {
        finish = () => cb(useAuthStore.getState());
        return () => undefined;
      }) as never,
    );

    render(<Probe />);
    expect(status()).toBe('unknown');

    useAuthStore.setState({ token: 'jwt' });
    act(() => finish());

    expect(status()).toBe('signed-in');
  });

  it('does not report unknown when it mounts after hydration', () => {
    // The other direction, and the reason the hook seeds its state from the
    // store rather than from `false`. A component mounting late must not flash
    // a loading surface it has no reason to show — which would replace the
    // original defect with a subtler one.
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(true);
    const onFinish = vi.spyOn(useAuthStore.persist, 'onFinishHydration');

    render(<Probe />);

    expect(status()).toBe('signed-out');
    // Subscribing is still correct — it is the unsubscribe that must exist —
    // but the first paint must already be accurate.
    expect(onFinish).toHaveBeenCalled();
  });

  it('unsubscribes on unmount', () => {
    const unsubscribe = vi.fn();
    vi.spyOn(useAuthStore.persist, 'hasHydrated').mockReturnValue(false);
    vi.spyOn(useAuthStore.persist, 'onFinishHydration').mockReturnValue(
      unsubscribe,
    );

    const view = render(<Probe />);
    view.unmount();

    expect(unsubscribe).toHaveBeenCalled();
  });
});
