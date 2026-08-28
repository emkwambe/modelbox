/**
 * Zustand store for the ERD canvas.
 *
 * Owns the visual graph state (nodes/edges), selection, paradigm/dialect
 * context, the latest validation report, and bounded undo/redo history. React
 * Flow change events are applied through the standard `applyNodeChanges` /
 * `applyEdgeChanges` helpers so the store stays the single source of truth.
 */

import { create } from 'zustand';
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react';
import dagre from 'dagre';

import { validateModel as apiValidateModel } from '@/lib/api';

import type {
  CanvasSnapshot,
  Cardinality,
  Column,
  Entity,
  EntityNode,
  EntityNodeData,
  Paradigm,
  Relationship,
  RelationshipEdge,
  SynthesizeResponse,
  ValidationReport,
} from '@/types/schema';

const HISTORY_LIMIT = 50;
const NODE_WIDTH = 240;
const NODE_HEIGHT = 160;

type LayoutDirection = 'TB' | 'LR';

interface CanvasState {
  // --- graph ---
  nodes: EntityNode[];
  edges: RelationshipEdge[];

  // --- context ---
  modelId: string | null;
  /**
   * The prompt a library template was loaded from, when the graph on the
   * canvas came from one. Non-null exactly when `modelId` is null and the
   * canvas is holding a reference model — it is what lets the canvas offer a
   * route to a real, synthesized model instead of five disabled buttons.
   */
  sourcePrompt: string | null;
  paradigm: Paradigm | null;
  dialect: string;
  validation: ValidationReport | null;
  validating: boolean;

  // --- selection ---
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  selectedColumn: { entityName: string; columnName: string } | null;

  // --- history (undo/redo) ---
  past: CanvasSnapshot[];
  future: CanvasSnapshot[];

  // --- React Flow event handlers ---
  onNodesChange: (changes: NodeChange<EntityNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<RelationshipEdge>[]) => void;
  onConnect: (connection: Connection) => void;

  // --- mutations ---
  addEntity: (entity: Entity) => void;
  updateEntity: (entityName: string, patch: Partial<EntityNodeData>) => void;
  updateColumn: (
    entityName: string,
    columnName: string,
    patch: Partial<Column>,
  ) => void;
  /** Rename an entity, cascading to node id, edges, and relationship refs. */
  renameEntity: (oldName: string, newName: string) => void;
  /** Rename a column, cascading to its entity's columns and relationship refs. */
  renameColumn: (
    entityName: string,
    oldColumn: string,
    newColumn: string,
  ) => void;
  selectColumn: (entityName: string, columnName: string | null) => void;
  removeEntity: (nodeId: string) => void;
  getGraphPayload: () => { entities: Entity[]; relationships: Relationship[] };
  loadGraph: (
    entities: Entity[],
    relationships: Relationship[],
    paradigm?: Paradigm | null,
    sourcePrompt?: string | null,
  ) => void;
  loadModel: (model: SynthesizeResponse) => void;
  applyLayout: (direction?: LayoutDirection) => void;
  setValidation: (report: ValidationReport | null) => void;
  validateModel: () => Promise<void>;

  // --- selection ---
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;

  // --- history controls ---
  undo: () => void;
  redo: () => void;
  reset: () => void;
}

/** Build a canvas node from a backend entity. */
function entityToNode(entity: Entity): EntityNode {
  return {
    id: entity.entity_name,
    type: 'entity',
    position: { x: entity.canvas_position_x, y: entity.canvas_position_y },
    data: {
      entity_name: entity.entity_name,
      entity_type: entity.entity_type,
      description: entity.description,
      grain: entity.grain,
      tier: entity.tier,
      freshness_sla: entity.freshness_sla,
      columns: entity.columns,
    },
  };
}

/** Build a canvas edge from a backend relationship. */
function relationshipToEdge(rel: Relationship, index: number): RelationshipEdge {
  const source = rel.from.split('.', 1)[0] ?? rel.from;
  const target = rel.to.split('.', 1)[0] ?? rel.to;
  return {
    id: `rel-${index}-${source}-${target}`,
    source,
    target,
    label: rel.cardinality,
    data: {
      cardinality: rel.cardinality as Cardinality,
      from_ref: rel.from,
      to_ref: rel.to,
    },
  };
}

/** Rewrite the entity part of an `entity.column` (or bare `entity`) ref. */
function rewriteRefEntity(ref: string, oldName: string, newName: string): string {
  const dot = ref.indexOf('.');
  if (dot === -1) return ref === oldName ? newName : ref;
  return ref.slice(0, dot) === oldName ? `${newName}${ref.slice(dot)}` : ref;
}

