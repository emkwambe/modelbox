'use client';

/**
 * Workspace members (Sprint 8 Step 6).
 *
 * An OWNER or ADMIN adds an existing appliance user by email, changes a
 * member's role, and removes a member. Users themselves are created by OIDC
 * sign-in, SCIM or `create-owner`; an email with no user is refused, and the
 * server's message says so. The server enforces every rule — no role above
 * your own, an ADMIN cannot make an OWNER, the last OWNER stays — and this
 * page shows its refusals as they come; the role choices it offers are only a
 * convenience.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

import { addMember, changeMemberRole, listMembers, listWorkspaces, removeMember } from '@/lib/api';
import { ErrorState, LoadingState, StatusText } from '@/components/ui';
import { errMessage, errorKind } from '@/lib/errors';
import type { ErrorKind } from '@/lib/errors';
import { ROLE_LADDER, capsUpTo } from '@/lib/roles';
import { useAuthStatus, useAuthStore } from '@/store/authStore';
import { color, radius, space, type } from '@/styles/tokens';
import type { MemberInfo, WorkspaceInfo, WorkspaceRole } from '@/types/schema';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready' }
  | { status: 'failed'; kind: ErrorKind; message: string };

export default function MembersPage() {
  const openModal = useAuthStore((s) => s.openModal);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const authStatus = useAuthStatus();
  const signedIn = authStatus === 'signed-in';

  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [members, setMembers] = useState<MemberInfo[]>([]);
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [email, setEmail] = useState('');
  const [newRole, setNewRole] = useState<WorkspaceRole>('VIEWER');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const failed = useCallback((e: unknown) => {
    setLoad({ status: 'failed', kind: errorKind(e), message: errMessage(e, 'The members could not be loaded.') });
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

  const loadMembers = useCallback(
    async (id: string) => {
      setLoad({ status: 'loading' });
      try {
        setMembers(await listMembers(id));
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
    if (signedIn && workspaceId) void loadMembers(workspaceId);
  }, [signedIn, workspaceId, loadMembers]);

  const ownRole = workspaces.find((w) => w.workspace_id === workspaceId)?.role ?? '';
  const canManage = ownRole === 'OWNER' || ownRole === 'ADMIN';
  // The same rule as an API key's cap: nothing above your own role.
  const offer = capsUpTo(ownRole) as WorkspaceRole[];

  async function run(action: () => Promise<MemberInfo[] | void>) {
    if (!workspaceId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      setMembers(result ?? (await listMembers(workspaceId)));
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const address = email.trim();
    if (!address || !workspaceId) return;
    void run(async () => {
      const result = await addMember(workspaceId, address, newRole);
      setEmail('');
      return result;
    });
  }

  if (authStatus === 'unknown') {
    return (
      <main style={page}>
        <h1 style={heading}>Members</h1>
        <LoadingState label="Checking your session…" />
      </main>
    );
  }

  return (
    <main style={page}>
      <Link href="/" style={backLink}>
        ← ModelBox AI
      </Link>
      <h1 style={heading}>Workspace members</h1>
      <p style={lede}>
        Add people who already have an account on this appliance, change their role, or remove them. Accounts
        are created by sign-in (OIDC), SCIM or the appliance owner&apos;s setup, not here.
      </p>

      {!signedIn && (
        <div style={panel}>
          <p style={{ margin: 0, color: color.neutral[600] }}>Sign in to see the members.</p>
          <button type="button" onClick={openModal} style={primaryBtn}>
            Sign in
          </button>
        </div>
      )}

      {signedIn && load.status === 'loading' && <LoadingState label="Loading the members…" />}
      {signedIn && load.status === 'failed' && (
        <ErrorState
          kind={load.kind}
          title="The members could not be loaded"
          onRetry={() => void (workspaceId ? loadMembers(workspaceId) : loadWorkspaces())}
        >
          {load.message}
        </ErrorState>
      )}

      {signedIn && load.status === 'ready' && (
        <>
          {workspaces.length > 1 && (
            <label style={field}>
              <span style={label}>Workspace</span>
              <select value={workspaceId ?? ''} onChange={(e) => setWorkspaceId(e.target.value)} style={input}>
                {workspaces.map((w) => (
                  <option key={w.workspace_id} value={w.workspace_id}>
                    {w.name} ({w.role})
                  </option>
                ))}
              </select>
            </label>
          )}

          {!canManage && <p style={lede}>Only a workspace owner or admin can change its members.</p>}

          <ul style={list} aria-label="Members">
            {members.map((m) => (
              <li key={m.user_id} style={row}>
                <span style={{ flex: 1 }}>{m.email}</span>
                {canManage ? (
                  <select
                    aria-label={`Role of ${m.email}`}
                    value={m.role}
                    disabled={busy}
                    onChange={(e) =>
                      workspaceId &&
                      void run(() => changeMemberRole(workspaceId, m.user_id, e.target.value as WorkspaceRole))
                    }
                    style={input}
                  >
                    {/* The member's current role is always listed, even above your own. */}
                    {ROLE_LADDER.filter((r) => offer.includes(r) || r === m.role).map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span style={meta}>{m.role}</span>
                )}
                {canManage && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => workspaceId && void run(() => removeMember(workspaceId, m.user_id))}
                    style={smallBtn}
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>

          {canManage && (
            <form onSubmit={handleAdd} style={{ ...row, marginTop: space.md }}>
              <input
                aria-label="Email of the user to add"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="someone@example.com"
                style={{ ...input, flex: 1 }}
              />
              <select
                aria-label="Role for the new member"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as WorkspaceRole)}
                style={input}
              >
                {offer.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button type="submit" disabled={busy || !email.trim()} style={primaryBtn}>
                Add member
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

const heading: React.CSSProperties = { fontSize: type.h2.size, fontWeight: type.h2.weight, marginTop: space.sm };

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
