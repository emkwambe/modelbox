/**
 * A model that arrives with no layout is laid out when it opens (Sprint 8
 * Step 7). A DDL import stores no positions, so every table came to the
 * canvas at the origin and was drawn as one pile. A model that was laid out
 * and saved opens exactly as it was saved.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { stackedAtOnePoint, useCanvasStore } from '@/store/canvasStore';
import type { Entity, SynthesizeResponse } from '@/types/schema';

function entity(name: string, x: number, y: number, columns = 3): Entity {
  return {
    entity_name: name,
    entity_type: 'TABLE',
    canvas_position_x: x,
    canvas_position_y: y,
    columns: Array.from({ length: columns }, (_, i) => ({
      name: `${name}_c${i}`, data_type: 'INTEGER', is_primary_key: i === 0, is_foreign_key: false,
      is_pii: false, is_metric: false,
    })),
    primary_key: [`${name}_c0`],
  };
}

function model(entities: Entity[]): SynthesizeResponse {
  return { model_id: 'm1', paradigm: '3NF', suggested_metrics: [], entities, relationships: [] };
}

const positions = () => useCanvasStore.getState().nodes.map((n) => `${n.position.x},${n.position.y}`);

beforeEach(() => {
  useCanvasStore.getState().reset();
});

describe('loadModel and layout', () => {
  it('lays out an imported model, whose tables all sit at the origin, and marks it unsaved', () => {
    useCanvasStore.getState().loadModel(model([entity('A', 0, 0), entity('B', 0, 0, 12), entity('C', 0, 0)]));
    expect(new Set(positions()).size).toBe(3);
    expect(stackedAtOnePoint(useCanvasStore.getState().nodes)).toBe(false);
    expect(useCanvasStore.getState().dirty).toBe(true);
  });

  it('keeps a saved layout exactly, and the model stays saved', () => {
    // The discriminating case: the rule must not re-lay out a placed model.
    useCanvasStore.getState().loadModel(model([entity('A', 0, 0), entity('B', 400, 0), entity('C', 0, 300)]));
    expect(positions()).toEqual(['0,0', '400,0', '0,300']);
    expect(useCanvasStore.getState().dirty).toBe(false);
  });

  it('leaves a one-table model where it is', () => {
    useCanvasStore.getState().loadModel(model([entity('A', 0, 0)]));
    expect(positions()).toEqual(['0,0']);
    expect(useCanvasStore.getState().dirty).toBe(false);
  });
});
