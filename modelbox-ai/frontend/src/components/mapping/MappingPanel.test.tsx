import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MappingPanel from './MappingPanel';
import { useCanvasStore } from '@/store/canvasStore';
import type { MappingReport } from '@/types/mapping';

const api = vi.hoisted(() => ({
  acceptProposal: vi.fn(),
  authorEntry: vi.fn(),
  createMapping: vi.fn(),
  exportMapping: vi.fn(),
  getLineage: vi.fn(),
  getMapping: vi.fn(),
  getModel: vi.fn(),
  listMappings: vi.fn(),
  listModels: vi.fn(),
  listWorkspaces: vi.fn(),
  proposeMappings: vi.fn(),
  rejectProposal: vi.fn(),
  removeEntry: vi.fn(),
}));
vi.mock('@/lib/api', () => api);

const DOC = {
  document_id: 'd1', workspace_id: 'w1', title: 'HR to dim', target_model_id: 'm1', source_model_id: 's1',
  source_model_title: 'HR', source_system: null, target_system: null, version: 1, status: 'draft',
  created_by_email: 'member@example.com', created_at: '2026-09-30T00:00:00Z',
};

function report(overrides: Partial<MappingReport> = {}): MappingReport {
  return {
    document: DOC,
    completeness: {
      total: 2, mapped: 0, explicitly_unmapped: 0, pending: 1, silent: 1, in_drift: 0, orphaned: 0,
      accepted_entries: 0, pending_proposals: 1, complete: false,
      summary: '0 of 2 target columns mapped, 0 explicitly unmapped, 1 silent; 1 pending review (1 proposals), 0 in drift; 0 accepted entries',
    },
    rows: [
      {
        target: { entity: 'dim_employee', column: 'email', exists: true, type: 'VARCHAR(25)' },
        status: 'pending', entry: null, drift: [],
        proposals: [{ proposal_id: 'p1', sources: [{ entity: 'EMPLOYEES', column: 'EMAIL', exists: true }],
                      name_similarity: 0.93, type_compatibility: 1, confidence: 0.951, method: 'name-type', method_version: '1' }],
      },
      {
        target: { entity: 'dim_employee', column: 'load_batch', exists: true, type: 'VARCHAR(20)' },
        status: 'silent', entry: null, drift: [], proposals: [],
      },
    ],
    ...overrides,
  };
}

function withRole(role: string) {
  api.listWorkspaces.mockResolvedValue([{ workspace_id: 'w1', name: 'W', role }]);
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  useCanvasStore.setState({ modelId: 'm1', workspaceId: 'w1' });
  api.listMappings.mockResolvedValue([DOC]);
  api.getMapping.mockResolvedValue(report());
  api.listModels.mockResolvedValue([{ model_id: 's1', workspace_id: 'w1', title: 'HR', target_dialect: 'postgres', version_number: 1 }]);
  api.getModel.mockResolvedValue({ entities: [{ entity_name: 'EMPLOYEES', columns: [{ name: 'EMAIL' }, { name: 'BATCH' }] }] });
});

describe('MappingPanel', () => {
  it('states completeness, and a pending proposal as pending with its scores', async () => {
    withRole('MEMBER');
    render(<MappingPanel onClose={() => {}} />);
    expect(await screen.findByRole('status')).toHaveTextContent('0 of 2 target columns mapped, 0 explicitly unmapped, 1 silent');
    expect(screen.getByLabelText('Completeness')).toHaveTextContent('Not complete');
    expect(screen.getByLabelText('Status of dim_employee.email')).toHaveTextContent('pending review');
    expect(screen.getByLabelText('Status of dim_employee.load_batch')).toHaveTextContent('silent');
    expect(screen.getByLabelText('Proposal for dim_employee.email')).toHaveTextContent(
      'EMPLOYEES.EMAIL · name 0.93 · type 1.00 · confidence 0.95');
  });

  it('accepts a proposal through the API, sending no decider', async () => {
    withRole('MEMBER');
    api.acceptProposal.mockResolvedValue(report());
    render(<MappingPanel onClose={() => {}} />);
    const proposal = await screen.findByLabelText('Proposal for dim_employee.email');
    await waitFor(() => expect(within(proposal).getByRole('button', { name: 'Accept' })).toBeInTheDocument());
    fireEvent.click(within(proposal).getByRole('button', { name: 'Accept' }));
    await waitFor(() => expect(api.acceptProposal).toHaveBeenCalledWith('d1', 'p1'));
    expect(api.acceptProposal.mock.calls[0]).toHaveLength(2);
  });

  it('writes an explicit unmapped entry for a silent column', async () => {
    withRole('MEMBER');
    api.authorEntry.mockResolvedValue(report());
    render(<MappingPanel onClose={() => {}} />);
    const kind = await screen.findByLabelText('Kind for dim_employee.load_batch');
    fireEvent.change(kind, { target: { value: 'constant' } });
    fireEvent.change(screen.getByLabelText('Rule for dim_employee.load_batch'), { target: { value: 'batch id' } });
    const entry = screen.getByLabelText('Entry for dim_employee.load_batch');
    fireEvent.click(within(entry).getByRole('button', { name: 'Save entry' }));
    await waitFor(() => expect(api.authorEntry).toHaveBeenCalledWith('d1', {
      target: { entity: 'dim_employee', column: 'load_batch' }, kind: 'constant', sources: [],
      fields: { rule_description: 'batch id' },
    }));
  });

  it('shows drift on an entry whose source column is gone', async () => {
    withRole('MEMBER');
    api.getMapping.mockResolvedValue(report({
      rows: [{
        target: { entity: 'dim_employee', column: 'email', exists: true },
        status: 'drift', drift: ['source column missing: EMPLOYEES.EMAIL'], proposals: [],
        entry: { entry_id: 'e1', mapping_key: 'M-0001', kind: 'mapped', revision: 1,
                 sources: [{ entity: 'EMPLOYEES', column: 'EMAIL', exists: false }], fields: {},
                 provenance_by: 'member@example.com', provenance_at: null },
      }],
    }));
    render(<MappingPanel onClose={() => {}} />);
    expect(await screen.findByRole('note')).toHaveTextContent('Drift: source column missing: EMPLOYEES.EMAIL');
    expect(screen.getByLabelText('Status of dim_employee.email')).toHaveTextContent('in drift');
  });

  it('gives a viewer no controls', async () => {
    withRole('VIEWER');
    render(<MappingPanel onClose={() => {}} />);
    await screen.findByText(/Only a member or above/);
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Propose mappings' })).toBeNull();
    expect(screen.queryByLabelText('Kind for dim_employee.load_batch')).toBeNull();
    // Control: the viewer still sees the document and can export it.
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });
});
