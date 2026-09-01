'use client';

/**
 * AuthModal — local sign-in / create-account form + one-click Dev Quick Login.
 *
 * The dialog shell is `ui/Modal` and the three inputs are `ui/Field`. This was
 * the worst of the three modals to meet with a keyboard: it had **no close
 * button at all**, so a user who opened it and did not want to sign in had no
 * way out — no Escape, no ✕, and Tab walked out of the form into the page
 * behind the overlay rather than back to the top of it.
 */

import { useState } from 'react';
import { AxiosError } from 'axios';

import { Field, Input, Modal, StatusText } from '@/components/ui';
import { login, register } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { color, semantic } from '@/styles/tokens';

const DEV_EMAIL = 'dev@modelbox.ai';
const DEV_PASSWORD = 'password123';

type Mode = 'signin' | 'register';

export default function AuthModal({ onClose }: { onClose: () => void }) {
  const setAuth = useAuthStore((s) => s.setAuth);
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn(useEmail: string, usePassword: string) {
    setLoading(true);
    setError(null);
    try {
      const token = await login(useEmail, usePassword);
      setAuth(token, useEmail);
      onClose();
    } catch {
      setError('Sign-in failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  }

  async function createAccount() {
    setLoading(true);
    setError(null);
    try {
      const token = await register(email, password, fullName || undefined);
      setAuth(token, email);
      onClose();
    } catch (err) {
      const status =
        err instanceof AxiosError ? err.response?.status : undefined;
      setError(
        status === 409
          ? 'That email is already registered. Try signing in.'
          : 'Registration failed. Check your details and try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  const tab = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: '8px 0',
    fontSize: 13,
    fontWeight: 600,
    border: 'none',
    borderBottom: `2px solid ${active ? color.blue : 'transparent'}`,
    color: active ? color.blue : color.neutral[500],
    background: 'transparent',
    cursor: 'pointer',
  });

  const isRegister = mode === 'register';
  const canSubmit = Boolean(email && password) && !loading;

  return (
    <Modal title="ModelBox AI" onClose={onClose} width="380px">
      <div style={{ display: 'flex', borderBottom: `1px solid ${color.neutral[200]}` }}>
        <button
          type="button"
          style={tab(!isRegister)}
          aria-pressed={!isRegister}
          onClick={() => {
            setMode('signin');
            setError(null);
          }}
        >
          Sign in
        </button>
        <button
          type="button"
          style={tab(isRegister)}
          aria-pressed={isRegister}
          onClick={() => {
            setMode('register');
            setError(null);
          }}
        >
          Create account
        </button>
      </div>

      <form
        style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}
        onSubmit={(e) => {
          e.preventDefault();
          if (isRegister) void createAccount();
          else void signIn(email, password);
        }}
      >
        {isRegister && (
          <Field label="Full name (optional)">
            <Input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ada Lovelace"
              autoComplete="name"
            />
          </Field>
        )}
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="username"
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isRegister ? 'new-password' : 'current-password'}
          />
        </Field>

        <button
          type="submit"
          disabled={!canSubmit}
          style={{
            width: '100%',
            marginTop: 6,
            padding: 10,
            borderRadius: 8,
            border: 'none',
            background: !canSubmit ? color.neutral[400] : color.blue,
            color: color.white,
            fontWeight: 600,
            cursor: !canSubmit ? 'default' : 'pointer',
          }}
        >
          {loading
            ? isRegister
              ? 'Creating account…'
              : 'Signing in…'
            : isRegister
              ? 'Create account'
              : 'Sign in'}
        </button>
      </form>

      {!isRegister && (
        <button
          type="button"
          onClick={() => void signIn(DEV_EMAIL, DEV_PASSWORD)}
          disabled={loading}
          style={{
            width: '100%',
            marginTop: 10,
            padding: 10,
            borderRadius: 8,
            border: `1px dashed ${color.neutral[400]}`,
            background: color.neutral[50],
            color: color.neutral[700],
            fontWeight: 600,
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          ⚡ Dev Quick Login
        </button>
      )}

      {error && (
        <div style={{ marginTop: 12 }}>
          {/*
           * `StatusText` derives `role="alert"` and `aria-live="assertive"`
           * from the tone, and takes its colour from `semantic.breaking` for a
           * light ground rather than the `#dc2626` that was written here — one
           * of the 22 sites where the app used Tailwind's red instead of the
           * brand's.
           */}
          <StatusText tone="breaking">{error}</StatusText>
        </div>
      )}
    </Modal>
  );
}
