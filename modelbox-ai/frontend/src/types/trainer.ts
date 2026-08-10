/**
 * ModelBox Trainer (Pillar 3) frontend types — mirror the backend trainer
 * schemas. Kept in a dedicated module to preserve module isolation.
 */

import type { Entity, Relationship } from '@/types/schema';

export interface TrainerGraph {
  entities: Entity[];
  relationships: Relationship[];
}

export interface Assignment {
  assignment_id: string;
  workspace_id: string;
  title: string;
  description: string;
  flawed_graph_json?: TrainerGraph | null;
  expected_graph_invariants: Record<string, boolean>;
}

export interface SocraticStep {
  next_question: string;
  hints: string[];
}

export interface GradeResult {
  score: number;
  passed_invariants: string[];
  violations: string[];
}

export interface SocraticMessage {
  role: 'assistant' | 'user';
  content: string;
}
