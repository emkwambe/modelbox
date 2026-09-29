/**
 * The canvas graph and the API's graph, converted both ways.
 *
 * Keys and constraints have one source (Sprint 8 Step 3): an entity's
 * `primary_key`, `unique_constraints` and `check_constraints`, and each
 * relationship's column lists. The column editor still toggles the familiar
 * one-column flags, so on save the lists are rebuilt from them:
 *
 * - `primary_key` keeps its saved order for columns still flagged, and appends
 *   newly flagged columns in column order;
 * - a UNIQUE or CHECK over several columns is kept as it is while its columns
 *   exist; a one-column one is kept, name and place, while its column's
 *   `is_unique` / `check_expression` still says the same, and replaced (at
 *   the end) when the editor changed it.
 *
 * Saved constraints keep their order, so a model reopens exactly as saved.
 *
 * The derived flags are then left out of the payload, because the server
 * refuses a flag that disagrees with a list, and derives them itself.
 */

import type {
  CheckConstraint,
  Column,
  Entity,
  EntityNodeData,
  Relationship,
  RelationshipEdgeData,
  UniqueConstraint,
} from '@/types/schema';

/** The flags the server derives from the lists. Never sent. */
const DERIVED: ReadonlyArray<keyof Column> = [
  'is_primary_key',
  'is_unique',
  'check_expression',
  'is_foreign_key',
  'references',
];

/** Split an older `entity.column` ref; a bare entity has no column. */
function splitRef(ref: string): [string, string[]] {
  const dot = ref.indexOf('.');
  return dot === -1 ? [ref, []] : [ref.slice(0, dot), [ref.slice(dot + 1)]];
}

/** A relationship as edge data: entities and column lists, whatever form it came in. */
export function relationshipToEdgeData(rel: Relationship): RelationshipEdgeData {
  const [fromEntity, fromDotted] = splitRef(rel.from);
  const [toEntity, toDotted] = splitRef(rel.to);
  return {
    cardinality: rel.cardinality,
    from_ref: fromEntity,
    to_ref: toEntity,
    from_columns: rel.from_columns?.length ? [...rel.from_columns] : fromDotted,
    to_columns: rel.to_columns?.length ? [...rel.to_columns] : toDotted,
    name: rel.name ?? null,
  };
}

/** Whether every referencing column is paired with a referenced one. */
export function isResolved(data: Pick<RelationshipEdgeData, 'from_columns' | 'to_columns'>): boolean {
  return data.from_columns.length > 0 && data.from_columns.length === data.to_columns.length;
}

/** One-column CHECKs joined as the server derives `check_expression`. */
function joined(expressions: string[]): string | null {
  if (expressions.length === 0) return null;
  if (expressions.length === 1) return expressions[0] ?? null;
  return expressions.map((e) => `(${e})`).join(' AND ');
}

/** The entity's key and constraint lists, rebuilt from its columns' flags. */
export function constraintLists(data: EntityNodeData): {
  primary_key: string[];
  unique_constraints: UniqueConstraint[];
  check_constraints: CheckConstraint[];
} {
  const names = new Set(data.columns.map((c) => c.name));
  const flagged = data.columns.filter((c) => c.is_primary_key).map((c) => c.name);
  const saved = (data.primary_key ?? []).filter((n) => flagged.includes(n));
  const primary_key = [...saved, ...flagged.filter((n) => !saved.includes(n))];

  // Saved constraints keep their places, so a model reopens in its saved
  // order; what the editor added is appended.
  const flaggedUnique = new Set(data.columns.filter((c) => c.is_unique).map((c) => c.name));
  const unique_constraints: UniqueConstraint[] = (data.unique_constraints ?? []).filter((u) =>
    u.columns.length > 1
      ? u.columns.every((c) => names.has(c))
      : flaggedUnique.delete(u.columns[0] ?? ''),
  );
  for (const column of data.columns) {
    if (flaggedUnique.has(column.name)) unique_constraints.push({ name: null, columns: [column.name] });
  }

  const savedChecks = data.check_constraints ?? [];
  const isOneColumn = (k: CheckConstraint) => k.columns?.length === 1;
  const edited = new Map<string, string>();
  for (const column of data.columns) {
    const expression = column.check_expression?.trim() ?? '';
    const saved = savedChecks.filter((k) => isOneColumn(k) && k.columns?.[0] === column.name);
    if ((joined(saved.map((k) => k.expression)) ?? '') !== expression) edited.set(column.name, expression);
  }
  const check_constraints: CheckConstraint[] = savedChecks.filter((k) =>
    isOneColumn(k)
      ? names.has(k.columns?.[0] ?? '') && !edited.has(k.columns?.[0] ?? '')
      : (k.columns ?? []).every((c) => names.has(c)),
  );
  for (const [column, expression] of edited) {
    if (expression) check_constraints.push({ name: null, expression, columns: [column] });
  }
  return { primary_key, unique_constraints, check_constraints };
}

/** A column as sent: everything but the flags the server derives. */
export function columnPayload(column: Column): Column {
  const out = { ...column } as Record<string, unknown>;
  for (const flag of DERIVED) delete out[flag];
  return out as unknown as Column;
}

/** An entity as sent to `PUT /model/{id}/graph`. */
export function entityPayload(
  data: EntityNodeData,
  position: { x: number; y: number },
): Entity {
  return {
    entity_name: data.entity_name,
    entity_type: data.entity_type,
    description: data.description ?? null,
    grain: data.grain ?? null,
    tier: data.tier ?? null,
    freshness_sla: data.freshness_sla ?? null,
    agg_time_column: data.agg_time_column ?? null,
    business_name: data.business_name ?? null,
    business_owner: data.business_owner ?? null,
    it_steward: data.it_steward ?? null,
    authoritative_source: data.authoritative_source ?? null,
    canvas_position_x: position.x,
    canvas_position_y: position.y,
    columns: data.columns.map(columnPayload),
    ...constraintLists(data),
  };
}

/** A relationship as sent: entities, column lists, name and cardinality. */
export function relationshipPayload(data: RelationshipEdgeData): Relationship {
  return {
    from: data.from_ref,
    to: data.to_ref,
    from_columns: [...data.from_columns],
    to_columns: [...data.to_columns],
    name: data.name ?? null,
    cardinality: data.cardinality,
  };
}

/** Rename one column in an entity's constraint lists. */
export function renameInLists(
  data: EntityNodeData,
  oldName: string,
  newName: string,
): Pick<EntityNodeData, 'primary_key' | 'unique_constraints' | 'check_constraints'> {
  const swap = (names: string[] | undefined) => names?.map((n) => (n === oldName ? newName : n));
  return {
    primary_key: swap(data.primary_key),
    unique_constraints: data.unique_constraints?.map((u) => ({ ...u, columns: swap(u.columns) ?? [] })),
    check_constraints: data.check_constraints?.map((k) => ({ ...k, columns: swap(k.columns) })),
  };
}
