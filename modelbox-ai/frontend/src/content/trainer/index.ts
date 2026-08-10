/**
 * Trainer lab catalog. Each lab JSON (see _LAB_SCHEMA.md) is imported here and
 * exposed as a typed `Lab`. `labToGraph` normalizes a lab's flawed graph into
 * the canvas Entity/Relationship shape (adding default canvas positions).
 */

import type {
  AssetTier,
  Cardinality,
  Column,
  Entity,
  EntityType,
  Relationship,
} from '@/types/schema';

import m1lab1 from './m1_lab1_grain_and_fanout.json';
import m2lab1 from './m2_lab1_semantic_grain_and_fanout.json';
import m3lab1 from './m3_lab1_governance_and_contracts.json';
import m4lab1 from './m4_lab1_quality_and_testing.json';
import m5capstone from './m5_capstone_mastery.json';

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
  min_value?: number | null;
  max_value?: number | null;
  regex_pattern?: string | null;
}

interface RawEntity {
  entity_name: string;
  entity_type: string;
  grain?: string | null;
  description?: string | null;
  tier?: string | null;
  freshness_sla?: string | null;
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
  m3lab1 as unknown as Lab,
  m4lab1 as unknown as Lab,
  m5capstone as unknown as Lab,
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
    tier: (e.tier ?? null) as AssetTier | null,
    freshness_sla: e.freshness_sla ?? null,
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
        min_value: c.min_value ?? null,
        max_value: c.max_value ?? null,
        regex_pattern: c.regex_pattern ?? null,
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
