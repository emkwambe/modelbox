/**
 * The DDL import page: the dialects and their evidence come from the API, the
 * upload sends the file with its dialect and workspace, and the result says
 * whether the import reconciled.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/store/authStore';

import ImportPage from './page';

const api = vi.hoisted(() => ({
  getImportReport: vi.fn(),
  getModel: vi.fn(),
  importDdl: vi.fn(),
  listImportDialects: vi.fn(),
  listWorkspaces: vi.fn(),
}));

vi.mock('@/lib/api', () => api);
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const DIALECTS = [
  { dialect: 'oracle', label: 'Oracle', evidence: 'genuine export', tool: 'DBMS_METADATA.GET_DDL' },
  { dialect: 'snowflake', label: 'Snowflake', evidence: 'documentation-derived', tool: 'GET_DDL' },
];
const WORKSPACES = [{ workspace_id: 'w1', name: 'Bank A', role: 'MEMBER' }];
const COUNTS = {
  count: 7, columns: 35, primary_keys: 7, foreign_keys: 10, unique_constraints: 1,
  check_constraints: 2, table_descriptions: 7, column_descriptions: 35,
};
const NONE = Object.fromEntries(Object.keys(COUNTS).map((k) => [k, 0]));

function result(status: 'reconciled' | 'unreconciled') {
  return {
    model_id: 'm1',
    title: 'hr',
    status,
    entities: 7,
    relationships: 10,
    report: {
      file: 'hr.sql', dialect: 'oracle', evidence: 'genuine export', encoding: 'UTF-8 without BOM',
      status,
      failures: status === 'reconciled' ? [] : [
        { statement: 5, line: 25, head: 'create or replace HYBRID TABLE ACCOUNTS', reason: 'opaque Command' },
      ],
      not_imported: [],
      reconciliation: {
        source: { tables: COUNTS, partitions: NONE },
        imported: { tables: COUNTS, partitions: NONE },
        gaps: [],
      },
    },
  };
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listImportDialects.mockResolvedValue(DIALECTS);
  api.listWorkspaces.mockResolvedValue(WORKSPACES);
  useAuthStore.setState({ token: 'a-token', email: 'dev@modelbox.ai', activeWorkspaceId: null });
});

async function chooseFileAndSubmit() {
  const file = new File(['CREATE TABLE t (a int);'], 'hr.sql', { type: 'application/sql' });
  fireEvent.change(await screen.findByLabelText(/DDL file/), { target: { files: [file] } });
  const button = screen.getByRole('button', { name: 'Import' });
  // The page's own guard: nothing to submit until a file is chosen.
  expect(button).toBeEnabled();
  // Submitted directly: jsdom's constraint validation does not see a file set
  // through fireEvent, so clicking would stop at the required file input.
  fireEvent.submit(button.closest('form')!);
  return file;
}

describe('ImportPage', () => {
  it('offers the dialects the API lists, each with its evidence', async () => {
    render(<ImportPage />);
    expect(await screen.findByRole('option', { name: 'Oracle (genuine export)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Snowflake (documentation-derived)' })).toBeInTheDocument();
  });

  it('uploads the file with its dialect and workspace', async () => {
    api.importDdl.mockResolvedValue(result('reconciled'));
    render(<ImportPage />);
    const file = await chooseFileAndSubmit();
    await waitFor(() =>
      expect(api.importDdl).toHaveBeenCalledWith({ workspaceId: 'w1', file, dialect: 'oracle', title: undefined }),
    );
    expect(await screen.findByText(/^Reconciled: 7 tables and 10 relationships/)).toBeInTheDocument();
  });

  it('says an unreconciled import is unreconciled and lists why', async () => {
    api.importDdl.mockResolvedValue(result('unreconciled'));
    render(<ImportPage />);
    await chooseFileAndSubmit();
    expect(await screen.findByRole('alert')).toHaveTextContent(/^Unreconciled/);
    expect(screen.getByText(/create or replace HYBRID TABLE ACCOUNTS/)).toBeInTheDocument();
  });

  it('reports a failed upload instead of a result', async () => {
    api.importDdl.mockRejectedValue(
      Object.assign(new Error('status 413'), { response: { status: 413, data: { detail: 'the file is larger than 10 MB' } } }),
    );
    render(<ImportPage />);
    await chooseFileAndSubmit();
    expect(await screen.findByRole('alert')).toHaveTextContent('the file is larger than 10 MB');
  });

  it('offers no import until a file is chosen', async () => {
    render(<ImportPage />);
    expect(await screen.findByRole('button', { name: 'Import' })).toBeDisabled();
  });

  it('asks for nothing while signed out', () => {
    useAuthStore.setState({ token: null, email: null });
    render(<ImportPage />);
    expect(api.listImportDialects).not.toHaveBeenCalled();
  });
});
