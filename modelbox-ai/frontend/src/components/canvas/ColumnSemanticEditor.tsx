'use client';

/**
 * ColumnSemanticEditor — the Visual Semantic Metric Builder popover.
 *
 * When a column is selected on the canvas, this floating editor lets the user
 * declare its semantic role: a MEASURE (with an aggregation) or a DIMENSION.
 * Edits set `is_metric` / `aggregation` on the column; Save (in the toolbar)
 * persists them and they flow into the MetricFlow / Cube / LookML exports.
 */

import { useCanvasStore } from '@/store/canvasStore';

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
          <div style={{ fontSize: 12, color: '#64748b' }}>
            <code>
              {selectedColumn.entityName}.{selectedColumn.columnName}
            </code>{' '}
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
        <span style={{ fontSize: 12, fontWeight: 600, color: '#475569' }}>
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
          <span style={{ fontSize: 12, fontWeight: 600, color: '#475569' }}>
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
          color: '#334155',
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
        <div style={{ fontSize: 12, fontWeight: 700, color: '#334155' }}>
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

      <p style={{ fontSize: 11, color: '#94a3b8', margin: '10px 0 0' }}>
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
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: 10,
  boxShadow: '0 8px 24px rgba(15,23,42,0.16)',
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
  color: '#64748b',
  cursor: 'pointer',
  lineHeight: 1,
};

const roleBtn = (active: boolean): React.CSSProperties => ({
  flex: 1,
  padding: '7px 10px',
  borderRadius: 6,
  border: `1px solid ${active ? '#2563eb' : '#cbd5e1'}`,
  background: active ? '#2563eb' : '#ffffff',
  color: active ? '#ffffff' : '#334155',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
});

const select: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  fontSize: 13,
  width: '100%',
  boxSizing: 'border-box',
};

const qualityBox: React.CSSProperties = {
  marginTop: 12,
  paddingTop: 10,
  borderTop: '1px solid #f1f5f9',
};

const qualityLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: '#475569',
};
