/**
 * Auth session store — persisted JWT + identity + active workspace, plus
 * transient modal state.
 */

import { useEffect, useState } from 'react';
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


/**
 * Whether the session is known yet, and if so what it is.
 *
 * **Three states, not two.** Before the persisted token has been rehydrated
 * from `localStorage`, the app does not know whether anyone is signed in — and
 * treating that as "signed out" or as "signed in" both produce visible defects:
 *
 * - `if (!mounted) return null` renders a **blank page** until hydration
 *   finishes. Nothing is drawn at all, so a slow load looks like a broken app
 *   rather than a loading one.
 * - `if (mounted && !token)` skips the signed-out branch while `mounted` is
 *   false, so an unauthenticated visitor is briefly shown the **signed-in UI**.
 *   That is the worse of the two: it flashes content that the next frame takes
 *   away.
 *
 * Both came from using a component's own `mounted` flag as a proxy for "the
 * token is known". They correlate by accident of ordering; they are not the
 * same question. `persist.hasHydrated()` answers the actual one.
 *
 * `unknown` is a real state with a real rendering — a loading surface — rather
 * than an absence to be collapsed into one of the other two.
 */
export type AuthStatus = 'unknown' | 'signed-out' | 'signed-in';

export function useAuthStatus(): AuthStatus {
  const token = useAuthStore((s) => s.token);
  // Initialised from the store rather than `false`, so a component mounting
  // after hydration has already finished never reports `unknown` and never
  // flashes a loading state it does not need.
  const [hydrated, setHydrated] = useState(() =>
    useAuthStore.persist.hasHydrated(),
  );

  useEffect(() => {
    // Both halves are required. `onFinishHydration` misses the case where
    // hydration completed between render and effect; the direct check misses
    // the case where it has not started. Either alone leaves a state stuck.
    const unsubscribe = useAuthStore.persist.onFinishHydration(() =>
      setHydrated(true),
    );
    if (useAuthStore.persist.hasHydrated()) setHydrated(true);
    return unsubscribe;
  }, []);

  if (!hydrated) return 'unknown';
  return token ? 'signed-in' : 'signed-out';
}
