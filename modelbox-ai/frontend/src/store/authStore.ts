/**
 * Auth session store — persisted JWT + identity.
 *
 * Kept separate from the canvas store: authentication is a cross-cutting
 * concern with its own lifecycle (localStorage persistence, 401 handling).
 */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

interface AuthState {
  token: string | null;
  email: string | null;
  setAuth: (token: string, email: string) => void;
  logout: () => void;
}

// SSR-safe storage: no-ops on the server where localStorage is undefined.
const safeStorage = createJSONStorage(() =>
  typeof window !== 'undefined'
    ? window.localStorage
    : {
        getItem: () => null,
        setItem: () => undefined,
        removeItem: () => undefined,
      },
);

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      setAuth: (token, email) => set({ token, email }),
      logout: () => set({ token: null, email: null }),
    }),
    { name: 'modelbox-auth', storage: safeStorage },
  ),
);
