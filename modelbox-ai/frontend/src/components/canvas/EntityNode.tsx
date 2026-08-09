'use client';

/**
 * EntityNode — custom React Flow node rendering a single entity.
 *
 * Header is colour-coded by entity type; each column row shows PK (🔑), FK (🔗),
 * and PII (⚠) markers plus its physical data type.
 */

import { Handle, Position, type NodeProps } from '@xyflow/react';

import type { EntityNode as EntityNodeType, EntityType } from '@/types/schema';

/** Accent colour per entity type for quick visual scanning. */
export const ENTITY_ACCENT: Record<EntityType, string> = {
  TABLE: '#64748b',
  FACT: '#2563eb',
  DIMENSION: '#16a34a',
  HUB: '#9333ea',
  LINK: '#ea580c',
  SATELLITE: '#0891b2',
};

export default function EntityNode({ data, selected }: NodeProps<EntityNodeType>) {
  const accent = ENTITY_ACCENT[data.entity_type] ?? '#64748b';

  return (
    <div
      style={{
        minWidth: 220,
        borderRadius: 8,
        border: `1px solid ${selected ? accent : '#e2e8f0'}`,
        boxShadow: selected ? `0 0 0 2px ${accent}33` : '0 1px 3px #0000001a',
        background: '#ffffff',
        fontSize: 12,
        overflow: 'hidden',
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div
        style={{
          background: accent,
          color: '#ffffff',
          padding: '6px 10px',
          fontWeight: 600,
          display: 'flex',
          justifyContent: 'space-between',
          gap: 8,
        }}
      >
        <span>{data.entity_name}</span>
        <span style={{ opacity: 0.85, fontWeight: 400 }}>{data.entity_type}</span>
      </div>
      {data.grain && (
        <div
          style={{
            padding: '2px 10px',
            fontStyle: 'italic',
            color: '#64748b',
            borderBottom: '1px solid #f1f5f9',
          }}
        >
          grain: {data.grain}
        </div>
      )}
      <ul style={{ listStyle: 'none', margin: 0, padding: '4px 0' }}>
        {data.columns.map((col) => (
          <li
            key={col.name}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              gap: 12,
              padding: '2px 10px',
            }}
          >
            <span>
              {col.is_primary_key && <strong title="Primary key">🔑 </strong>}
              {col.is_foreign_key && <span title="Foreign key">🔗 </span>}
              {col.name}
              {col.is_pii && (
                <span title={col.pii_type ?? 'PII'} style={{ color: '#dc2626' }}>
                  {' '}
                  ⚠
                </span>
              )}
            </span>
            <span style={{ color: '#94a3b8' }}>{col.data_type}</span>
          </li>
        ))}
      </ul>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
