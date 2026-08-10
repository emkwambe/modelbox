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
  // Columns holding a dangling foreign-key reference (precise source metadata).
  const danglingColumns = new Set(
    issues
      .filter(
        (i) =>
          i.code === 'DANGLING_REF' &&
          i.entity_name === data.entity_name &&
          i.column_name,
      )
      .map((i) => i.column_name as string),
  );
  // Columns flagged as unclassified PII by the governance lint (Pick 1).
  const piiExposureColumns = new Set(
    issues
      .filter((i) => i.code === 'PII_EXPOSURE' && i.column_name)
      .map((i) => i.column_name as string),
  );
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
        minWidth: 230,
        borderRadius: 10,
        border: `${statusColor ? 2 : 1}px solid ${borderColor}`,
        boxShadow: statusColor
          ? `0 0 0 3px ${statusColor}33`
          : selected
            ? `0 0 0 2px ${accent}33, 0 4px 14px rgba(15,23,42,0.10)`
            : '0 2px 8px rgba(15,23,42,0.08)',
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
          padding: '7px 11px',
          fontWeight: 700,
          letterSpacing: 0.2,
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
        {data.columns.map((col) => {
          const isDangling = danglingColumns.has(col.name);
          const isPiiExposure = !isDangling && piiExposureColumns.has(col.name);
          return (
            <li
              key={col.name}
              title={
                isDangling
                  ? 'Foreign key references a missing entity.'
                  : isPiiExposure
                    ? 'Looks like PII but is not classified (set is_pii/pii_type).'
                    : undefined
              }
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 12,
                padding: '2px 10px',
                background: isDangling
                  ? '#fef2f2'
                  : isPiiExposure
                    ? '#fffbeb'
                    : undefined,
                color: isDangling ? ERROR_COLOR : undefined,
                fontWeight: isDangling || isPiiExposure ? 600 : undefined,
              }}
            >
              <span>
                {col.is_primary_key && <strong title="Primary key">🔑 </strong>}
                {col.is_foreign_key && <span title="Foreign key">🔗 </span>}
                {col.name}
                {isDangling && <span title="Dangling reference"> ⛔</span>}
                {isPiiExposure && (
                  <span title="Unclassified PII" style={{ color: WARNING_COLOR }}>
                    {' '}
                    🔓
                  </span>
                )}
                {col.is_pii && (
                  <span
                    title={col.pii_type ?? 'PII'}
                    style={{ color: '#dc2626' }}
                  >
                    {' '}
                    ⚠
                  </span>
                )}
              </span>
              <span style={{ color: '#94a3b8' }}>{col.data_type}</span>
            </li>
          );
        })}
      </ul>
      <Handle
        type="source"
        position={Position.Bottom}
        style={
          danglingColumns.size > 0
            ? { background: ERROR_COLOR, width: 10, height: 10 }
            : undefined
        }
      />
    </div>
  );
}
