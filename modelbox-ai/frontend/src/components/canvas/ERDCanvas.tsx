'use client';

/**
 * ERDCanvas — the interactive entity-relationship canvas (FR-2).
 *
 * Wires React Flow to the Zustand canvas store: custom entity-node rendering,
 * relationship edges, drag/connect editing, minimap/controls, and the overlay
 * control panel for layout + undo/redo.
 */

import { useCallback } from 'react';
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
import { useCanvasStore } from '@/store/canvasStore';
import type { EntityNode as EntityNodeType } from '@/types/schema';

const nodeTypes: NodeTypes = { entity: EntityNode };

/** Inner canvas — must live within a ReactFlowProvider. */
function ERDCanvasInner() {
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const onNodesChange = useCanvasStore((s) => s.onNodesChange);
  const onEdgesChange = useCanvasStore((s) => s.onEdgesChange);
  const onConnect = useCanvasStore((s) => s.onConnect);
  const selectNode = useCanvasStore((s) => s.selectNode);

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: EntityNodeType) => selectNode(node.id),
    [selectNode],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onNodeClick={onNodeClick}
      onPaneClick={() => selectNode(null)}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={16} />
      <Controls />
      <MiniMap pannable zoomable />
      <ControlPanel />
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
