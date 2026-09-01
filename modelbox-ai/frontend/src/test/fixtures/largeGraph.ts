/**
 * A synthetic canvas graph of arbitrary size.
 *
 * F4 — "canvas remains usable at 500 tables" — had no evidence of any kind, and
 * the reason was upstream of the tests: **there was no way to produce a
 * 500-table model.** The largest thing in the tree is the Requirements Library
 * at 28 entities across all six templates, and the backend's synthetic
 * generator makes *rows*, not tables. A criterion whose subject cannot be
 * constructed cannot be measured, so this file is the prerequisite for every
 * assertion about scale.
 *
 * **Synthetic, deliberately.** The gold graphs are a curriculum and marketing
 * asset and must not be seeded with anything shaped to make a test pass
 * (`CLAUDE.md`, *Gold graphs*). A performance fixture is exactly that kind of
 * shaping — it wants pathological width and depth — so it belongs here, beside
 * the other defect reproductions, and never in `fixtures/gold/`.
 *
 * **Column counts vary on purpose.** A fixture where every entity is the same
 * height cannot expose a layout that assumes a fixed height, which is the
 * defect at `canvasStore.ts:NODE_HEIGHT`. `columnsFor` therefore spreads
 * entities from narrow to very wide across the requested range.
 */

import type {
  Column,
  Entity,
  EntityNode,
  EntityType,
  Relationship,
  RelationshipEdge,
} from '@/types/schema';

export interface LargeGraphOptions {
  /** How many entities. F4's number is 500. */
  entities: number;
  /** Narrowest entity, in columns. */
  minColumns?: number;
  /** Widest entity, in columns. A real warehouse fact table reaches 40. */
  maxColumns?: number;
  /** One in every `factEvery` entities is a FACT that references dimensions. */
  factEvery?: number;
}

/**
 * Column count for entity `i`, spread deterministically across the range.
 *
 * Deterministic rather than random: a fixture that differs run to run turns a
 * failure into a story about the seed. The spread is a simple sawtooth, which
 * is enough to give the layout assertions a mix of short and tall nodes.
 */
export function columnsFor(
  index: number,
  minColumns: number,
  maxColumns: number,
): number {
  const span = Math.max(1, maxColumns - minColumns + 1);
  return minColumns + (index % span);
}

function makeColumns(entityName: string, count: number): Column[] {
  const columns: Column[] = [
    {
      name: `${entityName}_sk`,
      data_type: 'BIGINT',
      is_primary_key: true,
      is_foreign_key: false,
      is_pii: false,
      pii_type: null,
      is_metric: false,
      is_nullable: false,
    },
  ];
  for (let c = 1; c < count; c += 1) {
    columns.push({
      name: `attribute_${c}`,
      data_type: c % 3 === 0 ? 'NUMERIC(18,2)' : 'VARCHAR(255)',
      is_primary_key: false,
      is_foreign_key: false,
      is_pii: false,
      pii_type: null,
      is_metric: c % 3 === 0,
      is_nullable: true,
    });
  }
  return columns;
}

export interface LargeGraph {
  entities: Entity[];
  relationships: Relationship[];
  nodes: EntityNode[];
  edges: RelationshipEdge[];
}

export function makeLargeGraph({
  entities: entityCount,
  minColumns = 6,
  maxColumns = 40,
  factEvery = 10,
}: LargeGraphOptions): LargeGraph {
  const entities: Entity[] = [];
  const relationships: Relationship[] = [];

  for (let i = 0; i < entityCount; i += 1) {
    const isFact = i % factEvery === 0;
    const name = isFact ? `fact_events_${i}` : `dim_attribute_${i}`;
    const type: EntityType = isFact ? 'FACT' : 'DIMENSION';
    const columns = makeColumns(name, columnsFor(i, minColumns, maxColumns));

    // A fact carries a foreign key to each dimension in its block, which is
    // what gives the graph edges to route and a fan-out to lay out.
    if (isFact) {
      for (let d = 1; d < factEvery && i + d < entityCount; d += 1) {
        const target = `dim_attribute_${i + d}`;
        columns.push({
          name: `${target}_sk`,
          data_type: 'BIGINT',
          is_primary_key: false,
          is_foreign_key: true,
          is_pii: false,
          pii_type: null,
          is_metric: false,
          is_nullable: false,
          references: `${target}.${target}_sk`,
        });
        relationships.push({
          from: `${name}.${target}_sk`,
          to: `${target}.${target}_sk`,
          cardinality: 'N:1',
        });
      }
    }

    entities.push({
      entity_name: name,
      entity_type: type,
      description: null,
      grain: isFact ? 'one row per event' : null,
      tier: null,
      freshness_sla: null,
      agg_time_column: null,
      // Every node starts at the origin. Position is what `applyLayout` is
      // supposed to compute, so a fixture that pre-positions them would hide
      // the thing the layout assertions are for.
      canvas_position_x: 0,
      canvas_position_y: 0,
      columns,
    });
  }

  const nodes: EntityNode[] = entities.map((entity) => ({
    id: entity.entity_name,
    type: 'entity' as const,
    position: { x: entity.canvas_position_x, y: entity.canvas_position_y },
    data: {
      entity_name: entity.entity_name,
      entity_type: entity.entity_type,
      description: entity.description,
      grain: entity.grain,
      tier: entity.tier,
      freshness_sla: entity.freshness_sla,
      agg_time_column: entity.agg_time_column,
      columns: entity.columns,
    },
  }));

  const edges: RelationshipEdge[] = relationships.map((rel, index) => {
    const source = rel.from.split('.', 1)[0] ?? rel.from;
    const target = rel.to.split('.', 1)[0] ?? rel.to;
    return {
      id: `rel-${index}-${source}-${target}`,
      source,
      target,
      data: { cardinality: rel.cardinality, from_ref: rel.from, to_ref: rel.to },
    };
  });

  return { entities, relationships, nodes, edges };
}
