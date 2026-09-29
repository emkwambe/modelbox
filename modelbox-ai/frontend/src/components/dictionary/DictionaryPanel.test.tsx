/**
 * The dictionary review (Sprint 8 Step 7): counts, statuses, the Verify
 * control for an approver only, and the three conditions shown for each
 * result with the reason a refused field stayed pending.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';

import DictionaryPanel, { whyPending } from './DictionaryPanel';

const api = vi.hoisted(() => ({ listAttestations: vi.fn(), listWorkspaces: vi.fn(), verifyFields: vi.fn() }));
vi.mock('@/lib/api', () => api);

const FIELD = {
  entity: 'LOCATIONS', column: 'CITY', field: 'data_type', status: 'pending' as const,
  provenance: 'ddl', provenance_by: null, provenance_at: null, verified_by: null, verified_at: null,
};
const OTHER = { ...FIELD, column: 'POSTAL_CODE' };

function attestations(verified: number) {
  return {
    model_id: 'm1',
    summary: { verified, fields: 2, pending_review: 2 - verified, statement: `${verified} of 2 fields verified, ${2 - verified} pending review` },
    fields: [{ ...FIELD, status: verified ? 'verified' : 'pending' }, OTHER],
  };
}

function as(role: string) {
  api.listWorkspaces.mockResolvedValue([{ workspace_id: 'w1', name: 'W', role }]);
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  useCanvasStore.setState({ modelId: 'm1', workspaceId: 'w1' });
  api.listAttestations.mockResolvedValue(attestations(0));
});

describe('DictionaryPanel', () => {
  it('shows the counts and each status', async () => {
    as('APPROVER');
    render(<DictionaryPanel onClose={() => {}} />);
    expect(await screen.findByText('0 of 2 fields verified, 2 pending review')).toBeInTheDocument();
    expect(screen.getByLabelText('Status of LOCATIONS.CITY · data_type')).toHaveTextContent('pending review');
  });

  it('an approver verifies one field, and the counts change', async () => {
    as('APPROVER');
    api.verifyFields.mockResolvedValue({
      model_id: 'm1', summary: attestations(1).summary,
      results: [{ ...FIELD, status: 'verified', conditions: {
        reconciled_import: true, definition_failures: [], provenance: 'ddl', provenance_verifiable: true } }],
    });
    render(<DictionaryPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Verify LOCATIONS.CITY · data_type' }));
    await waitFor(() => expect(api.verifyFields).toHaveBeenCalledWith('m1', [
      { entity: 'LOCATIONS', column: 'CITY', field: 'data_type' }]));
    api.listAttestations.mockResolvedValue(attestations(1));
    const results = await screen.findByLabelText('Verification results');
    expect(within(results).getByText('Reconciled import: yes')).toBeInTheDocument();
    expect(within(results).getByText('Definition (ISO/IEC 11179-4): passes')).toBeInTheDocument();
  });

  it('a refused field says which conditions failed', async () => {
    as('OWNER');
    api.verifyFields.mockResolvedValue({
      model_id: 'm1', summary: attestations(0).summary,
      results: [{ ...FIELD, conditions: {
        reconciled_import: false, definition_failures: ['CIRCULAR'], provenance: null, provenance_verifiable: false } }],
    });
    render(<DictionaryPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select LOCATIONS.CITY · data_type' }));
    fireEvent.click(screen.getByRole('button', { name: 'Verify selected (1)' }));
    expect(await screen.findByText(/Stayed pending review because the model is not a reconciled import; its definition fails the ISO\/IEC 11179-4 rules: CIRCULAR; no provenance is recorded\./)).toBeInTheDocument();
  });

  it.each(['MEMBER', 'VIEWER'])('a %s sees no Verify control', async (role) => {
    as(role);
    render(<DictionaryPanel onClose={() => {}} />);
    expect(await screen.findByText('Only an approver, admin or owner can ask for fields to be verified.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Verify/ })).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});

describe('whyPending', () => {
  it('names an AI draft as provenance that cannot support verified', () => {
    expect(whyPending({ ...FIELD, conditions: {
      reconciled_import: true, definition_failures: [], provenance: 'ai_draft', provenance_verifiable: false } }))
      .toEqual(['its provenance (ai_draft) cannot support verified']);
  });
});
