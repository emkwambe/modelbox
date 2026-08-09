'use client';

/**
 * EntityNode — custom React Flow node rendering a single entity.
 *
 * Header is colour-coded by entity type; each column row shows PK (🔑), FK (🔗),
 * and PII (⚠) markers plus its physical data type.
 */

import { Handle, Position, type NodeProps } from '@xyflow/react';

import { useCanvasStore } from '@/store/canvasStore';
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

const ERROR_COLOR = '#dc2626';
const WARNING_COLOR = '#f59e0b';

export default function EntityNode({ data, selected }: NodeProps<EntityNodeType>) {
  const accent = ENTITY_ACCENT[data.entity_type] ?? '#64748b';

  // Pull this entity's lint issues from the validation report (FR-2.3).
  const issues = useCanvasStore(
    (s) =>
      s.validation?.issues.filter((i) =>
        i.entities.includes(data.entity_name),
      ) ?? [],
  );
  const hasError = issues.some((i) => i.severity === 'error');
  const hasWarning = issues.some((i) => i.severity === 'warning');
  const missingPk = issues.some((i) => i.code === 'MISSING_PK');
  const statusColor = hasError
    ? ERROR_COLOR
    : hasWarning
      ? WARNING_COLOR
      : null;
  const borderColor = statusColor ?? (selected ? accent : '#e2e8f0');
  const tooltip = issues.map((i) => `[${i.code}] ${i.message}`).join('\n');

  return (
    <div
      style={{
        minWidth: 220,
        borderRadius: 8,
        border: `${statusColor ? 2 : 1}px solid ${borderColor}`,
        boxShadow: statusColor
          ? `0 0 0 3px ${statusColor}33`
          : selected
            ? `0 0 0 2px ${accent}33`
            : '0 1px 3px #0000001a',
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
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {issues.length > 0 && (
            <span
              title={tooltip}
              style={{
                background: statusColor ?? WARNING_COLOR,
                color: '#fff',
                borderRadius: 10,
                padding: '0 6px',
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              ⚠ {issues.length}
            </span>
          )}
          <span style={{ opacity: 0.85, fontWeight: 400 }}>
            {data.entity_type}
          </span>
        </span>
      </div>
      {missingPk && (
        <div
          title="This entity has no primary key."
          style={{
            padding: '2px 10px',
            background: '#fffbeb',
            color: WARNING_COLOR,
            fontWeight: 600,
            borderBottom: `1px solid ${WARNING_COLOR}33`,
          }}
        >
          ⚠ missing primary key
        </div>
      )}
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
