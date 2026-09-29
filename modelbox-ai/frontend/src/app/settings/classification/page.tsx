'use client';

/**
 * Classification scale settings (Sprint 8 Step 4b).
 *
 * Each workspace has one scale, least to most sensitive, four levels by
 * default. A workspace ADMIN adds, renames, moves and deletes levels. Columns
 * hold a level by id, so a rename changes every use at once; a level any
 * column uses cannot be deleted, and the server says how many use it. PII type
 * is a separate field, set on the column.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

import {
  addClassificationLevel,
  deleteClassificationLevel,
  getClassificationScale,
  listWorkspaces,
  updateClassificationLevel,
} from '@/lib/api';
import { ErrorState, LoadingState, StatusText } from '@/components/ui';
import { errMessage, errorKind } from '@/lib/errors';
import type { ErrorKind } from '@/lib/errors';
import { useAuthStatus, useAuthStore } from '@/store/authStore';
import { color, radius, space, type } from '@/styles/tokens';
import type { ClassificationScale, WorkspaceInfo } from '@/types/schema';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready' }
  | { status: 'failed'; kind: ErrorKind; message: string };

const EDITORS = new Set(['OWNER', 'ADMIN']);

export default function ClassificationPage() {
  const openModal = useAuthStore((s) => s.openModal);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const authStatus = useAuthStatus();
  const signedIn = authStatus === 'signed-in';

  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [scale, setScale] = useState<ClassificationScale | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [newLevel, setNewLevel] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const failed = useCallback((e: unknown) => {
    setLoad({
      status: 'failed',
      kind: errorKind(e),
      message: errMessage(e, 'The classification scale could not be loaded.'),
    });
  }, []);

  const loadWorkspaces = useCallback(async () => {
    setLoad({ status: 'loading' });
    try {
      const listed = await listWorkspaces();
      setWorkspaces(listed);
      const chosen =
        listed.find((w) => w.workspace_id === activeWorkspaceId)?.workspace_id ?? listed[0]?.workspace_id ?? null;
      setWorkspaceId((current) => current ?? chosen);
      if (!chosen) setLoad({ status: 'ready' });
    } catch (e) {
      failed(e);
    }
  }, [activeWorkspaceId, failed]);

  const loadScale = useCallback(
    async (id: string) => {
      setLoad({ status: 'loading' });
      try {
        setScale(await getClassificationScale(id));
        setLoad({ status: 'ready' });
      } catch (e) {
        failed(e);
      }
    },
    [failed],
  );

  useEffect(() => {
    if (signedIn) void loadWorkspaces();
  }, [signedIn, loadWorkspaces]);

  useEffect(() => {
    if (signedIn && workspaceId) void loadScale(workspaceId);
  }, [signedIn, workspaceId, loadScale]);

  const refresh = () => (workspaceId ? loadScale(workspaceId) : loadWorkspaces());

  const role = workspaces.find((w) => w.workspace_id === workspaceId)?.role ?? '';
  const canEdit = EDITORS.has(role);

  async function run(action: () => Promise<ClassificationScale | void>) {
    if (!workspaceId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      setScale(result ?? (await getClassificationScale(workspaceId)));
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const name = newLevel.trim();
    if (!name || !workspaceId) return;
    void run(async () => {
      const result = await addClassificationLevel(workspaceId, name);
      setNewLevel('');
      return result;
    });
  }

  if (authStatus === 'unknown') {
    return (
      <main style={page}>
        <h1 style={heading}>Classification</h1>
        <LoadingState label="Checking your session…" />
      </main>
    );
  }

  return (
    <main style={page}>
      <Link href="/" style={backLink}>
        ← ModelBox AI
      </Link>
      <h1 style={heading}>Classification scale</h1>
      <p style={lede}>
        The levels a column can be classified at in this workspace, least to most sensitive.
        Renaming a level renames it on every column that uses it; a level in use cannot be
        deleted. PII type is set on each column, separately.
      </p>

      {!signedIn && (
        <div style={panel}>
          <p style={{ margin: 0, color: color.neutral[600] }}>Sign in to see the classification scale.</p>
          <button type="button" onClick={openModal} style={primaryBtn}>
            Sign in
          </button>
        </div>
      )}

      {signedIn && load.status === 'loading' && <LoadingState label="Loading the scale…" />}
      {signedIn && load.status === 'failed' && (
        <ErrorState kind={load.kind} title="The classification scale could not be loaded" onRetry={() => void refresh()}>
          {load.message}
        </ErrorState>
      )}

      {signedIn && load.status === 'ready' && (
        <>
          {workspaces.length > 1 && (
            <label style={field}>
              <span style={label}>Workspace</span>
              <select
                value={workspaceId ?? ''}
                onChange={(e) => setWorkspaceId(e.target.value)}
                style={input}
              >
                {workspaces.map((w) => (
                  <option key={w.workspace_id} value={w.workspace_id}>
                    {w.name} ({w.role})
                  </option>
                ))}
              </select>
            </label>
          )}

          {!canEdit && (
            <p style={lede}>Only a workspace owner or admin can change the scale.</p>
          )}

          <ol style={list} aria-label="Classification levels">
            {(scale?.levels ?? []).map((level, index, levels) => (
              <li key={level.level_id} style={row}>
                {canEdit ? (
                  <input
                    key={`${level.level_id}-${level.name}`}
                    aria-label={`Name of level ${level.rank}`}
                    defaultValue={level.name}
                    onBlur={(e) => {
                      const name = e.target.value.trim();
                      if (name && name !== level.name && workspaceId) {
                        void run(() => updateClassificationLevel(workspaceId, level.level_id, { name }));
                      }
                    }}
                    style={{ ...input, flex: 1 }}
                  />
                ) : (
                  <span style={{ flex: 1 }}>{level.name}</span>
                )}
                <span style={meta}>
                  {level.columns_using === 1 ? '1 column' : `${level.columns_using} columns`}
                </span>
                {canEdit && (
                  <>
                    <button
                      type="button"
                      aria-label={`Move ${level.name} down the scale`}
                      disabled={busy || index === 0}
                      onClick={() =>
                        workspaceId &&
                        void run(() => updateClassificationLevel(workspaceId, level.level_id, { rank: level.rank - 1 }))
                      }
                      style={smallBtn}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${level.name} up the scale`}
                      disabled={busy || index === levels.length - 1}
                      onClick={() =>
                        workspaceId &&
                        void run(() => updateClassificationLevel(workspaceId, level.level_id, { rank: level.rank + 1 }))
                      }
                      style={smallBtn}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      disabled={busy || level.columns_using > 0}
                      title={
                        level.columns_using > 0
                          ? 'In use: reclassify its columns before deleting it'
                          : 'Delete this level'
                      }
                      onClick={() =>
                        workspaceId && void run(() => deleteClassificationLevel(workspaceId, level.level_id))
                      }
                      style={smallBtn}
                    >
                      Delete
                    </button>
                  </>
                )}
              </li>
            ))}
          </ol>

          {canEdit && (
            <form onSubmit={handleAdd} style={{ ...row, marginTop: space.md }}>
              <input
                aria-label="New level"
                value={newLevel}
                onChange={(e) => setNewLevel(e.target.value)}
                placeholder="A new, most sensitive level"
                style={{ ...input, flex: 1 }}
              />
              <button type="submit" disabled={busy || !newLevel.trim()} style={primaryBtn}>
                Add level
              </button>
            </form>
          )}
        </>
      )}

      {error && (
        <div style={{ marginTop: space.lg }}>
          <StatusText tone="breaking">{error}</StatusText>
        </div>
      )}
    </main>
  );
}

const page: React.CSSProperties = { maxWidth: 820, margin: '0 auto', padding: `${space.xxl}px ${space.xl}px` };

const heading: React.CSSProperties = {
  fontSize: type.h2.size,
  fontWeight: type.h2.weight,
  marginTop: space.sm,
};

const lede: React.CSSProperties = { color: color.neutral[600], marginTop: space.xs };

const backLink: React.CSSProperties = { color: color.blue, fontWeight: type.uiXSmall.weight, textDecoration: 'none' };

const panel: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.md,
  marginTop: space.lg,
  padding: space.lg,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: radius.lg,
  background: color.neutral[50],
};

const list: React.CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: `${space.lg}px 0 0`,
  display: 'flex',
  flexDirection: 'column',
  gap: space.sm,
};

const row: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: space.sm,
  padding: `${space.sm}px ${space.md}px`,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: radius.lg,
  background: color.white,
};

const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: space.xs, marginTop: space.lg };

const label: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[600],
};

const meta: React.CSSProperties = { fontSize: type.caption.size, color: color.neutral[500] };

const input: React.CSSProperties = {
  padding: `${space.xs}px ${space.sm}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: type.uiSmall.size,
};

const primaryBtn: React.CSSProperties = {
  padding: `${space.sm}px ${space.md}px`,
  borderRadius: radius.md,
  border: 'none',
  background: color.blue,
  color: color.white,
  fontWeight: type.uiXSmall.weight,
  cursor: 'pointer',
};

const smallBtn: React.CSSProperties = {
  padding: `${space.xs}px ${space.sm}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  background: color.white,
  fontSize: type.uiXSmall.size,
  cursor: 'pointer',
};
