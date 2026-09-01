'use client';

/**
 * TemplateLibraryModal — the Business Requirements Library.
 *
 * Browse curated starter scenarios and either populate the prompt bar
 * ("Use prompt", Mode A) or hydrate the gold-standard graph onto the canvas
 * ("Load canvas", Mode B).
 *
 * The dialog shell is `ui/Modal`. The search and facet row goes in its
 * `toolbar` slot rather than in the body, which is what keeps it fixed while
 * the results scroll — folding it into the children would have looked correct
 * and scrolled the filters away, so `Modal.test.tsx` asserts the two are
 * siblings rather than nested.
 */

import { useMemo, useState } from 'react';

import { Modal } from '@/components/ui';
import { color } from '@/styles/tokens';
import {
  TEMPLATES,
  TEMPLATE_DOMAINS,
  TEMPLATE_PARADIGMS,
  type Template,
} from '@/lib/templates';

interface Props {
  onClose: () => void;
  /** Mode A — populate a prompt bar. Omit where there is none (e.g. Trainer). */
  onUsePrompt?: (template: Template) => void;
  onLoadGraph: (template: Template) => void;
}

export default function TemplateLibraryModal({
  onClose,
  onUsePrompt,
  onLoadGraph,
}: Props) {
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('');
  const [paradigm, setParadigm] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return TEMPLATES.filter((t) => {
      if (domain && t.domain !== domain) return false;
      if (paradigm && t.paradigm !== paradigm) return false;
      if (!q) return true;
      return (
        t.title.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.highlights.some((h) => h.toLowerCase().includes(q))
      );
    });
  }, [query, domain, paradigm]);

  return (
    <Modal
      title="📚 Business Requirements Library"
      description="Start from a gold-standard reference architecture."
      onClose={onClose}
      width="min(920px, 100%)"
      toolbar={
        <>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search templates…"
            aria-label="Search templates"
            style={{ ...select, flex: 1, minWidth: 160 }}
          />
          <select
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            aria-label="Filter by domain"
            style={select}
          >
            <option value="">All domains</option>
            {TEMPLATE_DOMAINS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <select
            value={paradigm}
            onChange={(e) => setParadigm(e.target.value)}
            aria-label="Filter by paradigm"
            style={select}
          >
            <option value="">All paradigms</option>
            {TEMPLATE_PARADIGMS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </>
      }
    >
      <div style={grid}>
        {filtered.length === 0 && (
          <p style={{ color: color.neutral[500], gridColumn: '1 / -1' }}>
            No templates match your filters.
          </p>
        )}
        {filtered.map((t) => (
          <div key={t.id} style={card}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 20 }}>{t.emoji}</span>
              <strong style={{ fontSize: 14 }}>{t.title}</strong>
            </div>
            <span style={paradigmBadge}>{t.paradigm}</span>
            <p style={{ fontSize: 13, color: color.neutral[600], margin: '4px 0' }}>
              {t.description}
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {t.highlights.map((h) => (
                <span key={h} style={chip}>
                  {h}
                </span>
              ))}
            </div>

            {expanded === t.id && (
              <div style={detail}>
                <div style={detailLabel}>Prompt</div>
                <p style={detailText}>{t.rawPrompt}</p>
                <div style={detailLabel}>Why it&apos;s modeled this way</div>
                <p style={detailText}>{t.rationale}</p>
              </div>
            )}

            <div style={{ display: 'flex', gap: 6, marginTop: 'auto', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => setExpanded(expanded === t.id ? null : t.id)}
                style={ghostBtn}
              >
                {expanded === t.id ? 'Hide' : 'Preview'}
              </button>
              {onUsePrompt && (
                <button type="button" onClick={() => onUsePrompt(t)} style={ghostBtn}>
                  Use prompt →
                </button>
              )}
              <button type="button" onClick={() => onLoadGraph(t)} style={primaryBtn}>
                Load canvas →
              </button>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}

/*
 * The overlay, the dialog box, the header and the filter strip used to be four
 * more constants here. They are `.mb-modal*` now, so the scrim, the elevation
 * and the two 1px rules are stated once for all three dialogs rather than
 * three times with three sets of near-miss values.
 */
const grid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
};

const card: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 10,
  padding: 14,
  background: color.neutral[50],
};

const paradigmBadge: React.CSSProperties = {
  alignSelf: 'flex-start',
  fontSize: 11,
  fontWeight: 700,
  color: '#7c3aed',
  background: '#f5f3ff',
  border: '1px solid #ddd6fe',
  borderRadius: 6,
  padding: '2px 8px',
};

const chip: React.CSSProperties = {
  fontSize: 11,
  color: color.neutral[700],
  background: color.neutral[200],
  borderRadius: 6,
  padding: '2px 8px',
};

const detail: React.CSSProperties = {
  marginTop: 6,
  padding: 10,
  background: color.white,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 8,
};

const detailLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: color.neutral[500],
  marginTop: 6,
};

const detailText: React.CSSProperties = {
  fontSize: 12,
  color: color.neutral[600],
  margin: '2px 0 0',
  lineHeight: 1.5,
};

const select: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: 6,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: 13,
};

const primaryBtn: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: `1px solid ${color.blue}`,
  background: color.blue,
  color: color.white,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const ghostBtn: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: `1px solid ${color.neutral[300]}`,
  background: color.white,
  color: color.neutral[700],
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};
