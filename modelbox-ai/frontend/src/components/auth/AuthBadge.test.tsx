/**
 * The workspace list, and what happened when it failed.
 *
 * `listWorkspaces().catch(() => undefined)`. The switcher is gated on
 * `workspaces.length > 0`, so a failed request did not fail — it rendered
 * *nothing*. A user who could not switch workspace had no way to tell whether
 * they had one workspace or whether the request had died, and there was no
 * error anywhere on screen to ask about.
 *
 * A discarded error that changes what is displayed is the worst kind, because
 * the absence is indistinguishable from a legitimate empty state. That is the
 * same shape as the `/docs` "Loading…" forever, and it is why both are in this
 * commit.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/store/authStore';

import AuthBadge from './AuthBadge';

const { listWorkspaces } = vi.hoisted(() => ({ listWorkspaces: vi.fn() }));

vi.mock('@/lib/api', () => ({ listWorkspaces }));

const WORKSPACES = [
  { workspace_id: 'w1', name: 'Acme', role: 'owner' },
  { workspace_id: 'w2', name: 'Contoso', role: 'member' },
];

beforeEach(() => {
  listWorkspaces.mockReset();
  useAuthStore.setState({
    token: 'a-token',
    email: 'dev@modelbox.ai',
    workspaces: [],
    activeWorkspaceId: null,
    modalOpen: false,
  });
});

describe('AuthBadge', () => {
  it('offers a named switcher once the workspaces arrive', async () => {
    listWorkspaces.mockResolvedValue(WORKSPACES);
    render(<AuthBadge />);

    // By role and name: the `<select>` had no accessible name, so it was
    // announced as "combo box" with no indication of what it selected.
    const select = await screen.findByRole('combobox', {
      name: 'Active workspace',
    });
    expect(select).toBeInTheDocument();
  });

  it('says so when the workspaces cannot be loaded', async () => {
    listWorkspaces.mockRejectedValue(new Error('Network Error'));
    render(<AuthBadge />);

    // The defect, stated as an assertion: before this the badge rendered
    // exactly the same thing here as it does for a user with no workspaces.
    await waitFor(() =>
      expect(screen.getByText('Workspaces unavailable')).toBeInTheDocument(),
    );
    expect(screen.getByTitle('Network Error')).toBeInTheDocument();
  });

  it('shows no failure notice when nothing failed', async () => {
    // The precondition for the test above. If the notice were always rendered,
    // that assertion would pass on a component that never checks anything.
    listWorkspaces.mockResolvedValue(WORKSPACES);
    render(<AuthBadge />);

    await screen.findByRole('combobox', { name: 'Active workspace' });
    expect(screen.queryByText('Workspaces unavailable')).toBeNull();
  });

  it('does not ask for workspaces when signed out', () => {
    useAuthStore.setState({ token: null, email: null });
    render(<AuthBadge />);
    expect(listWorkspaces).not.toHaveBeenCalled();
  });
});
