'use client';

/**
 * The last boundary. This one catches a throw in the root layout itself, which
 * every `error.tsx` below it is powerless against — if the layout is the thing
 * that failed, there is no layout left to render an error inside.
 *
 * Which is why it renders its own `<html>` and `<body>`: Next.js replaces the
 * whole document with this component, so the tags the root layout would
 * normally supply have to come from here.
 *
 * And why the styling is inline rather than `.mb-state`. `ui.css` is imported
 * by the root layout; a failure in that layout is exactly the case where the
 * stylesheet may not have loaded. A boundary that depends on the thing that
 * broke is not a boundary. This is the one file in the frontend where an
 * unreachable token is the right call, and it is deliberately the only one.
 */

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Root layout error:', error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          padding: 24,
          textAlign: 'center',
          fontFamily: 'system-ui, sans-serif',
          background: '#f8fafc',
          color: '#0f172a',
        }}
      >
        <div role="alert">
          <p style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
            ModelBox AI could not start
          </p>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#475569' }}>
            {error.message || 'The application failed while loading.'}
            {error.digest ? ` (reference ${error.digest})` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={reset}
          style={{
            padding: '8px 14px',
            borderRadius: 6,
            border: '1px solid #2563eb',
            background: '#2563eb',
            color: '#ffffff',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
