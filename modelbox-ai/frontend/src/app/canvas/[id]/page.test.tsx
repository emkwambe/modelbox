/**
 * /canvas/<id> reads the model from the server and puts it on the canvas, so
 * a reload, a new tab or a shared link reopens it. Unsaved changes to the same
 * model already on the canvas are kept, not overwritten.
 */

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import type { SynthesizeResponse } from '@/types/schema';

import CanvasByIdPage from './page';

const { getModel } = vi.hoisted(() => ({ getModel: vi.fn() }));
vi.mock('@/lib/api', () => ({ getModel }));
vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'm42' }) }));
vi.mock('@/app/canvas/page', () => ({ default: () => <p>canvas workspace</p> }));

const MODEL: SynthesizeResponse = {
  model_id: 'm42',
  paradigm: '3NF',
  suggested_metrics: [],
  entities: [{ entity_name: 'customer', entity_type: 'TABLE', canvas_position_x: 0, canvas_position_y: 0,
    columns: [{ name: 'id', data_type: 'INTEGER', is_primary_key: true, is_foreign_key: false,
      is_pii: false, is_metric: false }], primary_key: ['id'] }],
  relationships: [],
};

beforeEach(() => {
  getModel.mockReset();
  useCanvasStore.getState().reset();
});

describe('/canvas/<id>', () => {
  it('reads the model from the server and shows the canvas', async () => {
    getModel.mockResolvedValue(structuredClone(MODEL));
    render(<CanvasByIdPage />);
    expect(await screen.findByText('canvas workspace')).toBeInTheDocument();
    expect(getModel).toHaveBeenCalledWith('m42');
    const state = useCanvasStore.getState();
    expect(state.modelId).toBe('m42');
    expect(state.nodes.map((n) => n.id)).toEqual(['customer']);
    expect(state.dirty).toBe(false);
  });

  it('keeps unsaved changes to the same model rather than reloading over them', async () => {
    useCanvasStore.getState().loadModel(structuredClone(MODEL));
    useCanvasStore.getState().updateColumn('customer', 'id', { description: 'edited' });
    render(<CanvasByIdPage />);
    expect(await screen.findByText('canvas workspace')).toBeInTheDocument();
    expect(getModel).not.toHaveBeenCalled();
    expect(useCanvasStore.getState().nodes[0]!.data.columns[0]!.description).toBe('edited');
  });

  it('says so when the model cannot be opened', async () => {
    getModel.mockRejectedValue(new Error('gone'));
    render(<CanvasByIdPage />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
