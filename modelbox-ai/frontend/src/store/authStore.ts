/**
 * Auth session store — persisted JWT + identity + active workspace, plus
 * transient modal state.
 */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { WorkspaceInfo } from '@/types/schema';

interface AuthState {
  token: string | null;
  email: string | null;
  /** Whether the sign-in modal is open (transient, not persisted). */
  modalOpen: boolean;
  workspaces: WorkspaceInfo[];
  activeWorkspaceId: string | null;
  setAuth: (token: string, email: string) => void;
  logout: () => void;
  openModal: () => void;
  closeModal: () => void;
  setWorkspaces: (workspaces: WorkspaceInfo[]) => void;
  setActiveWorkspace: (workspaceId: string | null) => void;
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
      workspaces: [],
      activeWorkspaceId: null,
      setAuth: (token, email) => set({ token, email, modalOpen: false }),
      logout: () =>
        set({
          token: null,
          email: null,
          workspaces: [],
          activeWorkspaceId: null,
        }),
      openModal: () => set({ modalOpen: true }),
      closeModal: () => set({ modalOpen: false }),
      setWorkspaces: (workspaces) => set({ workspaces }),
      setActiveWorkspace: (workspaceId) =>
        set({ activeWorkspaceId: workspaceId }),
    }),
    {
      name: 'modelbox-auth',
      storage: safeStorage,
      // Persist identity + active workspace, not transient/derived state.
      partialize: (s) => ({
        token: s.token,
        email: s.email,
        activeWorkspaceId: s.activeWorkspaceId,
      }),
    },
  ),
);
