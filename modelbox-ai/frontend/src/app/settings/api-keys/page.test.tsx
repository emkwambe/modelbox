/**
 * F2 on the settings lists — "No API keys yet" was shown before anyone knew.
 *
 * The page inferred "still loading" from `keys.length === 0`, which is also the
 * genuinely-empty state. So a user with keys was told they had none, and then
 * watched the sentence be replaced. An empty list and an unfinished request
 * look identical on screen and mean opposite things.
 *
 * The permission test is the other half. `lib/api.ts` handles 401 and lets
 * everything else through one generic path, so a 403 read "something went
 * wrong" over a retry button that could not work. Both the wording and the
 * absence of the button are asserted, because either alone would pass on a
 * component that got the other wrong.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/store/authStore';

import ApiKeysPage from './page';

const { createApiKey, listApiKeys, revokeApiKey } = vi.hoisted(() => ({
  createApiKey: vi.fn(),
  listApiKeys: vi.fn(),
  revokeApiKey: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ createApiKey, listApiKeys, revokeApiKey }));

const KEY = {
  api_key_id: 'k1',
  name: 'CI pipeline',
  key_prefix: 'mb_abc',
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: null,
  expires_at: null,
};

/** An axios-shaped rejection carrying a status. */
function apiError(status: number, detail: string) {
  return Object.assign(new Error(`status ${status}`), {
    response: { status, data: { detail } },
  });
}

beforeEach(() => {
  listApiKeys.mockReset();
  createApiKey.mockReset();
  revokeApiKey.mockReset();
  useAuthStore.setState({ token: 'a-token', email: 'dev@modelbox.ai' });
});

describe('ApiKeysPage', () => {
  it('does not claim the account is empty while it is still asking', async () => {
    listApiKeys.mockImplementation(() => new Promise(() => {}));
    render(<ApiKeysPage />);

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Loading API keys…'),
    );
    // The defect, as an assertion.
    expect(screen.queryByText('No API keys yet.')).toBeNull();
  });

  it('says the account is empty once it knows', async () => {
    listApiKeys.mockResolvedValue([]);
    render(<ApiKeysPage />);

    expect(await screen.findByText('No API keys yet.')).toBeInTheDocument();
  });

  it('lists the keys it was given', async () => {
    listApiKeys.mockResolvedValue([KEY]);
    render(<ApiKeysPage />);

    expect(await screen.findByText('CI pipeline')).toBeInTheDocument();
    expect(screen.queryByText('No API keys yet.')).toBeNull();
  });

  it('reports a failed load instead of an empty account', async () => {
    listApiKeys.mockRejectedValue(new Error('Network Error'));
    render(<ApiKeysPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Your API keys could not be loaded');
    expect(alert).toHaveTextContent('Network Error');
    expect(screen.queryByText('No API keys yet.')).toBeNull();
  });

  it('retries a failed load', async () => {
    listApiKeys.mockRejectedValueOnce(new Error('Network Error'));
    listApiKeys.mockResolvedValue([KEY]);
    render(<ApiKeysPage />);

    await screen.findByRole('alert');
    (await screen.findByRole('button', { name: 'Try again' })).click();

    expect(await screen.findByText('CI pipeline')).toBeInTheDocument();
  });

  it('words a permission failure as one, and offers no retry', async () => {
    listApiKeys.mockRejectedValue(
      apiError(403, 'Your role does not allow managing API keys.'),
    );
    render(<ApiKeysPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Your role does not allow managing API keys.',
    );
    // A retry here is a button guaranteed to fail: the answer does not change
    // on a second attempt.
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
  });

  it('asks for nothing while signed out', () => {
    useAuthStore.setState({ token: null, email: null });
    render(<ApiKeysPage />);

    expect(listApiKeys).not.toHaveBeenCalled();
    expect(
      screen.getByText('Sign in to manage API keys.'),
    ).toBeInTheDocument();
  });
});
