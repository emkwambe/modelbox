'use client';

/**
 * In-app documentation viewer (/docs).
 *
 * Renders the versioned Markdown guides (served from /content) with tab
 * navigation (User Guide / API Reference), a searchable section table of
 * contents, and copy buttons on code blocks.
 */

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { AUTH_BADGE_RESERVE } from '@/components/auth/AuthBadge';
import { ErrorState, LoadingState } from '@/components/ui';
import { errMessage } from '@/lib/errors';
import { color } from '@/styles/tokens';

type Tab = 'guide' | 'api';

const DOCS: Record<Tab, { label: string; src: string }> = {
  guide: { label: 'User Guide', src: '/content/USER_GUIDE.md' },
  api: { label: 'API Reference', src: '/content/API_REFERENCE.md' },
};

function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/`/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

/** Flatten React children to their plain text (for slugs + copy). */
function nodeText(node: ReactNode): string {
  if (node == null || node === false) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join('');
  if (typeof node === 'object' && 'props' in node) {
    return nodeText((node as { props: { children?: ReactNode } }).props.children);
  }
  return '';
}

function CopyPre({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = nodeText(children);
  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard?.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        style={{
          position: 'absolute',
          top: 8,
          right: 8,
          padding: '2px 8px',
          borderRadius: 4,
          border: `1px solid ${color.neutral[700]}`,
          background: color.neutral[800],
          color: color.neutral[200],
          fontSize: 11,
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
      <pre>{children}</pre>
    </div>
  );
}

/**
 * A document is loading, loaded, or failed — three states, not the two the
 * emptiness of a string can express.
 *
 * The previous code inferred "still loading" from `text[tab] === ''`, which is
 * also what a failed fetch leaves behind. With `catch {}` above it, a backend
 * that never serves `/content/USER_GUIDE.md` showed "Loading documentation…"
 * for as long as the page stayed open.
 */
type DocState =
  | { status: 'loading' }
  | { status: 'ready'; body: string }
  | { status: 'failed'; message: string };

const LOADING: Record<Tab, DocState> = {
  guide: { status: 'loading' },
  api: { status: 'loading' },
};

export default function DocsPage() {
  const [tab, setTab] = useState<Tab>('guide');
  const [docs, setDocs] = useState<Record<Tab, DocState>>(LOADING);
  const [query, setQuery] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setDocs(LOADING);

    (Object.keys(DOCS) as Tab[]).forEach(async (key) => {
      const update = (state: DocState) => {
        if (!cancelled) setDocs((prev) => ({ ...prev, [key]: state }));
      };

      try {
        const res = await fetch(DOCS[key].src);
        // `fetch` rejects only on a transport failure, so without this a 404
        // resolves happily and its HTML body is handed to the Markdown
        // renderer — the error page is displayed *as documentation*.
        if (!res.ok) {
          update({
            status: 'failed',
            message: `${DOCS[key].src} returned ${res.status}.`,
          });
          return;
        }
        update({ status: 'ready', body: await res.text() });
      } catch (e) {
        update({
          status: 'failed',
          message: errMessage(e, 'The documentation could not be fetched.'),
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const doc = docs[tab];
  // Only a loaded document has headings. A failed one contributing to the
  // table of contents would put links in the sidebar that scroll to nothing.
  const current = doc.status === 'ready' ? doc.body : '';

  const headings = useMemo(
    () =>
      current
        .split('\n')
        .filter((line) => /^##\s|^###\s/.test(line))
        .map((line) => {
          const level = line.startsWith('### ') ? 3 : 2;
          const title = line.replace(/^#+\s/, '').replace(/`/g, '');
          return { level, title, id: slug(title) };
        }),
    [current],
  );

  const filtered = headings.filter((h) =>
    h.title.toLowerCase().includes(query.trim().toLowerCase()),
  );

  const components = {
    h2: ({ children }: { children?: ReactNode }) => (
      <h2 id={slug(nodeText(children))}>{children}</h2>
    ),
    h3: ({ children }: { children?: ReactNode }) => (
      <h3 id={slug(nodeText(children))}>{children}</h3>
    ),
    pre: CopyPre,
  };

  return (
    <main style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px 64px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
          // Reserve space on the right for the fixed AuthBadge overlay. The
          // badge declares how much it needs; do not restate the number here.
          paddingRight: AUTH_BADGE_RESERVE,
        }}
      >
        <Link
          href="/"
          style={{ color: color.blue, fontWeight: 600, textDecoration: 'none' }}
        >
          ← ModelBox AI
        </Link>
        <div style={{ display: 'flex', gap: 8 }}>
          {(Object.keys(DOCS) as Tab[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              style={{
                padding: '6px 14px',
                borderRadius: 8,
                border: `1px solid ${color.neutral[300]}`,
                background: tab === key ? color.blue : color.white,
                color: tab === key ? color.white : color.neutral[700],
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {DOCS[key].label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 32, marginTop: 24, alignItems: 'flex-start' }}>
        {/* Table of contents */}
        <aside
          style={{
            width: 240,
            flexShrink: 0,
            position: 'sticky',
            top: 24,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search sections…"
            style={{
              padding: '6px 10px',
              borderRadius: 6,
              border: `1px solid ${color.neutral[300]}`,
              fontSize: 13,
            }}
          />
          <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {filtered.map((h) => (
              <a
                key={h.id}
                href={`#${h.id}`}
                style={{
                  fontSize: 13,
                  color: color.neutral[600],
                  textDecoration: 'none',
                  paddingLeft: h.level === 3 ? 12 : 0,
                  paddingBlock: 2,
                }}
              >
                {h.title}
              </a>
            ))}
          </nav>
        </aside>

        {/* Rendered document */}
        <article className="markdown-body" style={{ flex: 1, minWidth: 0 }}>
          {doc.status === 'ready' ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
              {doc.body}
            </ReactMarkdown>
          ) : doc.status === 'failed' ? (
            <ErrorState
              title={`${DOCS[tab].label} could not be loaded`}
              onRetry={() => setAttempt((n) => n + 1)}
            >
              {doc.message}
            </ErrorState>
          ) : (
            <LoadingState label="Loading documentation…" />
          )}
        </article>
      </div>
    </main>
  );
}
