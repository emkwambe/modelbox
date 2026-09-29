'use client';

/**
 * RelationshipColumnsModal — choosing which columns a relationship joins.
 *
 * Connecting two entities on the canvas opens this instead of adding an edge
 * straight away (Sprint 8 Step 3, owner decision). An edge drawn between node
 * handles names entities only, and saved that way it could never become a
 * foreign key: every relationship drawn before this step is exactly that, and
 * shows on the canvas as unresolved.
 *
 * The target's primary key is proposed as the referenced columns, in key
 * order, and each is paired with a source column of the same name where there
 * is one. Every pair is editable, pairs can be added or removed, so a
 * composite foreign key is one relationship. Nothing is added until every
 * pair has both columns; Cancel adds nothing.
 */

import { useState } from 'react';

import { Button, Field, Modal, Select, StatusText } from '@/components/ui';
import { useCanvasStore } from '@/store/canvasStore';
import { space } from '@/styles/tokens';
import type { Cardinality, EntityNodeData } from '@/types/schema';

const CARDINALITIES: Cardinality[] = ['N:1', '1:1', '1:N', 'N:M'];

interface Pair {
  from: string;
  to: string;
}

/** The pairs to start from: the saved ones, or the target's key matched by name. */
export function proposedPairs(
  source: EntityNodeData,
  target: EntityNodeData,
  saved?: { from_columns: string[]; to_columns: string[] },
): Pair[] {
  if (saved && saved.from_columns.length + saved.to_columns.length > 0) {
    const width = Math.max(saved.from_columns.length, saved.to_columns.length);
    return Array.from({ length: width }, (_, i) => ({
      from: saved.from_columns[i] ?? '',
      to: saved.to_columns[i] ?? '',
    }));
  }
  const key = target.primary_key?.length
    ? target.primary_key
    : target.columns.filter((c) => c.is_primary_key).map((c) => c.name);
  const sourceNames = new Set(source.columns.map((c) => c.name));
  if (key.length === 0) return [{ from: '', to: '' }];
  return key.map((to) => ({ from: sourceNames.has(to) ? to : '', to }));
}

export default function RelationshipColumnsModal() {
  const pending = useCanvasStore((s) => s.pendingConnection);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const connectColumns = useCanvasStore((s) => s.connectColumns);
  const cancelConnection = useCanvasStore((s) => s.cancelConnection);

  if (!pending) return null;
  const source = nodes.find((n) => n.id === pending.source)?.data;
  const target = nodes.find((n) => n.id === pending.target)?.data;
  if (!source || !target) return null;
  const existing = pending.edgeId ? edges.find((e) => e.id === pending.edgeId)?.data : undefined;

  return (
    <PairsForm
      // Remount per relationship, so the proposal is recomputed.
      key={`${pending.source}->${pending.target}:${pending.edgeId ?? 'new'}`}
      source={source}
      target={target}
      initialPairs={proposedPairs(source, target, existing)}
      initialCardinality={existing?.cardinality ?? 'N:1'}
      onConfirm={(pairs, cardinality) =>
        connectColumns(
          pairs.map((p) => p.from),
          pairs.map((p) => p.to),
          cardinality,
        )
      }
      onCancel={cancelConnection}
    />
  );
}

function PairsForm({
  source,
  target,
  initialPairs,
  initialCardinality,
  onConfirm,
  onCancel,
}: {
  source: EntityNodeData;
  target: EntityNodeData;
  initialPairs: Pair[];
  initialCardinality: Cardinality;
  onConfirm: (pairs: Pair[], cardinality: Cardinality) => void;
  onCancel: () => void;
}) {
  const [pairs, setPairs] = useState<Pair[]>(initialPairs);
  const [cardinality, setCardinality] = useState<Cardinality>(initialCardinality);

  const complete = pairs.length > 0 && pairs.every((p) => p.from && p.to);
  const repeated =
    new Set(pairs.map((p) => p.from)).size !== pairs.length ||
    new Set(pairs.map((p) => p.to)).size !== pairs.length;

  const update = (index: number, side: keyof Pair, value: string) =>
    setPairs((current) => current.map((p, i) => (i === index ? { ...p, [side]: value } : p)));

  return (
    <Modal
      title="Choose the columns"
      description={`${source.entity_name} references ${target.entity_name}. Pair each referencing column with the column it references.`}
      onClose={onCancel}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (complete && !repeated) onConfirm(pairs, cardinality);
        }}
        style={{ display: 'flex', flexDirection: 'column', gap: space.md }}
      >
        {pairs.map((pair, index) => (
          <div key={index} style={{ display: 'flex', gap: space.sm, alignItems: 'flex-end' }}>
            <Field label={`${source.entity_name} column ${index + 1}`}>
              <Select value={pair.from} onChange={(e) => update(index, 'from', e.target.value)}>
                <option value="">— choose —</option>
                {source.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={`${target.entity_name} column ${index + 1}`}>
              <Select value={pair.to} onChange={(e) => update(index, 'to', e.target.value)}>
                <option value="">— choose —</option>
                {target.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            {pairs.length > 1 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPairs((current) => current.filter((_, i) => i !== index))}
                aria-label={`Remove pair ${index + 1}`}
              >
                Remove
              </Button>
            )}
          </div>
        ))}
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setPairs((current) => [...current, { from: '', to: '' }])}
          >
            Add column pair
          </Button>
        </div>
        <Field label="Cardinality">
          <Select value={cardinality} onChange={(e) => setCardinality(e.target.value as Cardinality)}>
            {CARDINALITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </Field>
        {repeated && <StatusText tone="breaking">A column appears in two pairs.</StatusText>}
        <div style={{ display: 'flex', gap: space.sm, justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!complete || repeated}>
            Add relationship
          </Button>
        </div>
      </form>
    </Modal>
  );
}