/** Rewrite the column part of an `entity.column` ref for one entity. */
function rewriteRefColumn(
  ref: string,
  entityName: string,
  oldColumn: string,
  newColumn: string,
): string {
  const dot = ref.indexOf('.');
  if (dot === -1) return ref;
  return ref.slice(0, dot) === entityName && ref.slice(dot + 1) === oldColumn
    ? `${entityName}.${newColumn}`
    : ref;
}

/** Run a dagre layout pass, returning repositioned nodes. */
function layoutNodes(
  nodes: EntityNode[],
  edges: RelationshipEdge[],
  direction: LayoutDirection,
): EntityNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: direction, ranksep: 80, nodesep: 60 });

  nodes.forEach((node) => {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target);
  });

  dagre.layout(graph);

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id);
    return {
      ...node,
      position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 },
    };
  });
}

export const useCanvasStore = create<CanvasState>((set, get) => {
  /** Snapshot current graph onto the undo stack before a mutation. */
  const commit = (): void => {
    const { nodes, edges, past } = get();
    const snapshot: CanvasSnapshot = {
      nodes: structuredClone(nodes),
      edges: structuredClone(edges),
    };
    const trimmed = [...past, snapshot].slice(-HISTORY_LIMIT);
    set({ past: trimmed, future: [] });
  };

  return {
    nodes: [],
    edges: [],
    modelId: null,
    sourcePrompt: null,
    paradigm: null,
    dialect: 'snowflake',
    validation: null,
    validating: false,
    selectedNodeId: null,
    selectedEdgeId: null,
    selectedColumn: null,
    past: [],
    future: [],

    onNodesChange: (changes) => {
      set({ nodes: applyNodeChanges(changes, get().nodes) });
    },

    onEdgesChange: (changes) => {
      set({ edges: applyEdgeChanges(changes, get().edges) });
    },

    onConnect: (connection) => {
      commit();
      const edge: RelationshipEdge = {
        id: `rel-${connection.source}-${connection.target}-${get().edges.length}`,
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle: connection.targetHandle ?? undefined,
        label: '1:N',
        data: {
          cardinality: '1:N',
          from_ref: connection.source,
          to_ref: connection.target,
        },
      };
      set({ edges: addEdge(edge, get().edges) });
    },

    addEntity: (entity) => {
      commit();
      set({ nodes: [...get().nodes, entityToNode(entity)] });
    },

    updateEntity: (entityName, patch) => {
      commit();
      set({
        nodes: get().nodes.map((node) =>
          node.id === entityName
            ? { ...node, data: { ...node.data, ...patch } }
            : node,
        ),
      });
    },

    updateColumn: (entityName, columnName, patch) => {
      commit();
      set({
        nodes: get().nodes.map((node) =>
          node.id === entityName
            ? {
                ...node,
                data: {
                  ...node.data,
                  columns: node.data.columns.map((c) =>
                    c.name === columnName ? { ...c, ...patch } : c,
                  ),
                },
              }
            : node,
        ),
      });
    },

    renameEntity: (oldName, newName) => {
      const trimmed = newName.trim();
      if (!trimmed || trimmed === oldName) return;
      // Reject a collision with another existing entity.
      if (get().nodes.some((n) => n.id === trimmed)) return;
      commit();
      const sel = get().selectedColumn;
      set({
        nodes: get().nodes.map((node) =>
          node.id === oldName
            ? {
                ...node,
                id: trimmed,
                data: { ...node.data, entity_name: trimmed },
              }
            : node,
        ),
        edges: get().edges.map((edge) => ({
          ...edge,
          source: edge.source === oldName ? trimmed : edge.source,
          target: edge.target === oldName ? trimmed : edge.target,
          data: edge.data
            ? {
                ...edge.data,
                from_ref: rewriteRefEntity(edge.data.from_ref, oldName, trimmed),
                to_ref: rewriteRefEntity(edge.data.to_ref, oldName, trimmed),
              }
            : edge.data,
        })),
        selectedNodeId:
          get().selectedNodeId === oldName ? trimmed : get().selectedNodeId,
        selectedColumn:
          sel?.entityName === oldName
            ? { entityName: trimmed, columnName: sel.columnName }
            : sel,
      });
    },

    renameColumn: (entityName, oldColumn, newColumn) => {
      const trimmed = newColumn.trim();
      if (!trimmed || trimmed === oldColumn) return;
      const node = get().nodes.find((n) => n.id === entityName);
      if (!node) return;
      // Reject a collision with another column on the same entity.
      if (node.data.columns.some((c) => c.name === trimmed)) return;
      commit();
      const sel = get().selectedColumn;
      set({
        nodes: get().nodes.map((n) =>
          n.id === entityName
            ? {
                ...n,
                data: {
                  ...n.data,
                  columns: n.data.columns.map((c) =>
                    c.name === oldColumn ? { ...c, name: trimmed } : c,
                  ),
                },
              }
            : n,
        ),
        edges: get().edges.map((edge) =>
          edge.data
            ? {
                ...edge,
                data: {
                  ...edge.data,
                  from_ref: rewriteRefColumn(
                    edge.data.from_ref,
                    entityName,
                    oldColumn,
                    trimmed,
                  ),
                  to_ref: rewriteRefColumn(
                    edge.data.to_ref,
                    entityName,
                    oldColumn,
                    trimmed,
                  ),
                },
              }
            : edge,
        ),
        selectedColumn:
          sel?.entityName === entityName && sel.columnName === oldColumn
            ? { entityName, columnName: trimmed }
            : sel,
      });
    },

    selectColumn: (entityName, columnName) =>
      set({
        selectedColumn: columnName ? { entityName, columnName } : null,
      }),

    removeEntity: (nodeId) => {
      commit();
      set({
        nodes: get().nodes.filter((node) => node.id !== nodeId),
        edges: get().edges.filter(
          (edge) => edge.source !== nodeId && edge.target !== nodeId,
        ),
        selectedNodeId:
          get().selectedNodeId === nodeId ? null : get().selectedNodeId,
      });
    },

    getGraphPayload: () => {
      const { nodes, edges } = get();
      const entities: Entity[] = nodes.map((node) => ({
        entity_name: node.data.entity_name,
        entity_type: node.data.entity_type,
        description: node.data.description ?? null,
        grain: node.data.grain ?? null,
        tier: node.data.tier ?? null,
        freshness_sla: node.data.freshness_sla ?? null,
        canvas_position_x: node.position.x,
        canvas_position_y: node.position.y,
        columns: node.data.columns,
      }));
      const relationships: Relationship[] = edges.map((edge) => ({
        from: edge.data?.from_ref ?? edge.source,
        to: edge.data?.to_ref ?? edge.target,
        cardinality: edge.data?.cardinality ?? '1:N',
      }));
      return { entities, relationships };
    },

    loadGraph: (entities, relationships, paradigm = null, sourcePrompt = null) => {
      commit();
      set({
        modelId: null,
        sourcePrompt,
        paradigm,
        nodes: entities.map(entityToNode),
        edges: relationships.map(relationshipToEdge),
        validation: null,
        selectedNodeId: null,
        selectedEdgeId: null,
      });
    },

    loadModel: (model) => {
      commit();
      set({
        modelId: model.model_id,
        // A real model supersedes whatever template seeded the canvas.
        sourcePrompt: null,
        paradigm: model.paradigm,
        nodes: model.entities.map(entityToNode),
        edges: model.relationships.map(relationshipToEdge),
        validation: model.validation ?? null,
        selectedNodeId: null,
        selectedEdgeId: null,
      });
    },

    applyLayout: (direction = 'TB') => {
      commit();
      set({ nodes: layoutNodes(get().nodes, get().edges, direction) });
    },

    setValidation: (report) => set({ validation: report }),

    validateModel: async () => {
      const { modelId } = get();
      if (!modelId) return;
      set({ validating: true });
      try {
        const report = await apiValidateModel(modelId);
        set({ validation: report });
      } finally {
        set({ validating: false });
      }
    },

    selectNode: (nodeId) =>
      set({ selectedNodeId: nodeId, selectedEdgeId: null }),

    selectEdge: (edgeId) =>
      set({ selectedEdgeId: edgeId, selectedNodeId: null }),

    undo: () => {
      const { past, future, nodes, edges } = get();
      const previous = past[past.length - 1];
      if (!previous) return;
      const current: CanvasSnapshot = {
        nodes: structuredClone(nodes),
        edges: structuredClone(edges),
      };
      set({
        nodes: previous.nodes,
        edges: previous.edges,
        past: past.slice(0, -1),
        future: [current, ...future].slice(0, HISTORY_LIMIT),
      });
    },

    redo: () => {
      const { past, future, nodes, edges } = get();
      const next = future[0];
      if (!next) return;
      const current: CanvasSnapshot = {
        nodes: structuredClone(nodes),
        edges: structuredClone(edges),
      };
      set({
        nodes: next.nodes,
        edges: next.edges,
        past: [...past, current].slice(-HISTORY_LIMIT),
        future: future.slice(1),
      });
    },

    reset: () =>
      set({
        nodes: [],
        edges: [],
        modelId: null,
        sourcePrompt: null,
        paradigm: null,
        validation: null,
        validating: false,
        selectedNodeId: null,
        selectedEdgeId: null,
        selectedColumn: null,
        past: [],
        future: [],
      }),
  };
});

export type { CanvasState, LayoutDirection };
export { entityToNode, relationshipToEdge };
