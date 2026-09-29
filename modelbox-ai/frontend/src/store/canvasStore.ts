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
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react';
import dagre from 'dagre';

import { validateModel as apiValidateModel } from '@/lib/api';
import {
  entityPayload,
  isResolved,
  relationshipPayload,
  relationshipToEdgeData,
  renameInLists,
} from '@/store/graphPayload';
import { semantic } from '@/styles/tokens';

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
  RelationshipEdgeData,
  SynthesizeResponse,
  ValidationReport,
} from '@/types/schema';

/**
 * A relationship being drawn or edited: the two entities, and the edge it
 * replaces when an existing one is being given its columns.
 */
export interface PendingConnection {
  source: string;
  target: string;
  edgeId: string | null;
}

const HISTORY_LIMIT = 50;
export const NODE_WIDTH = 240;

/**
 * What a node actually occupies, rather than a constant.
 *
 * This was `NODE_HEIGHT = 160` for every node, handed to dagre regardless of
 * how many columns the entity had. A 40-column entity renders around 750px
 * tall, so dagre spaced ranks for a node less than a quarter of that size and
 * the tall ones overlapped everything beneath them. It reads as a rendering or
 * performance problem and it is neither: it is one number being wrong.
 *
 * The figures come from `EntityNode`'s own styles — a 12px row at
 * `padding: '2px 10px'`, a header at `'7px 11px'` and 700 weight, and the two
 * optional banners (`grain`, `tier`) at the row padding. They are an estimate
 * and are meant to be: jsdom cannot measure a box, and the alternative —
 * measuring in the browser and feeding it back — would make layout depend on
 * having rendered first. An estimate that tracks column count is the difference
 * between "wrong by a factor of four on the widest nodes" and "wrong by a few
 * pixels", and only the first one stacks nodes on top of each other.
 *
 * Validation banners are deliberately **not** counted. They come and go with a
 * lint report, and a layout that moved every time the linter ran would be worse
 * than one that is a row short on a node with a missing primary key.
 */
const HEADER_HEIGHT = 30;
const ROW_HEIGHT = 18;
const BANNER_HEIGHT = 18;
const NODE_CHROME = 4;

export function estimatedNodeHeight(columnCount: number, banners = 0): number {
  return (
    HEADER_HEIGHT +
    banners * BANNER_HEIGHT +
    columnCount * ROW_HEIGHT +
    NODE_CHROME
  );
}

type LayoutDirection = 'TB' | 'LR';

interface CanvasState {
  // --- graph ---
  nodes: EntityNode[];
  edges: RelationshipEdge[];

  // --- context ---
  modelId: string | null;
  /** The loaded model's workspace, whose classification scale its columns use. */
  workspaceId: string | null;
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

  /** Whether the graph has changed since it was loaded or last saved. */
  dirty: boolean;
  /** A relationship waiting for its columns to be chosen. */
  pendingConnection: PendingConnection | null;

  // --- React Flow event handlers ---
  onNodesChange: (changes: NodeChange<EntityNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<RelationshipEdge>[]) => void;
  /** Connecting two entities asks for columns; nothing is added until they are chosen. */
  onConnect: (connection: Connection) => void;
  /** Open the column picker for an existing edge. */
  editEdgeColumns: (edgeId: string) => void;
  /** Add (or replace) the pending relationship with its chosen columns. */
  connectColumns: (fromColumns: string[], toColumns: string[], cardinality?: Cardinality) => void;
  cancelConnection: () => void;
  /** Record that the current graph is what the server holds. */
  markSaved: () => void;

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
  /**
   * Point a column's one-column foreign key at `entity.column`, or remove it
   * (null): the relationship is replaced, since the relationship is the key.
   */
  setColumnReference: (entityName: string, columnName: string, target: string | null) => void;
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
      // Dropped here until Sprint 8 Step 3, so every canvas save cleared it.
      agg_time_column: entity.agg_time_column ?? null,
      // Dictionary fields (Step 4b): carried, or every save would clear them.
      business_name: entity.business_name ?? null,
      business_owner: entity.business_owner ?? null,
      it_steward: entity.it_steward ?? null,
      authoritative_source: entity.authoritative_source ?? null,
      columns: entity.columns,
      primary_key: entity.primary_key ?? entity.columns.filter((c) => c.is_primary_key).map((c) => c.name),
      unique_constraints: entity.unique_constraints ?? [],
      check_constraints: entity.check_constraints ?? [],
    },
  };
}

