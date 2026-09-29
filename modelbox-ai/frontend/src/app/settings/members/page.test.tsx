/**
 * The members page (Sprint 8 Step 6): it lists the members, lets an owner or
 * admin add an existing user, change a role and remove a member, offers no
 * role above the viewer's own, and shows the server's refusal when it comes
 * (an email with no user, the last owner). A member sees no controls.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/store/authStore';

import MembersPage from './page';

const api = vi.hoisted(() => ({
  addMember: vi.fn(),
  changeMemberRole: vi.fn(),
  listMembers: vi.fn(),
  listWorkspaces: vi.fn(),
  removeMember: vi.fn(),
}));

vi.mock('@/lib/api', () => api);

const MEMBERS = [
  { user_id: 'u1', email: 'owner@example.com', role: 'OWNER' },
  { user_id: 'u2', email: 'member@example.com', role: 'MEMBER' },
];

function apiError(status: number, detail: string) {
  return Object.assign(new Error(`status ${status}`), { response: { status, data: { detail } } });
}

function as(role: string) {
  api.listWorkspaces.mockResolvedValue([{ workspace_id: 'w1', name: 'W', role }]);
  api.listMembers.mockResolvedValue(structuredClone(MEMBERS));
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  useAuthStore.setState({ token: 'a-token', email: 'dev@modelbox.ai', activeWorkspaceId: null });
});

describe('MembersPage', () => {
  it('lists the members', async () => {
    as('OWNER');
    render(<MembersPage />);
    expect(await screen.findByText('member@example.com')).toBeInTheDocument();
    expect(api.listMembers).toHaveBeenCalledWith('w1');
  });

  it('gives a member no controls', async () => {
    as('MEMBER');
    render(<MembersPage />);
    await screen.findByText('member@example.com');
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.getByText('Only a workspace owner or admin can change its members.')).toBeInTheDocument();
  });

  it('offers an admin no OWNER role for a new member', async () => {
    as('ADMIN');
    render(<MembersPage />);
    const select = await screen.findByLabelText('Role for the new member');
    expect(within(select).queryByRole('option', { name: 'OWNER' })).toBeNull();
    expect(within(select).getByRole('option', { name: 'ADMIN' })).toBeInTheDocument();
  });

  it('adds an existing user by email', async () => {
    as('OWNER');
    api.addMember.mockResolvedValue(structuredClone(MEMBERS));
    render(<MembersPage />);
    fireEvent.change(await screen.findByLabelText('Email of the user to add'), {
      target: { value: 'new@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }));
    await waitFor(() => expect(api.addMember).toHaveBeenCalledWith('w1', 'new@example.com', 'VIEWER'));
  });

  it('shows the server refusing an email with no user', async () => {
    as('OWNER');
    api.addMember.mockRejectedValue(apiError(404, "No user with the email 'x@example.com' exists on this appliance."));
    render(<MembersPage />);
    fireEvent.change(await screen.findByLabelText('Email of the user to add'), { target: { value: 'x@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }));
    expect(await screen.findByText(/No user with the email/)).toBeInTheDocument();
  });

  it('changes a role and shows the last-owner refusal', async () => {
    as('OWNER');
    api.changeMemberRole.mockRejectedValue(apiError(409, 'The last OWNER of a workspace cannot be demoted or removed.'));
    render(<MembersPage />);
    fireEvent.change(await screen.findByLabelText('Role of owner@example.com'), { target: { value: 'ADMIN' } });
    await waitFor(() => expect(api.changeMemberRole).toHaveBeenCalledWith('w1', 'u1', 'ADMIN'));
    expect(await screen.findByText(/last OWNER/)).toBeInTheDocument();
  });

  it('removes a member', async () => {
    as('OWNER');
    api.removeMember.mockResolvedValue(undefined);
    render(<MembersPage />);
    await screen.findByText('member@example.com');
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[1]!);
    await waitFor(() => expect(api.removeMember).toHaveBeenCalledWith('w1', 'u2'));
  });
});
