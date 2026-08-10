/**
 * Trainer lab catalog. Each lab JSON (see _LAB_SCHEMA.md) is imported here and
 * exposed as a typed `Lab`. `labToGraph` normalizes a lab's flawed graph into
 * the canvas Entity/Relationship shape (adding default canvas positions).
 */

import type {
  Cardinality,
  Column,
  Entity,
  EntityType,
  Relationship,
} from '@/types/schema';

import m1lab1 from './m1_lab1_grain_and_fanout.json';
import m2lab1 from './m2_lab1_semantic_grain_and_fanout.json';

export interface LabFlaw {
  code: string;
  target: string;
  hint: string;
  fix: string;
}

interface RawColumn {
  name: string;
  data_type: string;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  is_pii: boolean;
  is_metric: boolean;
  aggregation?: string | null;
  description?: string | null;
}

interface RawEntity {
  entity_name: string;
  entity_type: string;
  grain?: string | null;
  description?: string | null;
  columns: RawColumn[];
}

interface RawRelationship {
  from: string;
  to: string;
  cardinality: string;
}

export interface Lab {
  id: string;
  module: number;
  edition: string;
  title: string;
  difficulty: string;
  brief: string;
  graph: { entities: RawEntity[]; relationships: RawRelationship[] };
  expected_flaws: LabFlaw[];
  solution_notes: string;
}

export const LABS: Lab[] = [
  m1lab1 as unknown as Lab,
  m2lab1 as unknown as Lab,
];

/** Convert a lab's flawed graph into loadable canvas entities/relationships. */
export function labToGraph(lab: Lab): {
  entities: Entity[];
  relationships: Relationship[];
} {
  const entities: Entity[] = lab.graph.entities.map((e) => ({
    entity_name: e.entity_name,
    entity_type: e.entity_type as EntityType,
    description: e.description ?? null,
    grain: e.grain ?? null,
    canvas_position_x: 0,
    canvas_position_y: 0,
    columns: e.columns.map(
      (c): Column => ({
        name: c.name,
        data_type: c.data_type,
        is_primary_key: c.is_primary_key,
        is_foreign_key: c.is_foreign_key,
        is_pii: c.is_pii,
        is_metric: c.is_metric,
        aggregation: c.aggregation ?? null,
        description: c.description ?? null,
      }),
    ),
  }));
  const relationships: Relationship[] = lab.graph.relationships.map((r) => ({
    from: r.from,
    to: r.to,
    cardinality: r.cardinality as Cardinality,
  }));
  return { entities, relationships };
}