/**
 * An unresolved relationship — saved before its columns could be chosen — is
 * drawn dashed in the caution tone, so it is visibly not a foreign key yet.
 */
const UNRESOLVED_EDGE_STYLE = { stroke: semantic.preview.onLight, strokeDasharray: '6 4' };

/** Build a canvas edge from a backend relationship. */
function relationshipToEdge(rel: Relationship, index: number): RelationshipEdge {
  const data = relationshipToEdgeData(rel);
  return edgeFor(data, `rel-${index}-${data.from_ref}-${data.to_ref}`);
}

function edgeFor(data: RelationshipEdgeData, id: string): RelationshipEdge {
  const resolved = isResolved(data);
  return {
    id,
    source: data.from_ref,
    target: data.to_ref,
    label: resolved ? data.cardinality : `${data.cardinality} · columns not chosen`,
    data,
    ...(resolved ? {} : { style: UNRESOLVED_EDGE_STYLE }),
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

  // Height per node, not one height for all of them. `heights` is kept so the
  // offset below uses the *same* number dagre was given — reading it back from
  // the graph would work too, but a second source is a second thing to get
  // wrong, and this pair was already wrong once.
  const heights = new Map<string, number>();
  nodes.forEach((node) => {
    const banners = (node.data.grain ? 1 : 0) + (node.data.tier ? 1 : 0);
    const height = estimatedNodeHeight(node.data.columns.length, banners);
    heights.set(node.id, height);
    graph.setNode(node.id, { width: NODE_WIDTH, height });
  });
  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target);
  });

  dagre.layout(graph);

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id);
    // dagre reports a centre; React Flow positions by top-left corner.
    const height = heights.get(node.id) ?? estimatedNodeHeight(0);
    return {
      ...node,
      position: { x: x - NODE_WIDTH / 2, y: y - height / 2 },
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
    // Every mutation commits first, so this is also where the graph becomes
    // unsaved. A load clears it again after its own commit.
    set({ past: trimmed, future: [], dirty: true });
  };

  return {
    nodes: [],
    edges: [],
    modelId: null,
    workspaceId: null,
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
    dirty: false,
    pendingConnection: null,

    onNodesChange: (changes) => {
      // A moved or removed node changes what is saved; a selection does not.
      const edits = changes.some((c) => c.type === 'position' || c.type === 'remove');
      set({ nodes: applyNodeChanges(changes, get().nodes), ...(edits ? { dirty: true } : {}) });
    },

    onEdgesChange: (changes) => {
      const edits = changes.some((c) => c.type === 'remove');
      set({ edges: applyEdgeChanges(changes, get().edges), ...(edits ? { dirty: true } : {}) });
    },

    onConnect: (connection) => {
      set({ pendingConnection: { source: connection.source, target: connection.target, edgeId: null } });
    },

    editEdgeColumns: (edgeId) => {
      const edge = get().edges.find((e) => e.id === edgeId);
      if (!edge) return;
      set({ pendingConnection: { source: edge.source, target: edge.target, edgeId } });
    },

    connectColumns: (fromColumns, toColumns, cardinality) => {
      const pending = get().pendingConnection;
      if (!pending || fromColumns.length === 0 || fromColumns.length !== toColumns.length) return;
      commit();
      const existing = pending.edgeId ? get().edges.find((e) => e.id === pending.edgeId) : undefined;
      const data: RelationshipEdgeData = {
        cardinality: cardinality ?? existing?.data?.cardinality ?? 'N:1',
        from_ref: pending.source,
        to_ref: pending.target,
        from_columns: fromColumns,
        to_columns: toColumns,
        name: existing?.data?.name ?? null,
      };
      if (existing) {
        set({
          edges: get().edges.map((e) => (e.id === existing.id ? edgeFor(data, e.id) : e)),
          pendingConnection: null,
        });
        return;
      }
      // Appended, not addEdge: React Flow's addEdge drops an edge between two
      // nodes that already have one, and two foreign keys between the same
      // tables (a role-playing dimension) are two relationships.
      const id = `rel-${pending.source}-${pending.target}-${get().edges.length}`;
      set({ edges: [...get().edges, edgeFor(data, id)], pendingConnection: null });
    },

    cancelConnection: () => set({ pendingConnection: null }),

    markSaved: () => set({ dirty: false }),

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
                from_ref: edge.data.from_ref === oldName ? trimmed : edge.data.from_ref,
                to_ref: edge.data.to_ref === oldName ? trimmed : edge.data.to_ref,
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
                  ...renameInLists(n.data, oldColumn, trimmed),
                  columns: n.data.columns.map((c) =>
                    c.name === oldColumn ? { ...c, name: trimmed } : c,
                  ),
                },
              }
            : n,
        ),
        edges: get().edges.map((edge) => {
          if (!edge.data) return edge;
          const swap = (entity: string, columns: string[]) =>
            entity === entityName ? columns.map((c) => (c === oldColumn ? trimmed : c)) : columns;
          return {
            ...edge,
            data: {
              ...edge.data,
              from_columns: swap(edge.data.from_ref, edge.data.from_columns),
              to_columns: swap(edge.data.to_ref, edge.data.to_columns),
            },
          };
        }),
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

    setColumnReference: (entityName, columnName, target) => {
      commit();
      const kept = get().edges.filter(
        (e) =>
          !(
            e.data?.from_ref === entityName &&
            e.data.from_columns.length === 1 &&
            e.data.from_columns[0] === columnName
          ),
      );
      if (target === null) {
        set({ edges: kept });
        return;
      }
      const dot = target.indexOf('.');
      const data: RelationshipEdgeData = {
        cardinality: 'N:1',
        from_ref: entityName,
        to_ref: target.slice(0, dot),
        from_columns: [columnName],
        to_columns: [target.slice(dot + 1)],
        name: null,
      };
      set({ edges: [...kept, edgeFor(data, `rel-${entityName}-${data.to_ref}-${kept.length}`)] });
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
      const entities: Entity[] = nodes.map((node) => entityPayload(node.data, node.position));
      const relationships: Relationship[] = edges.map((edge) =>
        relationshipPayload(
          edge.data ?? {
            cardinality: '1:N',
            from_ref: edge.source,
            to_ref: edge.target,
            from_columns: [],
            to_columns: [],
          },
        ),
      );
      return { entities, relationships };
    },

    loadGraph: (entities, relationships, paradigm = null, sourcePrompt = null) => {
      commit();
      set({
        modelId: null,
        workspaceId: null,
        sourcePrompt,
        paradigm,
        nodes: entities.map(entityToNode),
        edges: relationships.map(relationshipToEdge),
        validation: null,
        selectedNodeId: null,
        selectedEdgeId: null,
        pendingConnection: null,
        dirty: false,
      });
    },

    loadModel: (model) => {
      commit();
      set({
        modelId: model.model_id,
        workspaceId: model.workspace_id ?? null,
        // A real model supersedes whatever template seeded the canvas.
        sourcePrompt: null,
        paradigm: model.paradigm,
        nodes: model.entities.map(entityToNode),
        edges: model.relationships.map(relationshipToEdge),
        validation: model.validation ?? null,
        selectedNodeId: null,
        selectedEdgeId: null,
        pendingConnection: null,
        dirty: false,
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
        dirty: true,
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
        dirty: true,
      });
    },

    reset: () =>
      set({
        nodes: [],
        edges: [],
        modelId: null,
        workspaceId: null,
        sourcePrompt: null,
        paradigm: null,
        validation: null,
        validating: false,
        selectedNodeId: null,
        selectedEdgeId: null,
        selectedColumn: null,
        past: [],
        future: [],
        dirty: false,
        pendingConnection: null,
      }),
  };
});

export type { CanvasState, LayoutDirection };
export { entityToNode, relationshipToEdge };
