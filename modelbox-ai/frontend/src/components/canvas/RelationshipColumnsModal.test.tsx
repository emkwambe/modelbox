/**
 * Drawing a relationship asks for its columns (Sprint 8 Step 3, owner
 * decision): the target's primary key is proposed, source columns are matched
 * by name, every pair is editable, and nothing is added until every pair is
 * complete.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import RelationshipColumnsModal, { proposedPairs } from '@/components/canvas/RelationshipColumnsModal';
import { useCanvasStore } from '@/store/canvasStore';
import type { Column, Entity } from '@/types/schema';

const col = (name: string, extra: Partial<Column> = {}): Column => ({
  name, data_type: 'INTEGER', is_primary_key: false, is_foreign_key: false, is_pii: false, is_metric: false,
  ...extra,
});

const ENTITIES: Entity[] = [
  { entity_name: 'orders', entity_type: 'TABLE', canvas_position_x: 0, canvas_position_y: 0,
    columns: [col('order_id', { is_primary_key: true }), col('region', { is_primary_key: true })],
    primary_key: ['order_id', 'region'] },
  { entity_name: 'order_line', entity_type: 'TABLE', canvas_position_x: 0, canvas_position_y: 0,
    columns: [col('order_id'), col('zone'), col('line_no')] },
];

beforeEach(() => {
  useCanvasStore.getState().reset();
  useCanvasStore.getState().loadGraph(structuredClone(ENTITIES), []);
});

describe('proposedPairs', () => {
  it('proposes the target key, matching source columns by name', () => {
    const [target, source] = useCanvasStore.getState().nodes.map((n) => n.data);
    expect(proposedPairs(source!, target!)).toEqual([
      { from: 'order_id', to: 'order_id' },
      { from: '', to: 'region' },
    ]);
  });

  it('starts from the saved pairs when a relationship already has them', () => {
    const [target, source] = useCanvasStore.getState().nodes.map((n) => n.data);
    expect(proposedPairs(source!, target!, { from_columns: ['zone'], to_columns: ['region'] })).toEqual([
      { from: 'zone', to: 'region' },
    ]);
  });
});

describe('the picker', () => {
  it('adds nothing until every pair is chosen, then adds one composite relationship', async () => {
    useCanvasStore.getState().onConnect({ source: 'order_line', target: 'orders', sourceHandle: null,
      targetHandle: null });
    render(<RelationshipColumnsModal />);
    const add = screen.getByRole('button', { name: 'Add relationship' });
    expect(add).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText('order_line column 2'), 'zone');
    expect(add).toBeEnabled();
    await userEvent.click(add);

    const edges = useCanvasStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(edges[0]!.data).toMatchObject({
      from_ref: 'order_line', from_columns: ['order_id', 'zone'],
      to_ref: 'orders', to_columns: ['order_id', 'region'], cardinality: 'N:1',
    });
    expect(useCanvasStore.getState().pendingConnection).toBeNull();
  });

  it('refuses a column used in two pairs', async () => {
    useCanvasStore.getState().onConnect({ source: 'order_line', target: 'orders', sourceHandle: null,
      targetHandle: null });
    render(<RelationshipColumnsModal />);
    await userEvent.selectOptions(screen.getByLabelText('order_line column 2'), 'order_id');
    expect(screen.getByRole('button', { name: 'Add relationship' })).toBeDisabled();
    expect(screen.getByText('A column appears in two pairs.')).toBeInTheDocument();
  });

  it('Cancel adds nothing', async () => {
    useCanvasStore.getState().onConnect({ source: 'order_line', target: 'orders', sourceHandle: null,
      targetHandle: null });
    render(<RelationshipColumnsModal />);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(useCanvasStore.getState().edges).toHaveLength(0);
    expect(useCanvasStore.getState().pendingConnection).toBeNull();
  });
});
