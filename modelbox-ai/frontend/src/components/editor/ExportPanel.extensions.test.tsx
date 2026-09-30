/**
 * Sprint 9 Step 1a: the target's extensions are stated by the person
 * exporting, never assumed. The options appear only where the manifest says
 * the chosen dialect accepts them (PostgreSQL DDL), are off until checked,
 * and reach the API exactly as checked.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ArtifactStatusInfo } from '@/types/schema';

const MANIFEST: ArtifactStatusInfo[] = [
  {
    variant: 'postgres',
    family: 'ddl',
    status: 'CERTIFIED',
    reason: 'Applied to PostgreSQL.',
    options: ['target_has_ltree', 'target_has_postgis'],
  },
  { variant: 'duckdb', family: 'ddl', status: 'CERTIFIED', reason: 'Executed against the engine.' },
];

const listArtifactStatus = vi.fn();
const exportArtifact = vi.fn();

vi.mock('@/lib/api', () => ({
  listArtifactStatus: () => listArtifactStatus(),
  exportArtifact: (...args: unknown[]) => exportArtifact(...args),
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
  useCanvasStore: (selector: (s: unknown) => unknown) => selector({ modelId: 'm1' }),
}));

import ExportPanel from './ExportPanel';

describe('target extensions', () => {
  beforeEach(() => {
    listArtifactStatus.mockReset();
    listArtifactStatus.mockResolvedValue(MANIFEST);
    exportArtifact.mockReset();
    exportArtifact.mockResolvedValue({ files: { 'model_postgres.sql': '' } });
  });

  it('are off by default, and a generate sends none', async () => {
    render(<ExportPanel onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('postgres')).toBeInTheDocument();
    });
    expect(screen.getByRole('checkbox', { name: 'Target has ltree' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Target has PostGIS' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
    await waitFor(() => {
      expect(exportArtifact).toHaveBeenCalledWith('m1', 'ddl', 'postgres', {
        targetHasLtree: false,
        targetHasPostgis: false,
      });
    });
  });

  it('reach the API as checked', async () => {
    render(<ExportPanel onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('postgres')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Target has ltree' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Target has PostGIS' }));
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
    await waitFor(() => {
      expect(exportArtifact).toHaveBeenCalledWith('m1', 'ddl', 'postgres', {
        targetHasLtree: true,
        targetHasPostgis: true,
      });
    });
  });

  it('come from the manifest: a dialect it lists with no options offers none', async () => {
    listArtifactStatus.mockResolvedValue(MANIFEST.map((row) => ({ ...row, options: [] })));
    render(<ExportPanel onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('postgres')).toBeInTheDocument();
    });
    expect(screen.queryByRole('checkbox', { name: 'Target has ltree' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: 'Target has PostGIS' })).toBeNull();
  });

  it('are not offered for another dialect, and none is sent', async () => {
    render(<ExportPanel onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('postgres')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'SQL dialect' }), { target: { value: 'duckdb' } });
    expect(screen.queryByRole('checkbox', { name: 'Target has ltree' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Generate' }));
    await waitFor(() => {
      expect(exportArtifact).toHaveBeenCalledWith('m1', 'ddl', 'duckdb', {});
    });
  });
});
