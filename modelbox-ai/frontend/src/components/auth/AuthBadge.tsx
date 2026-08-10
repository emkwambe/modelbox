'use client';

/**
 * AuthBadge — fixed top-right session indicator, workspace switcher, and
 * sign-in trigger.
 */

import { useEffect, useState } from 'react';

import AuthModal from '@/components/auth/AuthModal';
import { listWorkspaces } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';

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
    right: 12,
    zIndex: 1500,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 12,
    fontWeight: 600,
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
              }}
              title={email ?? undefined}
            >
              🔒 {email}
            </span>
            <button type="button" style={btn} onClick={logout}>
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
