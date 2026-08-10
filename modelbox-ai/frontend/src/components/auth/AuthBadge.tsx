'use client';

/**
 * AuthBadge — fixed top-right session indicator + sign-in trigger.
 */

import { useEffect, useState } from 'react';

import AuthModal from '@/components/auth/AuthModal';
import { useAuthStore } from '@/store/authStore';

export default function AuthBadge() {
  const token = useAuthStore((s) => s.token);
  const email = useAuthStore((s) => s.email);
  const logout = useAuthStore((s) => s.logout);
  const modalOpen = useAuthStore((s) => s.modalOpen);
  const openModal = useAuthStore((s) => s.openModal);
  const closeModal = useAuthStore((s) => s.closeModal);
  const [mounted, setMounted] = useState(false);

  // Avoid SSR/CSR hydration mismatch: render only after the client mounts
  // (persisted auth state is not known during server render).
  useEffect(() => setMounted(true), []);
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

  return (
    <>
      <div style={pill}>
        {token ? (
          <>
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
