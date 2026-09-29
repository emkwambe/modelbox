/**
 * The key-access selector offers caps up to the creator's role, never above.
 *
 * Sprint 7 Step 2.5. The server refuses a cap above the creator's current role
 * (Step 2.3); the page must not offer one. The options come from the creator's
 * role in the workspace the key will be created in, and creation names that
 * same workspace, so the options and the request cannot disagree.
 *
 * The rendered options are read through one check, `checkNoCapAbove`. Its
 * negative control hands the check the full ladder as offered to a MEMBER and
 * asserts it fails.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ROLE_LADDER, capsUpTo } from '@/lib/roles';
import { useAuthStore } from '@/store/authStore';

import ApiKeysPage from './page';

const { createApiKey, listApiKeys, listWorkspaces, revokeApiKey } = vi.hoisted(() => ({
  createApiKey: vi.fn(),
  listApiKeys: vi.fn(),
  listWorkspaces: vi.fn(),
  revokeApiKey: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ createApiKey, listApiKeys, listWorkspaces, revokeApiKey }));

function ws(id: string, role: string) {
  return { workspace_id: id, name: `ws-${id}`, role };
}

/** Throws if any offered cap sits above ``role`` on the ladder. */
function checkNoCapAbove(offered: string[], role: string): void {
  const limit = ROLE_LADDER.indexOf(role as (typeof ROLE_LADDER)[number]);
  const above = offered.filter((cap) => ROLE_LADDER.indexOf(cap as never) > limit);
  if (limit < 0 || above.length > 0) {
    throw new Error(`offers ${above.join(', ') || 'caps'} above ${role}`);
  }
}

async function offeredCaps(): Promise<string[]> {
  const select = await screen.findByRole('combobox', { name: 'Key access' });
  return Array.from((select as HTMLSelectElement).options).map((o) => o.value);
}

beforeEach(() => {
  createApiKey.mockReset().mockResolvedValue({ api_key: 'mb_live_x' });
  listApiKeys.mockReset().mockResolvedValue([]);
  listWorkspaces.mockReset();
  revokeApiKey.mockReset();
  useAuthStore.setState({ token: 'a-token', email: 'a@example.com', activeWorkspaceId: null });
});

describe('capsUpTo', () => {
  it.each(ROLE_LADDER)('offers %s and everything below it, nothing above', (role) => {
    const caps = capsUpTo(role);
    expect(caps.at(-1)).toBe(role);
    expect(caps).toEqual(ROLE_LADDER.slice(0, ROLE_LADDER.indexOf(role) + 1));
  });

  it('offers nothing for a role it does not know', () => {
    expect(capsUpTo('SUPERUSER')).toEqual([]);
    expect(capsUpTo(undefined)).toEqual([]);
  });
});

describe('the key-access selector', () => {
  it.each(['VIEWER', 'MEMBER', 'APPROVER', 'ADMIN', 'OWNER'])(
    'offers caps up to a %s creator, never above',
    async (role) => {
      listWorkspaces.mockResolvedValue([ws('w1', role)]);
      render(<ApiKeysPage />);
      await waitFor(async () => expect(await offeredCaps()).toContain(role));
      const offered = await offeredCaps();
      checkNoCapAbove(offered, role);
      expect(offered).toEqual(capsUpTo(role));
    },
  );

  it('defaults to VIEWER', async () => {
    listWorkspaces.mockResolvedValue([ws('w1', 'ADMIN')]);
    render(<ApiKeysPage />);
    const select = await screen.findByRole('combobox', { name: 'Key access' });
    await waitFor(() => expect((select as HTMLSelectElement).options).toHaveLength(4));
    expect((select as HTMLSelectElement).value).toBe('VIEWER');
  });

  it('uses the role in the active workspace, not the first one', async () => {
    listWorkspaces.mockResolvedValue([ws('w1', 'ADMIN'), ws('w2', 'MEMBER')]);
    useAuthStore.setState({ activeWorkspaceId: 'w2' });
    render(<ApiKeysPage />);
    await waitFor(async () => expect(await offeredCaps()).toEqual(['VIEWER', 'MEMBER']));
  });

  it('creates the key in that workspace with the chosen cap', async () => {
    listWorkspaces.mockResolvedValue([ws('w1', 'ADMIN')]);
    render(<ApiKeysPage />);
    const select = await screen.findByRole('combobox', { name: 'Key access' });
    await waitFor(() => expect((select as HTMLSelectElement).options).toHaveLength(4));

    await userEvent.type(screen.getByPlaceholderText('e.g. CI pipeline'), 'CI');
    await userEvent.selectOptions(select, 'MEMBER');
    await userEvent.click(screen.getByRole('button', { name: 'Generate key' }));

    await waitFor(() =>
      expect(createApiKey).toHaveBeenCalledWith({
        name: 'CI',
        workspace_id: 'w1',
        role_cap: 'MEMBER',
      }),
    );
  });

  it('offers nothing and creates nothing when the role is unknown', async () => {
    listWorkspaces.mockResolvedValue([]);
    render(<ApiKeysPage />);
    const select = await screen.findByRole('combobox', { name: 'Key access' });
    expect((select as HTMLSelectElement).options).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Generate key' })).toBeDisabled();
  });

  it('negative control: the full ladder offered to a MEMBER fails the check', () => {
    expect(() => checkNoCapAbove([...ROLE_LADDER], 'MEMBER')).toThrow(
      'offers APPROVER, ADMIN, OWNER above MEMBER',
    );
  });
});
