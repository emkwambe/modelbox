'use client';

/**
 * LabModal — the "Spot the Flaw" lab selector for ModelBox Trainer.
 * Lists runnable labs from the content catalog; picking one loads its flawed
 * graph onto the canvas.
 *
 * The dialog shell is `ui/Modal`, so this file no longer owns the overlay, the
 * focus trap, Escape, the accessible name or the close button — see
 * `ui/Modal.test.tsx` for what that brings with it. What remains here is the
 * lab list, which is the only part that was ever specific to this modal.
 */

import { LABS, type Lab } from '@/content/trainer';
import { Modal, toneColor, toneTint } from '@/components/ui';
import { color } from '@/styles/tokens';

export default function LabModal({
  onClose,
  onSelect,
}: {
  onClose: () => void;
  onSelect: (lab: Lab) => void;
}) {
  return (
    <Modal
      title="🧪 Spot the Flaw — Labs"
      description="Load a flawed model, fix the seeded issues, and submit for grading."
      onClose={onClose}
      width="min(760px, 100%)"
    >
      <div style={grid}>
        {LABS.map((lab) => (
          <div key={lab.id} style={card}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
              <span style={moduleBadge}>Module {lab.module}</span>
              <span style={difficultyBadge}>{lab.difficulty}</span>
            </div>
            <strong style={{ fontSize: 14, marginTop: 6 }}>{lab.title}</strong>
            <p style={{ fontSize: 13, color: color.neutral[600], margin: '4px 0', lineHeight: 1.5 }}>
              {lab.brief}
            </p>
            <div style={{ fontSize: 12, color: color.neutral[500] }}>
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
    </Modal>
  );
}

/*
 * The grid keeps its own padding: `Modal` already pads the body, so the 20px
 * that used to live here is gone and the gap is all that is left.
 */
const grid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  gap: 12,
};

const card: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 10,
  padding: 14,
  background: color.neutral[50],
};

const moduleBadge: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: color.blue,
  background: toneTint('accent', 'light'),
  border: `1px solid ${toneColor('accent', 'light')}`,
  borderRadius: 6,
  padding: '2px 8px',
};

const difficultyBadge: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: color.neutral[700],
  background: color.neutral[200],
  borderRadius: 6,
  padding: '2px 8px',
  textTransform: 'capitalize',
};

const primaryBtn: React.CSSProperties = {
  padding: '7px 12px',
  borderRadius: 6,
  border: `1px solid ${color.blue}`,
  background: color.blue,
  color: color.white,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  alignSelf: 'flex-start',
};
