/**
 * The drift report panel (Sprint 8 Step 7): upload the deployed schema's DDL,
 * see each drift with its class and rule, the verified-field flag, the
 * unreconciled warning first, and possible renames as hints.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';

import DriftPanel from './DriftPanel';

const api = vi.hoisted(() => ({ driftReport: vi.fn(), listImportDialects: vi.fn() }));
vi.mock('@/lib/api', () => api);

const SOURCE = { label: 'Design', name: 'hr', model_id: 'm1', version: 3, imported_at: null, dialect: 'oracle',
  reconciliation: 'reconciled', statement: 'reconciled: the file\'s own counts match what was imported' };

function report(warnings: string[] = []) {
  return {
    report: 'Drift report', warnings,
    design: SOURCE,
    deployed: { ...SOURCE, label: 'Deployed', name: 'hr.sql', version: null, imported_at: '2026-09-29T18:00:00+00:00' },
    summary: { breaking: 1, 'non-breaking': 0, informational: 0, total: 1, verified_fields_affected: 1 },
    drifts: [{ kind: 'type_changed', table: 'JOBS', column: 'JOB_TITLE', columns: [], before: 'VARCHAR(35)',
      after: 'VARCHAR(32)', class: 'breaking', rule: 'D7', rule_text: 'A type is narrowed.',
      verified_fields_affected: ['JOBS.JOB_TITLE.data_type'], flag: 'verified field affected by drift' }],
    possible_renames: [{ table: 'LOCATIONS', removed: 'STREET_ADDRESS', added: 'ADDRESS_LINE', type: 'VARCHAR(40)',
      position: 2 }],
  };
}

async function compare() {
  render(<DriftPanel onClose={() => {}} />);
  await screen.findByRole('option', { name: 'Oracle' });
  const input = screen.getByLabelText('Deployed schema DDL file');
  fireEvent.change(input, { target: { files: [new File(['CREATE TABLE t (a int);'], 'hr.sql')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Compare' }));
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listImportDialects.mockResolvedValue([{ dialect: 'oracle', label: 'Oracle', evidence: '', tool: '' }]);
  useCanvasStore.setState({ modelId: 'm1' });
});

describe('DriftPanel', () => {
  it('lists each drift with its class, rule and the verified-field flag', async () => {
    api.driftReport.mockResolvedValue(report());
    await compare();
    await waitFor(() => expect(api.driftReport).toHaveBeenCalledWith('m1', expect.any(File), 'oracle'));
    const result = await screen.findByLabelText('Drift report result');
    const row = within(result).getByRole('row', { name: /JOBS\.JOB_TITLE/ });
    expect(row).toHaveTextContent('breaking');
    expect(row).toHaveTextContent('D7');
    expect(row).toHaveTextContent('verified field affected by drift: JOBS.JOB_TITLE.data_type');
    expect(result).toHaveTextContent('LOCATIONS: STREET_ADDRESS removed and ADDRESS_LINE added');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('warns first when an import is unreconciled', async () => {
    api.driftReport.mockResolvedValue(report(['Deployed is an unreconciled import.']));
    await compare();
    const result = await screen.findByLabelText('Drift report result');
    expect(result.firstElementChild).toHaveAttribute('role', 'alert');
    expect(result.firstElementChild).toHaveTextContent('Unreconciled import. Deployed is an unreconciled import.');
  });
});
