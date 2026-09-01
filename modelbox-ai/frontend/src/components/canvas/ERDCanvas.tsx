'use client';

/**
 * ERDCanvas — the interactive entity-relationship canvas (FR-2).
 *
 * Wires React Flow to the Zustand canvas store: custom entity-node rendering,
 * relationship edges, drag/connect editing, minimap/controls, and the overlay
 * control panel for layout + undo/redo.
 */

import { useCallback, useMemo } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import ControlPanel from '@/components/canvas/ControlPanel';
import EntityNode from '@/components/canvas/EntityNode';
import ValidationPanel from '@/components/canvas/ValidationPanel';
import { useCanvasStore } from '@/store/canvasStore';
import type { EntityNode as EntityNodeType } from '@/types/schema';
import { semantic } from '@/styles/tokens';

const nodeTypes: NodeTypes = { entity: EntityNode };
const CYCLE_EDGE_STYLE = { stroke: semantic.breaking.onLight, strokeWidth: 2 };

/** Inner canvas — must live within a ReactFlowProvider. */
function ERDCanvasInner() {
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const validation = useCanvasStore((s) => s.validation);
  const onNodesChange = useCanvasStore((s) => s.onNodesChange);
  const onEdgesChange = useCanvasStore((s) => s.onEdgesChange);
  const onConnect = useCanvasStore((s) => s.onConnect);
  const selectNode = useCanvasStore((s) => s.selectNode);
  const selectColumn = useCanvasStore((s) => s.selectColumn);

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: EntityNodeType) => {
      selectNode(node.id);
      selectColumn('', null); // node-level selection closes the column editor
    },
    [selectNode, selectColumn],
  );

  // Highlight edges whose endpoints both sit inside a CYCLIC_FK cycle.
  const styledEdges = useMemo(() => {
    const cycleEntities = new Set(
      (validation?.issues ?? [])
        .filter((i) => i.code === 'CYCLIC_FK')
        .flatMap((i) => i.entities),
    );
    if (cycleEntities.size === 0) return edges;
    return edges.map((edge) =>
      cycleEntities.has(edge.source) && cycleEntities.has(edge.target)
        ? { ...edge, animated: true, style: CYCLE_EDGE_STYLE }
        : edge,
    );
  }, [edges, validation]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={styledEdges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onNodeClick={onNodeClick}
      onPaneClick={() => {
        selectNode(null);
        selectColumn('', null);
      }}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={16} />
      <Controls />
      <MiniMap pannable zoomable />
      <ControlPanel />
      <ValidationPanel />
    </ReactFlow>
  );
}

/** Public canvas component — provides the React Flow context. */
export default function ERDCanvas() {
  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlowProvider>
        <ERDCanvasInner />
      </ReactFlowProvider>
    </div>
  );
}
