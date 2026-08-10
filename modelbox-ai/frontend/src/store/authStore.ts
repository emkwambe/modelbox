/**
 * Auth session store — persisted JWT + identity, plus transient modal state.
 *
 * Kept separate from the canvas store: authentication is a cross-cutting
 * concern with its own lifecycle (localStorage persistence, 401 handling).
 */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

interface AuthState {
  token: string | null;
  email: string | null;
  /** Whether the sign-in modal is open (transient, not persisted). */
  modalOpen: boolean;
  setAuth: (token: string, email: string) => void;
  logout: () => void;
  openModal: () => void;
  closeModal: () => void;
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
      modalOpen: false,
      setAuth: (token, email) => set({ token, email, modalOpen: false }),
      logout: () => set({ token: null, email: null }),
      openModal: () => set({ modalOpen: true }),
      closeModal: () => set({ modalOpen: false }),
    }),
    {
      name: 'modelbox-auth',
      storage: safeStorage,
      // Persist only identity — not the transient modal flag.
      partialize: (s) => ({ token: s.token, email: s.email }),
    },
  ),
);
