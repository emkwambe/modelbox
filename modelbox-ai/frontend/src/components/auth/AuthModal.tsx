'use client';

/**
 * AuthModal — local sign-in / create-account form + one-click Dev Quick Login.
 */

import { useState } from 'react';
import { AxiosError } from 'axios';

import { login, register } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';

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

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: 10,
    marginTop: 6,
    borderRadius: 6,
    border: '1px solid #cbd5e1',
    fontSize: 14,
  };
  const tab = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: '8px 0',
    fontSize: 13,
    fontWeight: 600,
    border: 'none',
    borderBottom: `2px solid ${active ? '#2563eb' : 'transparent'}`,
    color: active ? '#2563eb' : '#64748b',
    background: 'transparent',
    cursor: 'pointer',
  });

  const isRegister = mode === 'register';
  const canSubmit = Boolean(email && password) && !loading;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: '#0f172a99',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 380,
          background: '#ffffff',
          borderRadius: 12,
          padding: 24,
          boxShadow: '0 10px 40px #0000004d',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>ModelBox AI</h2>

        <div style={{ display: 'flex', marginTop: 16, borderBottom: '1px solid #e2e8f0' }}>
          <button
            type="button"
            style={tab(!isRegister)}
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
            onClick={() => {
              setMode('register');
              setError(null);
            }}
          >
            Create account
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (isRegister) void createAccount();
            else void signIn(email, password);
          }}
        >
          {isRegister && (
            <label style={{ display: 'block', marginTop: 16, fontSize: 13 }}>
              Full name (optional)
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Ada Lovelace"
                style={inputStyle}
                autoComplete="name"
              />
            </label>
          )}
          <label style={{ display: 'block', marginTop: 16, fontSize: 13 }}>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              style={inputStyle}
              autoComplete="username"
            />
          </label>
          <label style={{ display: 'block', marginTop: 12, fontSize: 13 }}>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
            />
          </label>

          <button
            type="submit"
            disabled={!canSubmit}
            style={{
              width: '100%',
              marginTop: 18,
              padding: 10,
              borderRadius: 8,
              border: 'none',
              background: !canSubmit ? '#94a3b8' : '#2563eb',
              color: '#fff',
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
              border: '1px dashed #94a3b8',
              background: '#f8fafc',
              color: '#334155',
              fontWeight: 600,
              cursor: loading ? 'default' : 'pointer',
            }}
          >
            ⚡ Dev Quick Login
          </button>
        )}

        {error && (
          <p style={{ color: '#dc2626', marginTop: 12, fontSize: 13 }} role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
