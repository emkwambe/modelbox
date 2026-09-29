'use client';

/**
 * Models — every saved model the signed-in user can see, each reopening at
 * `/canvas/<id>` exactly as it was saved (Sprint 8 Step 3).
 *
 * Until this page, a model could be reached only straight after creating it:
 * the canvas held its id in memory, so a reload or a new tab lost it, and
 * `listModels` was used by the diff panel alone.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';

import { ErrorState, LoadingState } from '@/components/ui';
import { listModels } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { color, space } from '@/styles/tokens';
import type { ModelInfo } from '@/types/schema';

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listModels()
      .then((found) => live && setModels(found))
      .catch((e) => live && setError(errMessage(e, 'The models could not be loaded.')));
    return () => {
      live = false;
    };
  }, []);

  return (
    <main style={{ maxWidth: 880, margin: '0 auto', padding: space.xl }}>
      <h1>Models</h1>
      {error && <ErrorState title="Models unavailable">{error}</ErrorState>}
      {!error && models === null && <LoadingState label="Loading models…" />}
      {models !== null && models.length === 0 && (
        <p>
          No saved models yet. <Link href="/">Synthesize one</Link> or{' '}
          <Link href="/import">import a DDL file</Link>.
        </p>
      )}
      {models !== null && models.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Title</th>
              <th style={{ textAlign: 'left' }}>Paradigm</th>
              <th style={{ textAlign: 'left' }}>Dialect</th>
              <th style={{ textAlign: 'right' }}>Version</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.model_id} style={{ borderTop: `1px solid ${color.neutral[200]}` }}>
                <td style={{ padding: `${space.sm}px 0` }}>
                  <Link href={`/canvas/${m.model_id}`}>{m.title}</Link>
                </td>
                <td>{m.current_paradigm ?? '—'}</td>
                <td>{m.target_dialect}</td>
                <td style={{ textAlign: 'right' }}>{m.version_number}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
