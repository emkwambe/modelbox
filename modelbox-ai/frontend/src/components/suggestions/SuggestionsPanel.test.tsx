/**
 * The suggestions panel (Sprint 9 Step 4): a guess is shown as a guess, with
 * its rule, anchor and evidence and no score for PII; a member decides; a
 * viewer sees no control; nothing is decided over unsaved canvas edits; the
 * time-column candidates are ranked with the audit column flagged.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import type { Suggestion } from '@/types/suggestion';

import SuggestionsPanel, { blocked, evidence } from './SuggestionsPanel';

const api = vi.hoisted(() => ({
  listSuggestions: vi.fn(),
  runSuggestions: vi.fn(),
  acceptSuggestion: vi.fn(),
  rejectSuggestion: vi.fn(),
  listWorkspaces: vi.fn(),
  getModel: vi.fn(),
}));
vi.mock('@/lib/api', () => api);

const EMAIL: Suggestion = {
  suggestion_id: 's1', kind: 'pii', entity: 'EMPLOYEES', column: 'EMAIL',
  suggested: { is_pii: true, pii_type: 'EMAIL' }, category: 'EMAIL', category_label: 'E-mail address',
  anchor: 'NIST SP 800-122 §2.2, address information', rule_name: 'pii.email.name', rule_source: 'builtin',
  signals: { rules: ['pii.email.name'], name: 'EMAIL', type: 'VARCHAR2(25)' }, confidence: null,
  provenance: 'heuristic', status: 'pending', stale: null, resolved_elsewhere: false,
  decided_by_email: null, decided_at: null,
};

function time(column: string, confidence: number, rank: number, audit: string | null): Suggestion {
  return {
    ...EMAIL, suggestion_id: `t-${column}`, kind: 'agg_time_column', entity: 'SalesOrderHeader', column,
    suggested: { agg_time_column: column }, category: 'agg_time_column', category_label: 'aggregation time column',
    anchor: 'a date or time column of the entity', rule_name: 'time.temporal_column', confidence,
    signals: { rules: ['time.temporal_column'], type: 'DATETIME', not_null: true, event_word: null,
      audit_word: audit, likely_audit_column: audit !== null, flag: audit ? 'likely an audit column' : null,
      rank, of: 4 },
  };
}

const HEADER = [time('OrderDate', 0.9, 1, null), time('DueDate', 0.7, 2, null), time('ShipDate', 0.5, 3, null),
  time('ModifiedDate', 0.1, 4, 'modified')];

function response(suggestions: Suggestion[]) {
  const pending = suggestions.filter((s) => s.status === 'pending').length;
  return {
    model_id: 'm1', ruleset_digest: 'd', suggestions,
    counts: { pending, accepted: 0, rejected: 0, superseded: 0, statement: `${pending} suggestions pending review` },
  };
}

function as(role: string) {
  api.listWorkspaces.mockResolvedValue([{ workspace_id: 'w1', name: 'W', role }]);
}

const loadModel = vi.fn();

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  loadModel.mockReset();
  useCanvasStore.setState({ modelId: 'm1', workspaceId: 'w1', dirty: false, loadModel });
  api.listSuggestions.mockResolvedValue(response([EMAIL, ...HEADER]));
});

describe('SuggestionsPanel', () => {
  it('shows a PII guess as a guess: rule, anchor, evidence, and no score', async () => {
    as('MEMBER');
    render(<SuggestionsPanel onClose={() => {}} />);
    expect(await screen.findByText('5 suggestions pending review')).toBeInTheDocument();
    const row = screen.getByLabelText('Suggestion for EMPLOYEES.EMAIL');
    expect(within(row).getByLabelText('Status of EMPLOYEES.EMAIL')).toHaveTextContent('suggested, not confirmed');
    expect(within(row).getByText(/Rule pii\.email\.name · NIST SP 800-122 §2\.2/)).toBeInTheDocument();
    expect(within(row).getByText(/column name "EMAIL"; type VARCHAR2\(25\)/)).toBeInTheDocument();
    expect(within(row).queryByLabelText('Confidence of EMPLOYEES.EMAIL')).toBeNull();
    expect(row).not.toHaveTextContent(/confidence|%/i);
  });

  it('a member accepts; the canvas reloads the saved model', async () => {
    as('MEMBER');
    api.acceptSuggestion.mockResolvedValue(response([{ ...EMAIL, status: 'accepted', decided_by_email: 'm@x' }]));
    api.getModel.mockResolvedValue({ model_id: 'm1', entities: [], relationships: [] });
    render(<SuggestionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Accept EMPLOYEES.EMAIL' }));
    await waitFor(() => expect(api.acceptSuggestion).toHaveBeenCalledWith('m1', 's1'));
    await waitFor(() => expect(loadModel).toHaveBeenCalledWith({ model_id: 'm1', entities: [], relationships: [] }));
  });

  it('an accept whose canvas refresh fails says the canvas is out of date', async () => {
    as('MEMBER');
    api.acceptSuggestion.mockResolvedValue(response([{ ...EMAIL, status: 'accepted', decided_by_email: 'm@x' }]));
    api.getModel.mockRejectedValue(new Error('network'));
    render(<SuggestionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Accept EMPLOYEES.EMAIL' }));
    expect(await screen.findByText(/Reload the page before saving the canvas/)).toBeInTheDocument();
    expect(loadModel).not.toHaveBeenCalled();
  });

  it('a reject leaves the canvas alone', async () => {
    as('MEMBER');
    api.rejectSuggestion.mockResolvedValue(response([{ ...EMAIL, status: 'rejected', decided_by_email: 'm@x' }]));
    render(<SuggestionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reject EMPLOYEES.EMAIL' }));
    await waitFor(() => expect(api.rejectSuggestion).toHaveBeenCalledWith('m1', 's1'));
    expect(api.getModel).not.toHaveBeenCalled();
    expect(loadModel).not.toHaveBeenCalled();
  });

  it('a viewer sees no control', async () => {
    as('VIEWER');
    render(<SuggestionsPanel onClose={() => {}} />);
    expect(await screen.findByText(/Only a member, approver, admin or owner/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Accept|Reject)/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Run the rules' })).toBeNull();
  });

  it('nothing is decided over unsaved canvas edits', async () => {
    as('MEMBER');
    useCanvasStore.setState({ dirty: true });
    render(<SuggestionsPanel onClose={() => {}} />);
    expect(await screen.findByText(/Save the canvas before deciding/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept EMPLOYEES.EMAIL' })).toBeDisabled();
  });

  it('a stale suggestion says why and offers no decision', async () => {
    as('MEMBER');
    api.listSuggestions.mockResolvedValue(response([{ ...EMAIL, stale: 'column EMPLOYEES.EMAIL is no longer in the model' }]));
    render(<SuggestionsPanel onClose={() => {}} />);
    expect(await screen.findByText(/Cannot be decided: column EMPLOYEES\.EMAIL is no longer in the model\./))
      .toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept EMPLOYEES.EMAIL' })).toBeNull();
  });

  it('time columns: every candidate ranked, the audit one flagged', async () => {
    as('MEMBER');
    render(<SuggestionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Time column' }));
    const list = screen.getByLabelText('Time column candidates for SalesOrderHeader');
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual([
      'Suggestion for SalesOrderHeader.OrderDate', 'Suggestion for SalesOrderHeader.DueDate',
      'Suggestion for SalesOrderHeader.ShipDate', 'Suggestion for SalesOrderHeader.ModifiedDate']);
    expect(within(list).getByLabelText('Confidence of SalesOrderHeader.ModifiedDate'))
      .toHaveTextContent('rank 4 of 4 · confidence 0.1');
    expect(within(list).getByLabelText('Flag on SalesOrderHeader.ModifiedDate')).toHaveTextContent('likely an audit column');
    expect(within(list).queryByLabelText('Flag on SalesOrderHeader.OrderDate')).toBeNull();
    expect(screen.getByText(/it is not a measured probability/)).toBeInTheDocument();
  });

  it('running the rules shows what they stored', async () => {
    as('MEMBER');
    api.listSuggestions.mockResolvedValue(response([]));
    api.runSuggestions.mockResolvedValue({ ...response([EMAIL]), created: 1, superseded_now: 0 });
    render(<SuggestionsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Run the rules' }));
    expect(await screen.findByText('1 suggestions pending review')).toBeInTheDocument();
  });
});

describe('evidence and blocked', () => {
  it('say what a time candidate read, and why a resolved one cannot be decided', () => {
    const modified = time('ModifiedDate', 0.1, 4, 'modified');
    expect(evidence(modified)).toEqual(['type DATETIME', 'never NULL',
      'name reads as a row-audit timestamp ("modified")']);
    expect(blocked({ ...EMAIL, resolved_elsewhere: true })).toBe('the field already holds a value');
    expect(blocked(EMAIL)).toBeNull();
  });
});
