/**
 * F2 on the canvas header actions — `test_a_failed_save_tells_the_user`.
 *
 * All three handlers were `try`/`finally` with **no `catch`**, so a rejected
 * save threw into an unhandled rejection: the button stopped saying "Saving…",
 * nothing else changed, and the user was left looking at a canvas they had
 * every reason to believe was written to the server. Delete was worse in a
 * quieter way — it caught the error only to call `setBusy(false)`, which is a
 * failure the code deliberately discarded.
 *
 * These three tests fail against the previous implementation; the save one
 * fails with an unhandled rejection rather than an assertion, which is itself
 * the report.
 *
 * The success path is asserted too. A handler that reported every outcome as a
 * failure would satisfy all three error tests.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';

import CanvasPage from './page';

const { deleteModel, saveGraph, updateModel } = vi.hoisted(() => ({
  deleteModel: vi.fn(),
  saveGraph: vi.fn(),
  updateModel: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ deleteModel, saveGraph, updateModel }));

// The canvas itself is React Flow, which needs layout jsdom cannot provide.
// Stubbed because this file is about the header's error handling, and rendering
// a graph would only add a way for the test to fail for an unrelated reason.
vi.mock('@/components/canvas/ERDCanvas', () => ({ default: () => <div /> }));
vi.mock('@/components/canvas/ColumnSemanticEditor', () => ({ default: () => null }));
vi.mock('@/components/canvas/EntitySettingsEditor', () => ({ default: () => null }));
vi.mock('@/components/migration/DiffPanel', () => ({ default: () => null }));
vi.mock('@/components/editor/ExportPanel', () => ({ default: () => null }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => {
  saveGraph.mockReset();
  updateModel.mockReset();
  deleteModel.mockReset();
  useCanvasStore.setState({ modelId: 'm1' });
});

const click = (name: string) =>
  userEvent.click(screen.getByRole('button', { name }));

describe('canvas header actions', () => {
  it('has a model, so the actions are enabled', () => {
    // Precondition: every button here is gated on `modelId`, and a disabled
    // button would make all three failure tests pass without ever calling the
    // handler they are about.
    render(<CanvasPage />);
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });

  it('tells the user when a save fails', async () => {
    saveGraph.mockRejectedValue(
      Object.assign(new Error('boom'), {
        response: { data: { detail: 'Entity "orders" has no primary key.' } },
      }),
    );
    render(<CanvasPage />);

    await click('Save');

    // Announced, not just shown: `role="alert"` reaches a user whose attention
    // is on the canvas rather than the header.
    const alert = await screen.findByRole('alert');
    // The server's `detail`, not axios's "Request failed with status code 422".
    expect(alert).toHaveTextContent('Entity "orders" has no primary key.');
  });

  it('says nothing went wrong when nothing did', async () => {
    saveGraph.mockResolvedValue({ is_valid: true, issues: [] });
    render(<CanvasPage />);

    await click('Save');

    await waitFor(() => expect(screen.getByText('✓ Saved')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('tells the user when a rename fails', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('New title');
    updateModel.mockRejectedValue(new Error('Network Error'));
    render(<CanvasPage />);

    await click('Rename');

    expect(await screen.findByRole('alert')).toHaveTextContent('Network Error');
  });

  it('tells the user when a delete fails, instead of only stopping', async () => {
    // The most misleading of the three: the old code caught the error and did
    // nothing but clear the busy flag, so the model stayed on screen and the
    // user reasonably concluded the click had not registered.
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deleteModel.mockRejectedValue(new Error('Network Error'));
    render(<CanvasPage />);

    await click('Delete');

    expect(await screen.findByRole('alert')).toHaveTextContent('Network Error');
  });

  it('re-enables the buttons after a failure', async () => {
    // `finally` has to survive the new `catch`. Without it a failed save would
    // leave every action disabled and the only way forward would be a reload.
    saveGraph.mockRejectedValue(new Error('Network Error'));
    render(<CanvasPage />);

    await click('Save');
    await screen.findByRole('alert');

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled(),
    );
  });
});
