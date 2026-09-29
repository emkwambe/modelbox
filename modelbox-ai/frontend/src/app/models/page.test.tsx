/**
 * The model list: every saved model, each opening at /canvas/<id>.
 */

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ModelsPage from './page';

const { listModels } = vi.hoisted(() => ({ listModels: vi.fn() }));
vi.mock('@/lib/api', () => ({ listModels }));

beforeEach(() => listModels.mockReset());

describe('the model list', () => {
  it('links each model to its canvas', async () => {
    listModels.mockResolvedValue([
      { model_id: 'a1', workspace_id: 'w', title: 'Billing', current_paradigm: '3NF',
        target_dialect: 'postgres', version_number: 3 },
      { model_id: 'b2', workspace_id: 'w', title: 'Claims', current_paradigm: null,
        target_dialect: 'oracle', version_number: 1 },
    ]);
    render(<ModelsPage />);
    expect(await screen.findByRole('link', { name: 'Billing' })).toHaveAttribute('href', '/canvas/a1');
    expect(screen.getByRole('link', { name: 'Claims' })).toHaveAttribute('href', '/canvas/b2');
  });

  it('says so when there are none', async () => {
    listModels.mockResolvedValue([]);
    render(<ModelsPage />);
    expect(await screen.findByText(/No saved models yet/)).toBeInTheDocument();
  });

  it('says so when the list cannot be loaded', async () => {
    // Rejected when called, not when the test is set up (see Step 3's verification record).
    listModels.mockImplementation(async () => {
      throw new Error('down');
    });
    render(<ModelsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('down');
  });
});
