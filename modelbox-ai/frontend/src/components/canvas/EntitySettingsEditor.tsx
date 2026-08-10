'use client';

/**
 * EntitySettingsEditor — entity-level governance/semantics popover.
 *
 * Opens when an entity node is selected (and no column is being edited). Sets
 * the entity's description, grain, asset tier, and freshness SLA. Tier + SLA
 * flow into the OpenDataContract / dbt exports; a Tier-1/2 asset without an SLA
 * is flagged by the MISSING_SLA lint.
 */

import { useCanvasStore } from '@/store/canvasStore';
import type { AssetTier } from '@/types/schema';

const TIERS: { value: AssetTier | ''; label: string }[] = [
  { value: '', label: '— none —' },
  { value: 'TIER_1_CRITICAL', label: 'Tier 1 · Critical' },
  { value: 'TIER_2_IMPORTANT', label: 'Tier 2 · Important' },
  { value: 'TIER_3_STANDARD', label: 'Tier 3 · Standard' },
  { value: 'TIER_4_EXPERIMENTAL', label: 'Tier 4 · Experimental' },
];

export default function EntitySettingsEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const selectedColumn = useCanvasStore((s) => s.selectedColumn);
  const nodes = useCanvasStore((s) => s.nodes);
  const updateEntity = useCanvasStore((s) => s.updateEntity);
  const renameEntity = useCanvasStore((s) => s.renameEntity);
  const selectNode = useCanvasStore((s) => s.selectNode);

  // The column editor takes precedence when a column is selected.
  if (!selectedNodeId || selectedColumn) return null;
  const node = nodes.find((n) => n.id === selectedNodeId);
  if (!node) return null;
  const d = node.data;

  return (
    <div style={card}>
      <div style={header}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>Entity settings</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>
            <code>{d.entity_name}</code> · {d.entity_type}
          </div>
        </div>
        <button
          type="button"
          onClick={() => selectNode(null)}
          style={closeBtn}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <label style={field}>
        <span style={lbl}>Name</span>
        <input
          key={`name-${selectedNodeId}`}
          defaultValue={d.entity_name}
          onBlur={(e) => renameEntity(d.entity_name, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
          }}
          placeholder="e.g. fact_orders"
          style={input}
        />
      </label>

      <label style={field}>
        <span style={lbl}>Description</span>
        <input
          value={d.description ?? ''}
          onChange={(e) => updateEntity(selectedNodeId, { description: e.target.value })}
          placeholder="Business description"
          style={input}
        />
      </label>

      <label style={field}>
        <span style={lbl}>Grain</span>
        <input
          value={d.grain ?? ''}
          onChange={(e) => updateEntity(selectedNodeId, { grain: e.target.value })}
          placeholder="e.g. one row per order line"
          style={input}
        />
      </label>

      <label style={field}>
        <span style={lbl}>Asset tier</span>
        <select
          value={d.tier ?? ''}
          onChange={(e) =>
            updateEntity(selectedNodeId, {
              tier: (e.target.value || null) as AssetTier | null,
            })
          }
          style={input}
        >
          {TIERS.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>

      <label style={field}>
        <span style={lbl}>Freshness SLA</span>
        <input
          value={d.freshness_sla ?? ''}
          onChange={(e) =>
            updateEntity(selectedNodeId, { freshness_sla: e.target.value || null })
          }
          placeholder="e.g. < 1h"
          style={input}
        />
      </label>

      <p style={{ fontSize: 11, color: '#94a3b8', margin: '8px 0 0' }}>
        Save to persist. Tier &amp; SLA flow into ODCS + dbt exports; a Tier 1/2
        asset without an SLA is flagged.
      </p>
    </div>
  );
}

const card: React.CSSProperties = {
  position: 'absolute',
  left: 16,
  bottom: 16,
  width: 288,
  zIndex: 30,
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: 10,
  boxShadow: '0 8px 24px rgba(15,23,42,0.16)',
  padding: 14,
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
};

const header: React.CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 8,
};

const field: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 3,
};

const lbl: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: '#475569',
};

const input: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  fontSize: 13,
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: 15,
  color: '#64748b',
  cursor: 'pointer',
  lineHeight: 1,
};
