/**
 * The diff panel says, above everything else, when a migration drops data
 * (Sprint 8 Step 6): each statement that destroys data is named in words.
 * Negative control: a migration that drops nothing shows no such alert.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';

import DiffPanel from './DiffPanel';

const api = vi.hoisted(() => ({ diffModels: vi.fn(), listModels: vi.fn() }));
vi.mock('@/lib/api', () => api);

const LOSS = 'Drops column a.cust_email and its data. Columns of separately saved models are matched by name.';

function diff(dataLoss: string[]) {
  return {
    source_model_id: 'm1', target_model_id: 'm2', dialect: 'postgres',
    alter_statements: [], breaking_changes: [], semantic_breaks: [], data_loss: dataLoss,
  };
}

async function compute() {
  render(<DiffPanel onClose={() => {}} />);
  await screen.findByRole('option', { name: 'Orders v2 · v1' });
  // The first select is the target model; the second, the dialect.
  fireEvent.change(screen.getAllByRole('combobox')[0]!, { target: { value: 'm2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Compute diff' }));
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listModels.mockResolvedValue([
    { model_id: 'm2', title: 'Orders v2', version_number: 1, workspace_id: 'w1' },
  ]);
  useCanvasStore.setState({ modelId: 'm1' });
});

describe('DiffPanel', () => {
  it('says the migration drops data, naming each column', async () => {
    api.diffModels.mockResolvedValue(diff([LOSS]));
    await compute();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('This migration drops data (1)');
    expect(alert).toHaveTextContent(LOSS);
  });

  it('negative control: no alert when nothing is dropped', async () => {
    api.diffModels.mockResolvedValue(diff([]));
    await compute();
    await waitFor(() => expect(screen.getByText('✓ No breaking changes')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
