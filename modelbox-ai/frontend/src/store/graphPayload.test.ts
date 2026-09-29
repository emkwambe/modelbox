/**
 * The canvas round trip (Sprint 8 Step 3): what the server returns, loaded on
 * the canvas and saved back untouched, is the same graph — every entity,
 * column, constraint and relationship, in order. Compared whole, not field by
 * field, with negative controls showing the comparison sees a change.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import {
  columnPayload,
  constraintLists,
  relationshipToEdgeData,
  renameInLists,
} from '@/store/graphPayload';
import type { Column, EntityNodeData, SynthesizeResponse } from '@/types/schema';

const col = (name: string, extra: Partial<Column> = {}): Column => ({
  name,
  data_type: 'INTEGER',
  is_primary_key: false,
  is_foreign_key: false,
  is_pii: false,
  is_metric: false,
  ...extra,
});

/** A model as the server returns it: lists, and the flags derived from them. */
const SERVED: SynthesizeResponse = {
  model_id: 'm1',
  paradigm: '3NF',
  suggested_metrics: [],
  entities: [
    {
      entity_name: 'orders',
      entity_type: 'FACT',
      canvas_position_x: 10,
      canvas_position_y: 20,
      agg_time_column: 'placed_at',
      columns: [
        col('order_id', { is_primary_key: true, is_nullable: false }),
        col('region', { data_type: 'VARCHAR(8)', is_primary_key: true, is_nullable: false,
          check_expression: "region IN ('EU', 'US')" }),
        col('placed_at', { data_type: 'TIMESTAMP' }),
      ],
      primary_key: ['region', 'order_id'],
      unique_constraints: [{ name: 'uq_placed', columns: ['placed_at', 'region'] }],
      check_constraints: [{ name: 'ck_region', expression: "region IN ('EU', 'US')", columns: ['region'] }],
    },
    {
      entity_name: 'order_line',
      entity_type: 'TABLE',
      canvas_position_x: 300,
      canvas_position_y: 20,
      columns: [
        col('order_id', { is_foreign_key: true, references: 'orders.order_id' }),
        col('region', { is_foreign_key: true, references: 'orders.region' }),
      ],
      primary_key: [],
      unique_constraints: [],
      check_constraints: [],
    },
  ],
  relationships: [
    { from: 'order_line', from_columns: ['region', 'order_id'], to: 'orders',
      to_columns: ['region', 'order_id'], name: 'fk_line', cardinality: 'N:1' },
    { from: 'order_line', from_columns: [], to: 'orders', to_columns: [], name: null, cardinality: 'N:1' },
  ],
};

/** What saving it back must send: the lists, and no derived flag. */
function expectedPayload() {
  const derived = ['is_primary_key', 'is_unique', 'check_expression', 'is_foreign_key', 'references'];
  return {
    entities: SERVED.entities.map((e) => ({
      entity_name: e.entity_name,
      entity_type: e.entity_type,
      description: null,
      grain: null,
      tier: null,
      freshness_sla: null,
      agg_time_column: e.agg_time_column ?? null,
      canvas_position_x: e.canvas_position_x,
      canvas_position_y: e.canvas_position_y,
      columns: e.columns.map((c) =>
        Object.fromEntries(Object.entries(c).filter(([k]) => !derived.includes(k))),
      ),
      primary_key: e.primary_key,
      unique_constraints: e.unique_constraints,
      check_constraints: e.check_constraints,
    })),
    relationships: SERVED.relationships,
  };
}

beforeEach(() => useCanvasStore.getState().reset());

describe('a loaded model saves back as the same graph', () => {
  it('sends the whole graph unchanged, lists and order included', () => {
    useCanvasStore.getState().loadModel(structuredClone(SERVED));
    expect(useCanvasStore.getState().getGraphPayload()).toEqual(expectedPayload());
  });

  it('negative control: the comparison sees a changed constraint name', () => {
    useCanvasStore.getState().loadModel(structuredClone(SERVED));
    const expected = expectedPayload();
    expected.entities[0]!.unique_constraints = [{ name: 'other', columns: ['placed_at', 'region'] }];
    expect(useCanvasStore.getState().getGraphPayload()).not.toEqual(expected);
  });

  it('negative control: the comparison sees a reordered key', () => {
    useCanvasStore.getState().loadModel(structuredClone(SERVED));
    const expected = expectedPayload();
    expected.entities[0]!.primary_key = ['order_id', 'region'];
    expect(useCanvasStore.getState().getGraphPayload()).not.toEqual(expected);
  });

  it('is not dirty after a load, and is after an edit, until saved', () => {
    const store = useCanvasStore.getState();
    store.loadModel(structuredClone(SERVED));
    expect(useCanvasStore.getState().dirty).toBe(false);
    store.updateColumn('orders', 'placed_at', { description: 'When.' });
    expect(useCanvasStore.getState().dirty).toBe(true);
    store.markSaved();
    expect(useCanvasStore.getState().dirty).toBe(false);
  });
});

