/**
 * The same three-state defect as `api-keys`, on the other settings list.
 *
 * Kept as its own file rather than parameterised over the two pages: they share
 * a shape, not an implementation, and a shared test would go green on one page
 * while the other regressed. The duplication is the point — each page is
 * asserted against its own rendering.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/store/authStore';

import ConnectorsPage from './page';

const api = vi.hoisted(() => ({
  createConnection: vi.fn(),
  deleteConnection: vi.fn(),
  introspectConnection: vi.fn(),
  listConnections: vi.fn(),
}));

vi.mock('@/lib/api', () => api);
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const CONNECTION = {
  connection_id: 'c1',
  name: 'Warehouse',
  engine: 'POSTGRESQL',
  created_at: '2026-01-01T00:00:00Z',
};

function apiError(status: number, detail: string) {
  return Object.assign(new Error(`status ${status}`), {
    response: { status, data: { detail } },
  });
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  useAuthStore.setState({
    token: 'a-token',
    email: 'dev@modelbox.ai',
    activeWorkspaceId: null,
  });
});

describe('ConnectorsPage', () => {
  it('does not claim there are no connections while it is still asking', async () => {
    api.listConnections.mockImplementation(() => new Promise(() => {}));
    render(<ConnectorsPage />);

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'Loading connections…',
      ),
    );
    expect(screen.queryByText('No connections yet.')).toBeNull();
  });

  it('says there are none once it knows', async () => {
    api.listConnections.mockResolvedValue([]);
    render(<ConnectorsPage />);

    expect(await screen.findByText('No connections yet.')).toBeInTheDocument();
  });

  it('lists the connections it was given', async () => {
    api.listConnections.mockResolvedValue([CONNECTION]);
    render(<ConnectorsPage />);

    expect(await screen.findByText('Warehouse')).toBeInTheDocument();
  });

  it('reports a failed load instead of an empty list', async () => {
    api.listConnections.mockRejectedValue(new Error('Network Error'));
    render(<ConnectorsPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Your connections could not be loaded');
    expect(screen.queryByText('No connections yet.')).toBeNull();
  });

  it('words a permission failure as one, and offers no retry', async () => {
    api.listConnections.mockRejectedValue(
      apiError(403, 'Your role does not allow managing connections.'),
    );
    render(<ConnectorsPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your role does not allow managing connections.',
    );
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
  });

  it('asks for nothing while signed out', () => {
    useAuthStore.setState({ token: null, email: null });
    render(<ConnectorsPage />);
    expect(api.listConnections).not.toHaveBeenCalled();
  });
});
