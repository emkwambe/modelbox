'use client';

/**
 * A surface that is waiting.
 *
 * Deliberately thin: the announcement is `StatusText`'s, already derived from
 * tone and already tested. What this adds is the one thing a bare status line
 * cannot do — occupy the space the content will fill, so a route in flight
 * reads as loading rather than as empty.
 *
 * That distinction is a real defect in this app, not a hypothetical one. The
 * api-keys and connectors pages render their empty state while the first fetch
 * is still open, so a user with keys is told "No API keys yet" and then watches
 * it replaced. An empty list and an unfinished request look identical on screen
 * and mean opposite things.
 */

import StatusText from './StatusText';

interface LoadingStateProps {
  /** What is being waited for. Specific beats "Loading…" — say the noun. */
  label?: string;
}

export default function LoadingState({
  label = 'Loading…',
}: LoadingStateProps) {
  return (
    <div className="mb-state">
      <StatusText>{label}</StatusText>
    </div>
  );
}
