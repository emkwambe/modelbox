'use client';

/**
 * A surface that failed.
 *
 * The frontend has no error boundary and no `error.tsx` anywhere, so a
 * render-time throw takes down the whole app and leaves a blank page. This is
 * what the boundaries render instead, and it is also what a panel renders when
 * its own fetch fails.
 *
 * **Three kinds of failure, not one.** `lib/api.ts` clears the session on 401
 * and lets 403 fall through to the generic path, so a user whose workspace does
 * not permit an action is told "something went wrong" — which is both untrue
 * and unactionable, because retrying cannot help. The `kind` prop is that
 * distinction, and it decides both the wording and whether a retry is offered
 * at all: a retry button on a permission failure is a button that is guaranteed
 * to fail.
 */

import type { ReactNode } from 'react';

import Button from './Button';

export type ErrorKind = 'error' | 'denied' | 'missing';

interface ErrorStateProps {
  kind?: ErrorKind;
  /** Overrides the default heading for the kind. */
  title?: string;
  /** What happened, in the user's terms. Never a stack trace. */
  children?: ReactNode;
  /**
   * Offered only when retrying could plausibly work — so it is ignored for
   * `denied`, where the answer will not change on a second attempt.
   */
  onRetry?: () => void;
  retryLabel?: string;
}

const TITLES: Record<ErrorKind, string> = {
  error: 'Something went wrong',
  denied: 'Your workspace does not permit this',
  missing: 'Not found',
};

export default function ErrorState({
  kind = 'error',
  title,
  children,
  onRetry,
  retryLabel = 'Try again',
}: ErrorStateProps) {
  const canRetry = Boolean(onRetry) && kind !== 'denied';

  return (
    <div className="mb-state">
      {/* The role is on the region rather than the heading so the detail is
          announced with it — a heading-only alert reads "Something went wrong"
          and stops before the sentence that says what to do. */}
      <div role="alert" className="mb-state__message">
        <p className="mb-state__title">{title ?? TITLES[kind]}</p>
        {children ? <p className="mb-state__detail">{children}</p> : null}
      </div>

      {canRetry ? (
        <Button variant="primary" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}
