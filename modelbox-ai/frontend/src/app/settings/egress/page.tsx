'use client';

/**
 * Egress ledger — what left the network, when, and on whose behalf (D4).
 *
 * The criterion is that an operator can answer that question without
 * engineering help. Until this page the answer was a SQL query, which is
 * engineering help by definition.
 *
 * Two things this page will not do. It does not show prompt text — the ledger
 * stores a digest and a length, never the content, and a governance view is
 * the wrong place to widen that. And it does not quietly drop what workspace
 * scoping cannot return: rows written with no workspace belong to nobody, and
 * the banner says how many there are, because "this is what left" and "this is
 * what left that we can place" are different answers and only one of them is
 * true.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

import { Banner, StatusText } from '@/components/ui';
import { listEgressEvents } from '@/lib/api';
import { useAuthStatus, useAuthStore } from '@/store/authStore';
import { color, semantic } from '@/styles/tokens';
import type { EgressEvent, EgressLedgerPage } from '@/types/schema';

const CLASS_COLORS: Record<string, string> = {
  // Residency reads as a status, so it takes the semantic roles rather than a
  // palette of its own: local is the contained case, the two regional pins are
  // the "not deployment-verified" case, and unrestricted `cloud` is the one an
  // operator is meant to notice.
  local: semantic.validated.onLight,
  cloud_eu: semantic.preview.onLight,
  cloud_apac: semantic.preview.onLight,
  cloud: semantic.breaking.onLight,
};

const EVENT_COLORS: Record<string, string> = {
  ATTEMPT: color.neutral[600],
  SUCCESS: semantic.validated.onLight,
  FAILURE: semantic.breaking.onLight,
};

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span
      style={{
        color,
        border: `1px solid ${color}`,
        borderRadius: 3,
        padding: '1px 6px',
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
      }}
    >
      {text}
    </span>
  );
}

export default function EgressLedgerPageView() {
  const token = useAuthStore((s) => s.token);
  const openModal = useAuthStore((s) => s.openModal);
  const [page, setPage] = useState<EgressLedgerPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [eventFilter, setEventFilter] = useState('');
  const authStatus = useAuthStatus();


  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      setPage(await listEgressEvents(eventFilter ? { event: eventFilter } : {}));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the ledger.');
    } finally {
      setLoading(false);
    }
  }, [token, eventFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  // `unknown` renders the signed-out frame rather than the ledger. Gating on
  // `mounted && !token` meant that while `mounted` was false this branch was
  // skipped and the **ledger itself** rendered to a visitor who was not signed
  // in — a flash of authenticated UI, which is worse than a blank page because
  // it shows something rather than nothing.
  if (authStatus !== 'signed-in') {
    return (
      <main style={{ maxWidth: 760, margin: '64px auto', padding: '0 24px' }}>
        <h1 style={{ fontSize: 26, fontWeight: 800 }}>Egress ledger</h1>
        <p style={{ color: color.neutral[600] }}>
          Sign in to see what this appliance has sent to a model provider.
        </p>
        <button
          type="button"
          onClick={openModal}
          style={{
            padding: '8px 16px',
            borderRadius: 6,
            border: `1px solid ${color.blue}`,
            background: color.blue,
            color: color.white,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Sign in
        </button>
      </main>
    );
  }

  const events: EgressEvent[] = page?.events ?? [];

  return (
    <main style={{ maxWidth: 1200, margin: '40px auto 80px', padding: '0 24px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>Egress ledger</h1>
        <Link href="/" style={{ fontSize: 13, color: color.blue }}>
          ← Studio
        </Link>
      </div>
      <p style={{ color: color.neutral[600], maxWidth: '68ch', marginTop: 8 }}>
        Every request this appliance made to a model provider, recorded before it
        was sent. Prompt text is never stored — only its SHA-256 and length.
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '20px 0 12px' }}>
        <label htmlFor="event" style={{ fontSize: 13, color: color.neutral[600] }}>
          Show
        </label>
        <select
          id="event"
          value={eventFilter}
          onChange={(e) => setEventFilter(e.target.value)}
          style={{
            padding: '5px 10px',
            borderRadius: 6,
            border: `1px solid ${color.neutral[300]}`,
            fontSize: 13,
          }}
        >
          <option value="">All events</option>
          <option value="ATTEMPT">Attempts</option>
          <option value="SUCCESS">Successes</option>
          <option value="FAILURE">Failures</option>
        </select>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          style={{
            padding: '5px 12px',
            borderRadius: 6,
            border: `1px solid ${color.neutral[300]}`,
            background: color.white,
            fontSize: 13,
            fontWeight: 600,
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
        {page && (
          <span style={{ fontSize: 13, color: color.neutral[500] }}>
            {page.total} event{page.total === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {page && page.unattributed > 0 && (
        <div style={{ maxWidth: '78ch' }}>
          {/*
            Was a hand-rolled amber box: `#fffbeb` ground, `#fde68a` border,
            `#92400e` text — three values from Tailwind's amber ramp, none of
            them in this product's, and the foreground never measured against
            the ground it sat on. `Banner` derives both from the `preview` role
            at an alpha `Badge.test.tsx` holds to the contrast floor, so the
            pair cannot drift apart.
          */}
          <Banner tone="preview">
            <strong>{page.unattributed}</strong> further event
            {page.unattributed === 1 ? '' : 's'} left this appliance without a
            workspace recorded, so{' '}
            {page.unattributed === 1 ? 'it is' : 'they are'} not shown above.
            This list is what left that can be attributed, not everything that
            left.
          </Banner>
        </div>
      )}

      {/*
        `#dc2626` is Tailwind's red-600 — one of the two literals
        `status-colour.test.tsx` bans by name, and the most-repeated colour in
        the frontend at 22 occurrences.

        It is worth being exact about *why* it goes, because the obvious reason
        is not the true one: measured, it is **4.62:1** on this page's
        `neutral-50` ground and so it clears the 4.5:1 body floor. It is not a
        legibility defect. It goes because it is not this product's red —
        `breaking.onLight` is, at 6.01:1 — and because `StatusText` carries the
        assertive announcement with the tone, rather than leaving `role="alert"`
        to a call site that has to remember it.
      */}
      {error && <StatusText tone="breaking">{error}</StatusText>}

      {!loading && !error && events.length === 0 && (
        <p style={{ color: color.neutral[500], fontSize: 14 }}>
          Nothing has been sent to a provider from your workspaces yet.
        </p>
      )}

      {events.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: color.neutral[500] }}>
                {['When', 'Event', 'Task', 'Provider', 'Egress', 'Tokens', 'Prompt', 'Detail'].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        padding: '6px 10px 6px 0',
                        borderBottom: `1px solid ${color.neutral[300]}`,
                        fontSize: 11,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.egress_id}>
                  <td style={cell} title={e.occurred_at}>
                    {new Date(e.occurred_at).toLocaleString()}
                  </td>
                  <td style={cell}>
                    <Pill text={e.event} color={EVENT_COLORS[e.event] ?? color.neutral[600]} />
                  </td>
                  <td style={cell}>{e.task}</td>
                  <td style={cell}>{e.provider}</td>
                  <td style={cell}>
                    <Pill
                      text={e.egress_class}
                      color={CLASS_COLORS[e.egress_class] ?? color.neutral[600]}
                    />
                  </td>
                  <td style={{ ...cell, fontVariantNumeric: 'tabular-nums' }}>
                    {e.prompt_tokens ?? e.completion_tokens
                      ? `${e.prompt_tokens ?? 0} / ${e.completion_tokens ?? 0}`
                      : '—'}
                  </td>
                  <td
                    style={{ ...cell, fontFamily: 'ui-monospace, monospace' }}
                    title={`${e.prompt_sha256} (${e.prompt_chars} chars)`}
                  >
                    {e.prompt_sha256.slice(0, 10)}…
                  </td>
                  <td style={{ ...cell, color: e.error ? semantic.breaking.onLight : color.neutral[500] }}>
                    {e.error ?? (e.model_id ? `model ${e.model_id.slice(0, 8)}` : '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

const cell: React.CSSProperties = {
  padding: '6px 10px 6px 0',
  borderBottom: `1px solid ${color.neutral[200]}`,
  verticalAlign: 'top',
  whiteSpace: 'nowrap',
};
