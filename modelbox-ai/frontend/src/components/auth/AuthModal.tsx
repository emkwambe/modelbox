'use client';

/**
 * AuthModal — local sign-in form + one-click Dev Quick Login.
 */

import { useState } from 'react';

import { login } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';

const DEV_EMAIL = 'dev@modelbox.ai';
const DEV_PASSWORD = 'password123';

export default function AuthModal({ onClose }: { onClose: () => void }) {
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
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

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: 10,
    marginTop: 6,
    borderRadius: 6,
    border: '1px solid #cbd5e1',
    fontSize: 14,
  };

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
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
          Sign in to ModelBox AI
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void signIn(email, password);
          }}
        >
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
              autoComplete="current-password"
            />
          </label>

          <button
            type="submit"
            disabled={loading || !email || !password}
            style={{
              width: '100%',
              marginTop: 18,
              padding: 10,
              borderRadius: 8,
              border: 'none',
              background: loading ? '#94a3b8' : '#2563eb',
              color: '#fff',
              fontWeight: 600,
              cursor: loading ? 'default' : 'pointer',
            }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

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

        {error && (
          <p style={{ color: '#dc2626', marginTop: 12, fontSize: 13 }} role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
