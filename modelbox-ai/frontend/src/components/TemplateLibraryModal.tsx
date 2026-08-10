'use client';

/**
 * TemplateLibraryModal — the Business Requirements Library.
 *
 * Browse curated starter scenarios and either populate the prompt bar
 * ("Use prompt", Mode A) or hydrate the gold-standard graph onto the canvas
 * ("Load canvas", Mode B).
 */

import { useMemo, useState } from 'react';

import {
  TEMPLATES,
  TEMPLATE_DOMAINS,
  TEMPLATE_PARADIGMS,
  type Template,
} from '@/lib/templates';

interface Props {
  onClose: () => void;
  onUsePrompt: (template: Template) => void;
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
    <div style={overlay} onClick={onClose} role="presentation">
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>
              📚 Business Requirements Library
            </div>
            <div style={{ fontSize: 12, color: '#64748b' }}>
              Start from a gold-standard reference architecture.
            </div>
          </div>
          <button type="button" onClick={onClose} style={closeBtn} aria-label="Close">
            ✕
          </button>
        </div>

        <div style={filters}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search templates…"
            style={{ ...select, flex: 1, minWidth: 160 }}
          />
          <select value={domain} onChange={(e) => setDomain(e.target.value)} style={select}>
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
            style={select}
          >
            <option value="">All paradigms</option>
            {TEMPLATE_PARADIGMS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div style={grid}>
          {filtered.length === 0 && (
            <p style={{ color: '#94a3b8', gridColumn: '1 / -1' }}>
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
              <p style={{ fontSize: 13, color: '#475569', margin: '4px 0' }}>
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
                <button type="button" onClick={() => onUsePrompt(t)} style={ghostBtn}>
                  Use prompt →
                </button>
                <button type="button" onClick={() => onLoadGraph(t)} style={primaryBtn}>
                  Load canvas →
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(15, 23, 42, 0.55)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: 24,
};

const modal: React.CSSProperties = {
  background: '#ffffff',
  borderRadius: 12,
  width: 'min(920px, 100%)',
  maxHeight: '86vh',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
};

const header: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  padding: '16px 20px',
  borderBottom: '1px solid #e2e8f0',
};

const filters: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  padding: '12px 20px',
  borderBottom: '1px solid #e2e8f0',
  flexWrap: 'wrap',
};

const grid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
  padding: 20,
  overflowY: 'auto',
};

const card: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  border: '1px solid #e2e8f0',
  borderRadius: 10,
  padding: 14,
  background: '#f8fafc',
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
  color: '#334155',
  background: '#e2e8f0',
  borderRadius: 6,
  padding: '2px 8px',
};

const detail: React.CSSProperties = {
  marginTop: 6,
  padding: 10,
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: 8,
};

const detailLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: '#64748b',
  marginTop: 6,
};

const detailText: React.CSSProperties = {
  fontSize: 12,
  color: '#475569',
  margin: '2px 0 0',
  lineHeight: 1.5,
};

const select: React.CSSProperties = {
  padding: '6px 10px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  fontSize: 13,
};

const primaryBtn: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: '1px solid #2563eb',
  background: '#2563eb',
  color: '#ffffff',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const ghostBtn: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  background: '#ffffff',
  color: '#334155',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: 18,
  color: '#64748b',
  cursor: 'pointer',
  lineHeight: 1,
};
