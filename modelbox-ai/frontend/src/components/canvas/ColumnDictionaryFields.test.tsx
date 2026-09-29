/**
 * The column's dictionary fields (Sprint 8 Step 4b): each edit reaches the
 * column in the store, permissible values are a list, the classification
 * choices are the workspace's levels, and "not assessed" is not "no".
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import type { Column } from '@/types/schema';

import ColumnDictionaryFields, { parsePermissibleValues } from './ColumnDictionaryFields';

const api = vi.hoisted(() => ({ getClassificationScale: vi.fn() }));
vi.mock('@/lib/api', () => api);

const COLUMN: Column = {
  name: 'region', data_type: 'VARCHAR(8)', is_primary_key: false, is_foreign_key: false, is_pii: false,
  is_metric: false,
};

function column(): Column {
  return useCanvasStore.getState().nodes[0]!.data.columns[0]!;
}

function renderFields() {
  return render(<ColumnDictionaryFields entityName="orders" column={column()} />);
}

beforeEach(() => {
  api.getClassificationScale.mockReset();
  api.getClassificationScale.mockResolvedValue({
    workspace_id: 'w1', scale_id: 's1', name: 'Sensitivity',
    levels: [{ level_id: 'l1', name: 'Public', rank: 1, columns_using: 0 },
      { level_id: 'l3', name: 'Confidential', rank: 3, columns_using: 0 }],
  });
  useCanvasStore.getState().reset();
  useCanvasStore.getState().loadModel({
    model_id: 'm1', paradigm: '3NF', suggested_metrics: [], relationships: [], workspace_id: 'w1',
    entities: [{ entity_name: 'orders', entity_type: 'TABLE', canvas_position_x: 0, canvas_position_y: 0,
      columns: [COLUMN] }],
  });
});

describe('parsePermissibleValues', () => {
  it('reads one value per line, dropping blanks', () => {
    expect(parsePermissibleValues('EU\n\n US \n')).toEqual(['EU', 'US']);
  });
  it('gives no list for no values', () => {
    expect(parsePermissibleValues('  \n')).toBeNull();
  });
});

describe('ColumnDictionaryFields', () => {
  it('offers the workspace levels and stores the chosen level by id', async () => {
    renderFields();
    const select = screen.getByLabelText('Classification');
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(api.getClassificationScale).toHaveBeenCalledWith('w1');
    fireEvent.change(select, { target: { value: 'l3' } });
    expect(column().classification_level_id).toBe('l3');
  });

  it('stores permissible values as a list', () => {
    renderFields();
    const area = screen.getByLabelText('Permissible values (one per line)');
    fireEvent.change(area, { target: { value: 'EU\nUS' } });
    fireEvent.blur(area);
    expect(column().permissible_values).toEqual(['EU', 'US']);
  });

  it('keeps "not assessed" apart from "no"', () => {
    renderFields();
    const cde = screen.getByLabelText('Critical data element');
    fireEvent.change(cde, { target: { value: 'no' } });
    expect(column().critical_data_element).toBe(false);
    fireEvent.change(cde, { target: { value: '' } });
    expect(column().critical_data_element).toBeNull();
  });

  it('stores the definition, business name, unit and source', () => {
    renderFields();
    fireEvent.change(screen.getByLabelText('Definition'), { target: { value: 'Sales region of the order.' } });
    fireEvent.change(screen.getByLabelText('Business name'), { target: { value: 'Region' } });
    fireEvent.change(screen.getByLabelText('Unit'), { target: { value: 'each' } });
    fireEvent.change(screen.getByLabelText('Authoritative source'), { target: { value: 'ERP' } });
    expect([column().description, column().business_name, column().unit, column().authoritative_source])
      .toEqual(['Sales region of the order.', 'Region', 'each', 'ERP']);
  });
});
