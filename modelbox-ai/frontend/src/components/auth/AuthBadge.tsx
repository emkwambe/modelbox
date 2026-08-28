'use client';

/**
 * AuthBadge — fixed top-right session indicator, workspace switcher, and
 * sign-in trigger.
 */

import { useEffect, useState } from 'react';

import AuthModal from '@/components/auth/AuthModal';
import { listWorkspaces } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';

/**
 * Hard bound on the badge's rendered width.
 *
 * The badge is a fixed overlay, so a page underneath it cannot discover how
 * wide it is — it can only keep space clear and trust the badge to stay
 * inside. The bound is what makes that trust sound: workspace name and email
 * both truncate rather than pushing the badge wider.
 */
/*
 * Sized to what the badge actually holds rather than to a round number: the
 * workspace select (capped at 200), the email pill, the Logout button, and two
 * 8px gaps. At the previous 320 the email truncated to five characters, which
 * is a bound the design does not survive.
 */
export const AUTH_BADGE_WIDTH = 400;

/** Right offset of the fixed badge. */
const AUTH_BADGE_RIGHT = 12;

/**
 * Horizontal space a page must keep clear for the badge — its width, its
 * offset from the edge, and a gutter so content does not touch it.
 *
 * Import this rather than restating the number: a page that hard-codes its own
 * reservation is a second source of truth, and it silently stopped agreeing
 * when the email pill grew (the canvas toolbar's "Export artifacts" ended up
 * underneath the workspace switcher, unclickable).
 */
export const AUTH_BADGE_RESERVE = AUTH_BADGE_WIDTH + AUTH_BADGE_RIGHT + 12;

export default function AuthBadge() {
  const token = useAuthStore((s) => s.token);
  const email = useAuthStore((s) => s.email);
  const logout = useAuthStore((s) => s.logout);
  const modalOpen = useAuthStore((s) => s.modalOpen);
  const openModal = useAuthStore((s) => s.openModal);
  const closeModal = useAuthStore((s) => s.closeModal);
  const workspaces = useAuthStore((s) => s.workspaces);
  const activeWorkspaceId = useAuthStore((s) => s.activeWorkspaceId);
  const setWorkspaces = useAuthStore((s) => s.setWorkspaces);
  const setActiveWorkspace = useAuthStore((s) => s.setActiveWorkspace);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  // Load the caller's workspaces whenever authenticated.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listWorkspaces()
      .then((list) => {
        if (cancelled) return;
        setWorkspaces(list);
        const current = useAuthStore.getState().activeWorkspaceId;
        const stillValid = list.some((w) => w.workspace_id === current);
        if (!stillValid && list.length > 0) {
          setActiveWorkspace(list[0]!.workspace_id);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [token, setWorkspaces, setActiveWorkspace]);

  if (!mounted) return null;

  const pill: React.CSSProperties = {
    position: 'fixed',
    top: 10,
    right: AUTH_BADGE_RIGHT,
    zIndex: 1500,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 8,
    fontSize: 12,
    fontWeight: 600,
    // Stay inside what pages reserve. Without the bound the badge is sized by
    // its content — a long workspace name or email pushes it left over
    // whatever sits in the page header.
    maxWidth: AUTH_BADGE_WIDTH,
    minWidth: 0,
  };
  const btn: React.CSSProperties = {
    padding: '4px 10px',
    borderRadius: 14,
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    cursor: 'pointer',
  };

  const activeRole = workspaces.find(
    (w) => w.workspace_id === activeWorkspaceId,
  )?.role;

  return (
    <>
      <div style={pill}>
        {token ? (
          <>
            {workspaces.length > 0 && (
              <select
                value={activeWorkspaceId ?? ''}
                onChange={(e) => setActiveWorkspace(e.target.value)}
                title={activeRole ? `Role: ${activeRole}` : undefined}
                style={{
                  ...btn,
                  maxWidth: 200,
                  minWidth: 0,
                  flexShrink: 1,
                  fontWeight: 600,
                }}
              >
                {workspaces.map((w) => (
                  <option key={w.workspace_id} value={w.workspace_id}>
                    {w.name} · {w.role}
                  </option>
                ))}
              </select>
            )}
            <span
              style={{
                background: '#ecfdf5',
                color: '#047857',
                border: '1px solid #6ee7b7',
                borderRadius: 14,
                padding: '4px 10px',
                // Truncate rather than widen the badge; the full address stays
                // available in the tooltip.
                minWidth: 0,
                flexShrink: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={email ?? undefined}
            >
              🔒 {email}
            </span>
            <button
              type="button"
              style={{ ...btn, flexShrink: 0 }}
              onClick={logout}
            >
              Logout
            </button>
          </>
        ) : (
          <button
            type="button"
            style={{
              ...btn,
              borderColor: '#2563eb',
              color: '#fff',
              background: '#2563eb',
            }}
            onClick={openModal}
          >
            Sign in
          </button>
        )}
      </div>
      {modalOpen && <AuthModal onClose={closeModal} />}
    </>
  );
}
