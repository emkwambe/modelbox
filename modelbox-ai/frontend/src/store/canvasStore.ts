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
  paradigm: Paradigm | null;
  dialect: string;
  validation: ValidationReport | null;
  validating: boolean;

  // --- selection ---
  selectedNodeId: string | null;
  selectedEdgeId: string | null;

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
  removeEntity: (nodeId: string) => void;
  getGraphPayload: () => { entities: Entity[]; relationships: Relationship[] };
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
    paradigm: null,
    dialect: 'snowflake',
    validation: null,
    validating: false,
    selectedNodeId: null,
    selectedEdgeId: null,
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

    loadModel: (model) => {
      commit();
      set({
        modelId: model.model_id,
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
        paradigm: null,
        validation: null,
        validating: false,
        selectedNodeId: null,
        selectedEdgeId: null,
        past: [],
        future: [],
      }),
  };
});

export type { CanvasState, LayoutDirection };
export { entityToNode, relationshipToEdge };
