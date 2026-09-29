/**
 * The classification scale page (Sprint 8 Step 4b): it shows the workspace's
 * levels with how many columns use each, lets an admin add, rename and delete,
 * and says so when the server refuses a delete. A member sees the scale and
 * no controls. Negative control: an unused level's delete is offered.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/store/authStore';

import ClassificationPage from './page';

const api = vi.hoisted(() => ({
  addClassificationLevel: vi.fn(),
  deleteClassificationLevel: vi.fn(),
  getClassificationScale: vi.fn(),
  listWorkspaces: vi.fn(),
  updateClassificationLevel: vi.fn(),
}));

vi.mock('@/lib/api', () => api);

const SCALE = {
  workspace_id: 'w1',
  scale_id: 's1',
  name: 'Sensitivity',
  levels: [
    { level_id: 'l1', name: 'Public', rank: 1, columns_using: 0 },
    { level_id: 'l2', name: 'Internal', rank: 2, columns_using: 0 },
    { level_id: 'l3', name: 'Confidential', rank: 3, columns_using: 2 },
    { level_id: 'l4', name: 'Restricted', rank: 4, columns_using: 0 },
  ],
};

function apiError(status: number, detail: string) {
  return Object.assign(new Error(`status ${status}`), { response: { status, data: { detail } } });
}

function as(role: string) {
  api.listWorkspaces.mockResolvedValue([{ workspace_id: 'w1', name: 'W', role }]);
  api.getClassificationScale.mockResolvedValue(structuredClone(SCALE));
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  useAuthStore.setState({ token: 'a-token', email: 'dev@modelbox.ai', activeWorkspaceId: null });
});

describe('ClassificationPage', () => {
  it('lists the levels in order with how many columns use each', async () => {
    as('MEMBER');
    render(<ClassificationPage />);
    expect(await screen.findByText('Confidential')).toBeInTheDocument();
    const items = screen.getAllByRole('listitem').map((li) => li.textContent);
    expect(items).toEqual([
      'Public0 columns', 'Internal0 columns', 'Confidential2 columns', 'Restricted0 columns',
    ]);
    expect(api.getClassificationScale).toHaveBeenCalledTimes(1);
  });

  it('gives a member no controls', async () => {
    as('MEMBER');
    render(<ClassificationPage />);
    await screen.findByText('Confidential');
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(screen.getByText('Only a workspace owner or admin can change the scale.')).toBeInTheDocument();
  });

  it('does not offer to delete a level in use; negative control: an unused one is offered', async () => {
    as('ADMIN');
    render(<ClassificationPage />);
    await screen.findByDisplayValue('Confidential');
    const deletes = screen.getAllByRole('button', { name: 'Delete' });
    expect(deletes.map((b) => (b as HTMLButtonElement).disabled)).toEqual([false, false, true, false]);
  });

  it('says so when the server refuses a delete', async () => {
    as('ADMIN');
    api.deleteClassificationLevel.mockRejectedValue(apiError(409, "The level 'Public' is used by 1 column(s)"));
    render(<ClassificationPage />);
    await screen.findByDisplayValue('Public');
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]!);
    expect(await screen.findByText(/used by 1 column/)).toBeInTheDocument();
  });

  it('renames a level on blur', async () => {
    as('ADMIN');
    api.updateClassificationLevel.mockResolvedValue(structuredClone(SCALE));
    render(<ClassificationPage />);
    const input = await screen.findByDisplayValue('Internal');
    fireEvent.change(input, { target: { value: 'Internal use' } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(api.updateClassificationLevel).toHaveBeenCalledWith('w1', 'l2', { name: 'Internal use' }),
    );
  });

  it('adds a level', async () => {
    as('ADMIN');
    api.addClassificationLevel.mockResolvedValue(structuredClone(SCALE));
    render(<ClassificationPage />);
    fireEvent.change(await screen.findByLabelText('New level'), { target: { value: 'Secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add level' }));
    await waitFor(() => expect(api.addClassificationLevel).toHaveBeenCalledWith('w1', 'Secret'));
  });

  it('reports a failed load', async () => {
    api.listWorkspaces.mockResolvedValue([{ workspace_id: 'w1', name: 'W', role: 'ADMIN' }]);
    api.getClassificationScale.mockRejectedValue(new Error('Network Error'));
    render(<ClassificationPage />);
    expect(await screen.findByText('The classification scale could not be loaded')).toBeInTheDocument();
  });
});
