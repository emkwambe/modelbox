'use client';

/**
 * ColumnSemanticEditor — the Visual Semantic Metric Builder popover.
 *
 * Carries the Sprint 2 physical constraints — nullability, uniqueness, default
 * and check — plus the column-level foreign-key target. `stable_id` is shown
 * read-only: it is server-assigned and never reused, and a field that can be
 * edited is not stable.
 *
 * When a column is selected on the canvas, this floating editor lets the user
 * declare its semantic role: a MEASURE (with an aggregation) or a DIMENSION.
 * Edits set `is_metric` / `aggregation` on the column; Save (in the toolbar)
 * persists them and they flow into the MetricFlow / Cube / LookML exports.
 */

import { useCanvasStore } from '@/store/canvasStore';
import { color } from '@/styles/tokens';

const AGGREGATIONS = ['SUM', 'COUNT', 'COUNT_DISTINCT', 'AVG', 'MIN', 'MAX'];

export default function ColumnSemanticEditor() {
  const selectedColumn = useCanvasStore((s) => s.selectedColumn);
  const nodes = useCanvasStore((s) => s.nodes);
  const updateColumn = useCanvasStore((s) => s.updateColumn);
  const renameColumn = useCanvasStore((s) => s.renameColumn);
  const selectColumn = useCanvasStore((s) => s.selectColumn);

  if (!selectedColumn) return null;

  const node = nodes.find((n) => n.id === selectedColumn.entityName);
  const column = node?.data.columns.find(
    (c) => c.name === selectedColumn.columnName,
  );
  if (!node || !column) return null;

  // Qualified targets a foreign key can point at: any column on another
  // entity. Self-references are excluded — legal SQL, but almost always a
  // modelling mistake on a canvas.
  const referenceTargets = nodes
    .filter((n) => n.id !== selectedColumn.entityName)
    .flatMap((n) => n.data.columns.map((c) => `${n.id}.${c.name}`))
    .sort();

  const isMeasure = column.is_metric;
  const agg = (column.aggregation ?? 'SUM').toUpperCase();

  function setDimension() {
    updateColumn(selectedColumn!.entityName, selectedColumn!.columnName, {
      is_metric: false,
      aggregation: null,
    });
  }

  function setMeasure(nextAgg: string) {
    updateColumn(selectedColumn!.entityName, selectedColumn!.columnName, {
      is_metric: true,
      aggregation: nextAgg,
    });
  }

  return (
    <div style={card}>
      <div style={header}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>Semantic role</div>
          <div style={{ fontSize: 12, color: color.neutral[500] }}>
            <code>
              {selectedColumn.entityName}.{selectedColumn.columnName}
            </code>
            {column.stable_id != null && (
              <span
                style={{ marginLeft: 6 }}
                title="Server-assigned stable identity. Never reused, never editable."
              >
                #{column.stable_id}
              </span>
            )}{' '}
            · {column.data_type}
          </div>
        </div>
        <button
          type="button"
          onClick={() => selectColumn(selectedColumn.entityName, null)}
          style={closeBtn}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <label
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          marginTop: 10,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: color.neutral[600] }}>
          Name
        </span>
        <input
          key={`col-${selectedColumn.entityName}.${selectedColumn.columnName}`}
          defaultValue={column.name}
          onBlur={(e) =>
            renameColumn(
              selectedColumn!.entityName,
              column.name,
              e.target.value,
            )
          }
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
          }}
          placeholder="e.g. customer_sk"
          style={select}
        />
      </label>

      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginTop: 10,
          fontSize: 13,
          fontWeight: 600,
          color: color.neutral[700],
        }}
      >
        <input
          type="checkbox"
          checked={Boolean(column.is_primary_key)}
          onChange={(e) =>
            updateColumn(selectedColumn!.entityName, selectedColumn!.columnName, {
              is_primary_key: e.target.checked,
            })
          }
        />
        🔑 Primary key
      </label>

      <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
        <button
          type="button"
          onClick={setDimension}
          style={roleBtn(!isMeasure)}
        >
          Dimension
        </button>
        <button
          type="button"
          onClick={() => setMeasure(agg)}
          style={roleBtn(isMeasure)}
        >
          Σ Measure
        </button>
      </div>

      {isMeasure && (
        <label
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            marginTop: 10,
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: color.neutral[600] }}>
            Aggregation
          </span>
          <select
            value={agg}
            onChange={(e) => setMeasure(e.target.value)}
            style={select}
          >
            {AGGREGATIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
      )}

      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginTop: 12,
          fontSize: 13,
          fontWeight: 600,
          color: color.neutral[700],
        }}
      >
        <input
          type="checkbox"
          checked={Boolean(column.is_pii)}
          onChange={(e) =>
            updateColumn(selectedColumn!.entityName, selectedColumn!.columnName, {
              is_pii: e.target.checked,
              pii_type: e.target.checked ? (column.pii_type ?? 'EMAIL') : null,
            })
          }
        />
        Contains PII
      </label>
      {column.is_pii && (
        <select
          value={column.pii_type ?? 'EMAIL'}
          onChange={(e) =>
            updateColumn(selectedColumn!.entityName, selectedColumn!.columnName, {
              pii_type: e.target.value as typeof column.pii_type,
            })
          }
          style={{ ...select, marginTop: 6 }}
        >
          {['EMAIL', 'SSN', 'PHONE', 'CREDIT_CARD', 'IBAN', 'NAME', 'ADDRESS'].map(
            (p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ),
          )}
        </select>
      )}

      <div style={qualityBox}>
        <div style={{ fontSize: 12, fontWeight: 700, color: color.neutral[700] }}>
          Quality rules
        </div>
        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
          <label style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={qualityLabel}>Min</span>
            <input
              type="number"
              value={column.min_value ?? ''}
              onChange={(e) =>
                updateColumn(
                  selectedColumn!.entityName,
                  selectedColumn!.columnName,
                  {
                    min_value:
                      e.target.value === '' ? null : Number(e.target.value),
                  },
                )
              }
              style={select}
            />
          </label>
          <label style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <span style={qualityLabel}>Max</span>
            <input
              type="number"
              value={column.max_value ?? ''}
              onChange={(e) =>
                updateColumn(
                  selectedColumn!.entityName,
                  selectedColumn!.columnName,
                  {
                    max_value:
                      e.target.value === '' ? null : Number(e.target.value),
                  },
                )
              }
              style={select}
            />
          </label>
        </div>
        <label
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 3,
            marginTop: 6,
          }}
        >
          <span style={qualityLabel}>Regex pattern</span>
          <input
            type="text"
            value={column.regex_pattern ?? ''}
            placeholder="^[^@]+@[^@]+$"
            onChange={(e) =>
              updateColumn(
                selectedColumn!.entityName,
                selectedColumn!.columnName,
                { regex_pattern: e.target.value === '' ? null : e.target.value },
              )
            }
            style={select}
          />
        </label>
      </div>

      <div style={qualityBox}>
        <div style={{ ...qualityLabel, marginBottom: 6 }}>Physical constraints</div>

        <label style={checkRow}>
          <input
            type="checkbox"
            checked={column.is_nullable === false}
            disabled={Boolean(column.is_primary_key)}
            onChange={(e) =>
              updateColumn(
                selectedColumn!.entityName,
                selectedColumn!.columnName,
                { is_nullable: !e.target.checked },
              )
            }
          />
          NOT NULL
          {column.is_primary_key && (
            <span style={{ fontSize: 11, color: color.neutral[500], fontWeight: 400 }}>
              (implied by the key)
            </span>
          )}
        </label>

        <label style={checkRow}>
          <input
            type="checkbox"
            checked={Boolean(column.is_unique)}
            onChange={(e) =>
              updateColumn(
                selectedColumn!.entityName,
                selectedColumn!.columnName,
                { is_unique: e.target.checked },
              )
            }
          />
          UNIQUE
        </label>

        <label style={fieldRow}>
          <span style={qualityLabel}>Default</span>
          <input
            type="text"
            value={column.default_value ?? ''}
            placeholder="e.g. 0, CURRENT_TIMESTAMP"
            onChange={(e) =>
              updateColumn(
                selectedColumn!.entityName,
                selectedColumn!.columnName,
                { default_value: e.target.value === '' ? null : e.target.value },
              )
            }
            style={select}
          />
        </label>

        <label style={fieldRow}>
          <span style={qualityLabel}>Check expression</span>
          <input
            type="text"
            value={column.check_expression ?? ''}
            placeholder="e.g. amount >= 0"
            onChange={(e) =>
              updateColumn(
                selectedColumn!.entityName,
                selectedColumn!.columnName,
                {
                  check_expression:
                    e.target.value === '' ? null : e.target.value,
                },
              )
            }
            style={select}
          />
        </label>

        <label style={fieldRow}>
          <span style={qualityLabel}>References</span>
          <select
            value={column.references ?? ''}
            onChange={(e) =>
              updateColumn(
                selectedColumn!.entityName,
                selectedColumn!.columnName,
                { references: e.target.value === '' ? null : e.target.value },
              )
            }
            style={select}
          >
            <option value="">— none —</option>
            {referenceTargets.map((target) => (
              <option key={target} value={target}>
                {target}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p style={{ fontSize: 11, color: color.neutral[500], margin: '10px 0 0' }}>
        Save the model to persist. Declared measures drive the exports; classified
        PII clears the exposure warning; quality rules export as dbt / ODCS tests.
      </p>
    </div>
  );
}

const card: React.CSSProperties = {
  position: 'absolute',
  left: 16,
  bottom: 16,
  width: 280,
  zIndex: 30,
  background: color.white,
  border: `1px solid ${color.neutral[200]}`,
  borderRadius: 10,
  // `neutral-900` at 0.16 as a hex-alpha suffix, so the shadow stays derived.
  boxShadow: `0 8px 24px ${color.neutral[900]}29`,
  padding: 14,
};

const header: React.CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 8,
};

const closeBtn: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: 15,
  color: color.neutral[500],
  cursor: 'pointer',
  lineHeight: 1,
};

const roleBtn = (active: boolean): React.CSSProperties => ({
  flex: 1,
  padding: '7px 10px',
  borderRadius: 6,
  border: `1px solid ${active ? color.blue : color.neutral[300]}`,
  background: active ? color.blue : color.white,
  color: active ? color.white : color.neutral[700],
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
});

const select: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: 6,
  border: `1px solid ${color.neutral[300]}`,
  fontSize: 13,
  width: '100%',
  boxSizing: 'border-box',
};

const qualityBox: React.CSSProperties = {
  marginTop: 12,
  paddingTop: 10,
  borderTop: `1px solid ${color.neutral[100]}`,
};

const checkRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginTop: 6,
  fontSize: 13,
  fontWeight: 600,
  color: color.neutral[700],
};

const fieldRow: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 3,
  marginTop: 6,
};

const qualityLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: color.neutral[600],
};
