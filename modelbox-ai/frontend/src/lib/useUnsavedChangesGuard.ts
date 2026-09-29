'use client';

/**
 * Ask before leaving a canvas with unsaved changes (Sprint 8 Step 3).
 *
 * Two ways out are guarded:
 *
 * - **Closing, reloading or typing another address.** `beforeunload`; the
 *   browser shows its own prompt, and ignores any text supplied.
 * - **Following a link inside the app.** A capturing click listener on the
 *   document runs before `next/link`'s handler; if the user declines, the
 *   click's default is prevented, which `next/link` honours by not navigating.
 *
 * Not guarded: the browser's Back button within the app, which the App Router
 * handles without an event that can be cancelled.
 */

import { useEffect } from 'react';

export const LEAVE_PROMPT = 'You have unsaved changes on this canvas. Leave without saving?';

/** The in-app link a click is following, or null if it leaves nothing. */
function internalLink(event: MouseEvent): HTMLAnchorElement | null {
  if (event.defaultPrevented || event.button !== 0) return null;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return null;
  const anchor = (event.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
  if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return null;
  const url = new URL(anchor.href, window.location.href);
  if (url.origin !== window.location.origin) return null;
  const here = window.location.pathname + window.location.search;
  return url.pathname + url.search === here ? null : anchor;
}

export function useUnsavedChangesGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;

    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Required by some browsers to show the prompt at all.
      event.returnValue = '';
    };
    const onClick = (event: MouseEvent) => {
      if (internalLink(event) && !window.confirm(LEAVE_PROMPT)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };

    window.addEventListener('beforeunload', onBeforeUnload);
    document.addEventListener('click', onClick, true);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      document.removeEventListener('click', onClick, true);
    };
  }, [dirty]);
}
