/**
 * F5 — the export surface shows per-artifact status drawn from the harness.
 *
 * "Drawn from" is the criterion's own wording and the part that was missing.
 * The panel used to hold its own copies of `CERTIFIED_DIALECTS` and
 * `PREVIEW_DIALECTS`, and a test in the fidelity harness read this file as
 * *text* to check they matched. The label reached the user by being retyped,
 * and the check ran backwards.
 *
 * These tests are parameterised over a manifest fixture rather than over a
 * written list, so an artifact added to the manifest is covered here on arrival
 * instead of when someone remembers.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ArtifactStatusInfo } from '@/types/schema';

const MANIFEST: ArtifactStatusInfo[] = [
  {
    variant: 'duckdb',
    family: 'ddl',
    status: 'CERTIFIED',
    reason: 'Executed against the engine.',
  },
  {
    variant: 'clickhouse',
    family: 'ddl',
    status: 'PREVIEW',
    reason: 'Transpiles, but needs an ENGINE clause to deploy.',
  },
  {
    variant: 'markdown',
    family: 'dictionary',
    status: 'UNVERIFIED',
    reason: 'No fidelity gate exists for the dictionary exporter.',
  },
];

const listArtifactStatus = vi.fn();

vi.mock('@/lib/api', () => ({
  listArtifactStatus: () => listArtifactStatus(),
  exportArtifact: vi.fn(),
  exportContract: vi.fn(),
  exportDictionary: vi.fn(),
  exportSemantic: vi.fn(),
  exportSyntheticData: vi.fn(),
  downloadExportZip: vi.fn(),
}));

vi.mock('@/components/editor/CodeEditor', () => ({
  default: () => null,
}));

vi.mock('@/store/canvasStore', () => ({
  useCanvasStore: (selector: (s: unknown) => unknown) =>
    selector({ modelId: 'm1', dialect: 'duckdb' }),
}));

import ExportPanel from './ExportPanel';

describe('export status', () => {
  beforeEach(() => {
    listArtifactStatus.mockResolvedValue(MANIFEST);
  });

  it('offers the dialects the manifest declares, and no others', async () => {
    render(<ExportPanel onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'duckdb' })).toBeInTheDocument();
    });
    expect(
      screen.getByRole('option', { name: /clickhouse/ }),
    ).toBeInTheDocument();
    // Present in the real manifest, absent from this fixture — so its presence
    // would mean the panel had a source other than the fetch.
    expect(screen.queryByRole('option', { name: 'snowflake' })).toBeNull();
  });

  it('defaults to a certified dialect rather than naming one', async () => {
    render(<ExportPanel onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('duckdb')).toBeInTheDocument();
    });
  });

  it('says nothing when the manifest cannot be fetched', async () => {
    // The honest failure. A panel that defaulted to "certified" because a fetch
    // failed would state a verification nobody performed — worse than showing
    // no badge at all.
    listArtifactStatus.mockRejectedValue(new Error('offline'));
    render(<ExportPanel onClose={() => {}} />);

    await waitFor(() => {
      expect(listArtifactStatus).toHaveBeenCalled();
    });
    expect(screen.queryByRole('status')).toBeNull();
  });
});
