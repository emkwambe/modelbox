'use client';

/**
 * LabModal — the "Spot the Flaw" lab selector for ModelBox Trainer.
 * Lists runnable labs from the content catalog; picking one loads its flawed
 * graph onto the canvas.
 */

import { LABS, type Lab } from '@/content/trainer';

export default function LabModal({
  onClose,
  onSelect,
}: {
  onClose: () => void;
  onSelect: (lab: Lab) => void;
}) {
  return (
    <div style={overlay} onClick={onClose} role="presentation">
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>🧪 Spot the Flaw — Labs</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>
              Load a flawed model, fix the seeded issues, and submit for grading.
            </div>
          </div>
          <button type="button" onClick={onClose} style={closeBtn} aria-label="Close">
            ✕
          </button>
        </div>

        <div style={grid}>
          {LABS.map((lab) => (
            <div key={lab.id} style={card}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <span style={moduleBadge}>Module {lab.module}</span>
                <span style={difficultyBadge}>{lab.difficulty}</span>
              </div>
              <strong style={{ fontSize: 14, marginTop: 6 }}>{lab.title}</strong>
              <p style={{ fontSize: 13, color: '#475569', margin: '4px 0', lineHeight: 1.5 }}>
                {lab.brief}
              </p>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Objectives: clear {lab.expected_flaws.length} flaw
                {lab.expected_flaws.length === 1 ? '' : 's'} —{' '}
                {lab.expected_flaws.map((f) => f.code).join(', ')}
              </div>
              <button
                type="button"
                onClick={() => onSelect(lab)}
                style={{ ...primaryBtn, marginTop: 10 }}
              >
                Start lab →
              </button>
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
  width: 'min(760px, 100%)',
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

const grid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  gap: 12,
  padding: 20,
  overflowY: 'auto',
};

const card: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  border: '1px solid #e2e8f0',
  borderRadius: 10,
  padding: 14,
  background: '#f8fafc',
};

const moduleBadge: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: '#2563eb',
  background: '#eff6ff',
  border: '1px solid #bfdbfe',
  borderRadius: 6,
  padding: '2px 8px',
};

const difficultyBadge: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: '#334155',
  background: '#e2e8f0',
  borderRadius: 6,
  padding: '2px 8px',
  textTransform: 'capitalize',
};

const primaryBtn: React.CSSProperties = {
  padding: '7px 12px',
  borderRadius: 6,
  border: '1px solid #2563eb',
  background: '#2563eb',
  color: '#ffffff',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  alignSelf: 'flex-start',
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: 18,
  color: '#64748b',
  cursor: 'pointer',
  lineHeight: 1,
};
