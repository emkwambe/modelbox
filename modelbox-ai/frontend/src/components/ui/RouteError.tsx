'use client';

/**
 * What a route segment renders when it throws.
 *
 * Before this, the frontend had no error boundary anywhere: a render-time throw
 * unmounted the tree and left a blank page with the failure visible only in the
 * console. Next.js will use an `error.tsx` if one exists and otherwise do
 * exactly that, so the absence was the behaviour.
 *
 * Each segment's `error.tsx` supplies only its own `surface` name. That is the
 * entire reason those files are per-segment rather than one root boundary:
 * without nested layouts the boundaries render in the same place, so the thing
 * they buy is telling the user *which part* failed instead of "something went
 * wrong" over an app that has seven of them.
 */

import { useEffect } from 'react';

import ErrorState from './ErrorState';

export interface RouteErrorProps {
  /** Supplied by Next.js. */
  error: Error & { digest?: string };
  /** Supplied by Next.js: re-renders the segment. */
  reset: () => void;
  /** The failing surface, named the way the user would name it. */
  surface: string;
}

export default function RouteError({ error, reset, surface }: RouteErrorProps) {
  useEffect(() => {
    // A boundary that renders a message and swallows the cause makes the next
    // report unactionable. The console is the only sink an appliance has.
    console.error(`Route error in ${surface}:`, error);
  }, [error, surface]);

  return (
    <ErrorState title={`${surface} could not be displayed`} onRetry={reset}>
      {/*
        The message is shown rather than hidden behind a generic sentence. This
        is a self-hosted tool run by the people who operate the backend it talks
        to — "an unexpected error occurred" costs them the one detail that would
        let them fix it. The digest is included when Next.js supplies one,
        because that is the identifier a server-side log can be searched by.
      */}
      {error.message || 'The page stopped while it was being rendered.'}
      {error.digest ? ` (reference ${error.digest})` : ''}
    </ErrorState>
  );
}
