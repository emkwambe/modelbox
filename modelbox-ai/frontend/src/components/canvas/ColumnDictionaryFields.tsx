'use client';

/**
 * ColumnDictionaryFields — the data dictionary fields a person supplies for a
 * column (Sprint 8 Step 4b): its definition, business name, permissible
 * values, unit, classification, critical-data-element flag and authoritative
 * source. Save the model to persist them.
 *
 * Nothing here sets a field's status. A value a person changes is recorded as
 * supplied by them and is pending review; "verified" is set only by the server,
 * when an approver asks and the three conditions hold.
 */

import { useEffect, useState } from 'react';

import { getClassificationScale } from '@/lib/api';
import { useCanvasStore } from '@/store/canvasStore';
import { color, radius, semantic, space, type } from '@/styles/tokens';
import type { ClassificationLevel, Column } from '@/types/schema';

/** One value per line, blank lines dropped; an empty list is no list. */
export function parsePermissibleValues(text: string): string[] | null {
  const values = text
    .split('\n')
    .map((v) => v.trim())
    .filter((v) => v !== '');
  return values.length ? values : null;
}

const CDE_OPTIONS: { value: string; label: string; stored: boolean | null }[] = [
  { value: '', label: 'Not assessed', stored: null },
  { value: 'yes', label: 'Yes', stored: true },
  { value: 'no', label: 'No', stored: false },
];

function cdeValue(stored: boolean | null | undefined): string {
  if (stored === true) return 'yes';
  if (stored === false) return 'no';
  return '';
}

export default function ColumnDictionaryFields({
  entityName,
  column,
}: {
  entityName: string;
  column: Column;
}) {
  const updateColumn = useCanvasStore((s) => s.updateColumn);
  const workspaceId = useCanvasStore((s) => s.workspaceId);
  const [levels, setLevels] = useState<ClassificationLevel[] | null>(null);
  const [levelsError, setLevelsError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    getClassificationScale(workspaceId)
      .then((scale) => {
        if (!cancelled) setLevels(scale.levels);
      })
      .catch(() => {
        if (!cancelled) setLevelsError('The classification scale could not be loaded.');
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  function set(patch: Partial<Column>) {
    updateColumn(entityName, column.name, patch);
  }

  const text = (value: string) => (value === '' ? null : value);
  const key = `${entityName}.${column.name}`;

  return (
    <div style={box}>
      <div style={heading}>Data dictionary</div>

      <label style={row}>
        <span style={label}>Definition</span>
        <textarea
          value={column.description ?? ''}
          rows={2}
          placeholder="What one value of this column means"
          onChange={(e) => set({ description: text(e.target.value) })}
          style={input}
        />
      </label>

      <label style={row}>
        <span style={label}>Business name</span>
        <input
          type="text"
          value={column.business_name ?? ''}
          onChange={(e) => set({ business_name: text(e.target.value) })}
          style={input}
        />
      </label>

      <label style={row}>
        <span style={label}>Permissible values (one per line)</span>
        <textarea
          key={`pv-${key}`}
          defaultValue={(column.permissible_values ?? []).join('\n')}
          rows={3}
          onBlur={(e) => set({ permissible_values: parsePermissibleValues(e.target.value) })}
          style={input}
        />
      </label>

      <label style={row}>
        <span style={label}>Unit</span>
        <input
          type="text"
          value={column.unit ?? ''}
          placeholder="e.g. USD, kg, each"
          onChange={(e) => set({ unit: text(e.target.value) })}
          style={input}
        />
      </label>

      <label style={row}>
        <span style={label}>Classification</span>
        {workspaceId ? (
          <select
            value={column.classification_level_id ?? ''}
            onChange={(e) => set({ classification_level_id: text(e.target.value) })}
            style={input}
            disabled={levels === null}
          >
            <option value="">— not classified —</option>
            {(levels ?? []).map((level) => (
              <option key={level.level_id} value={level.level_id}>
                {level.name}
              </option>
            ))}
          </select>
        ) : (
          <span style={note}>Save the model to classify its columns.</span>
        )}
        {levelsError && (
          <span role="alert" style={{ ...note, color: semantic.breaking.onLight }}>
            {levelsError}
          </span>
        )}
      </label>

      <label style={row}>
        <span style={label}>Critical data element</span>
        <select
          value={cdeValue(column.critical_data_element)}
          onChange={(e) =>
            set({
              critical_data_element:
                CDE_OPTIONS.find((o) => o.value === e.target.value)?.stored ?? null,
            })
          }
          style={input}
        >
          {CDE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label style={row}>
        <span style={label}>Authoritative source</span>
        <input
          type="text"
          value={column.authoritative_source ?? ''}
          placeholder="The system of record"
          onChange={(e) => set({ authoritative_source: text(e.target.value) })}
          style={input}
        />
      </label>

      <p style={note}>
        A value you change is recorded as supplied by you and is pending review. Only an approver&apos;s
        request can make a field verified, and only when its conditions hold.
      </p>
    </div>
  );
}

const box: React.CSSProperties = {
  marginTop: space.md,
  paddingTop: space.sm,
  borderTop: `1px solid ${color.neutral[100]}`,
};

const heading: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[700],
  marginBottom: space.xs,
};

const row: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: space.xs,
  marginTop: space.sm,
};

const label: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  fontWeight: type.uiXSmall.weight,
  color: color.neutral[600],
};

const input: React.CSSProperties = {
  padding: `${space.xs}px ${space.sm}px`,
  borderRadius: radius.md,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: type.uiSmall.size,
  width: '100%',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
};

const note: React.CSSProperties = {
  fontSize: type.uiXSmall.size,
  color: color.neutral[500],
  margin: `${space.sm}px 0 0`,
};