describe('the column editor edits the lists through its flags', () => {
  const data = (): EntityNodeData => ({
    entity_name: 'orders',
    entity_type: 'FACT',
    columns: SERVED.entities[0]!.columns.map((c) => ({ ...c })),
    primary_key: ['region', 'order_id'],
    unique_constraints: [{ name: 'uq_placed', columns: ['placed_at', 'region'] }],
    check_constraints: [{ name: 'ck_region', expression: "region IN ('EU', 'US')", columns: ['region'] }],
  });

  it('keeps the key order and appends a newly flagged column', () => {
    const d = data();
    d.columns[2] = { ...d.columns[2]!, is_primary_key: true };
    expect(constraintLists(d).primary_key).toEqual(['region', 'order_id', 'placed_at']);
  });

  it('keeps a multi-column UNIQUE and a named CHECK whose expression is unchanged', () => {
    const lists = constraintLists(data());
    expect(lists.unique_constraints).toEqual([{ name: 'uq_placed', columns: ['placed_at', 'region'] }]);
    expect(lists.check_constraints).toEqual([
      { name: 'ck_region', expression: "region IN ('EU', 'US')", columns: ['region'] },
    ]);
  });

  it('an edited CHECK replaces the saved one', () => {
    const d = data();
    d.columns[1] = { ...d.columns[1]!, check_expression: "region = 'EU'" };
    expect(constraintLists(d).check_constraints).toEqual([
      { name: null, expression: "region = 'EU'", columns: ['region'] },
    ]);
  });

  it('never sends a derived flag', () => {
    const sent = columnPayload(col('x', { is_primary_key: true, references: 'a.b', is_unique: true }));
    expect(Object.keys(sent)).not.toContain('is_primary_key');
    expect(Object.keys(sent)).not.toContain('references');
    expect(Object.keys(sent)).not.toContain('is_unique');
  });

  it('a rename reaches every list', () => {
    expect(renameInLists(data(), 'region', 'zone')).toEqual({
      primary_key: ['zone', 'order_id'],
      unique_constraints: [{ name: 'uq_placed', columns: ['placed_at', 'zone'] }],
      check_constraints: [{ name: 'ck_region', expression: "region IN ('EU', 'US')", columns: ['zone'] }],
    });
  });
});

describe('relationships', () => {
  it('reads the older entity.column form as one column pair', () => {
    expect(relationshipToEdgeData({ from: 'a.b_id', to: 'b.id', cardinality: 'N:1' })).toEqual({
      cardinality: 'N:1', from_ref: 'a', to_ref: 'b', from_columns: ['b_id'], to_columns: ['id'], name: null,
    });
  });

  it('connecting two entities adds nothing until the columns are chosen', () => {
    const store = useCanvasStore.getState();
    store.loadModel(structuredClone(SERVED));
    const before = useCanvasStore.getState().edges.length;
    store.onConnect({ source: 'order_line', target: 'orders', sourceHandle: null, targetHandle: null });
    expect(useCanvasStore.getState().edges).toHaveLength(before);
    expect(useCanvasStore.getState().pendingConnection).toEqual({
      source: 'order_line', target: 'orders', edgeId: null });
    store.cancelConnection();
    expect(useCanvasStore.getState().edges).toHaveLength(before);

    store.onConnect({ source: 'order_line', target: 'orders', sourceHandle: null, targetHandle: null });
    store.connectColumns(['order_id'], ['order_id']);
    const added = useCanvasStore.getState().edges.at(-1)!;
    expect(added.data).toMatchObject({ from_ref: 'order_line', to_ref: 'orders',
      from_columns: ['order_id'], to_columns: ['order_id'] });
  });

  it('an unresolved relationship is given its columns in place', () => {
    const store = useCanvasStore.getState();
    store.loadModel(structuredClone(SERVED));
    const unresolved = useCanvasStore.getState().edges[1]!;
    expect(unresolved.style).toBeDefined(); // drawn as unresolved
    store.editEdgeColumns(unresolved.id);
    store.connectColumns(['order_id'], ['order_id']);
    const edges = useCanvasStore.getState().edges;
    expect(edges).toHaveLength(2);
    expect(edges[1]!.data?.from_columns).toEqual(['order_id']);
    expect(edges[1]!.style).toBeUndefined();
  });
});
