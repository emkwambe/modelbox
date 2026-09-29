/**
 * F4, the geometry half: auto-layout must not stack nodes on top of each other.
 *
 * This is not a performance test even though it lives under F4. `NODE_HEIGHT`
 * is a **fixed 160** handed to dagre for every node regardless of how many
 * columns that node has, and a 40-column entity renders roughly 600px tall. So
 * dagre packs ranks 160px apart and the tall nodes overlap the ones below them.
 * A user meets that as "the canvas is a mess at scale" and files it as
 * performance, which is why it is being pinned as geometry before anything is
 * optimised: it is arithmetic, it is deterministic, and it has nothing to do
 * with how fast anything runs.
 *
 * jsdom cannot measure a rendered box, and this test does not ask it to. The
 * height a node *will* occupy is a function of its column count and the row
 * metrics the component uses — that function is the thing under test, and it is
 * the same function the layout has to be told about.
 *
 * **Timing lives here too, deliberately narrowly.** `dagre.layout()` is pure
 * CPU with no paint and no browser, which makes it the one duration in this
 * sprint stable enough to assert. The ceiling is loose on purpose: it exists to
 * catch a change of algorithmic complexity, not to police a 200ms regression on
 * a loaded runner.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import { estimatedNodeHeight, NODE_WIDTH } from '@/store/canvasStore';
import { makeLargeGraph } from '@/test/fixtures/largeGraph';

const ENTITIES = 500;

const graph = makeLargeGraph({ entities: ENTITIES, minColumns: 6, maxColumns: 40 });

interface Box {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

const boxesFrom = (): Box[] =>
  useCanvasStore.getState().nodes.map((node) => ({
    id: node.id,
    x: node.position.x,
    y: node.position.y,
    w: NODE_WIDTH,
    h: estimatedNodeHeight(node.data.columns.length),
  }));

const overlaps = (a: Box, b: Box): boolean =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

function overlappingPairs(boxes: Box[]): [string, string][] {
  // Sweep by x-band rather than comparing all 125,000 pairs. Sorting by y and
  // breaking when the next box starts below the current one's bottom keeps this
  // near-linear on a laid-out graph, where nodes are already rank-ordered.
  const sorted = [...boxes].sort((p, q) => p.y - q.y || p.x - q.x);
  const found: [string, string][] = [];
  for (let i = 0; i < sorted.length; i += 1) {
    const a = sorted[i]!;
    for (let j = i + 1; j < sorted.length; j += 1) {
      const b = sorted[j]!;
      if (b.y >= a.y + a.h) break;
      if (overlaps(a, b)) found.push([a.id, b.id]);
    }
  }
  return found;
}

describe('auto-layout at 500 entities', () => {
  beforeEach(() => {
    useCanvasStore.setState({
      nodes: graph.nodes.map((n) => ({ ...n, position: { x: 0, y: 0 } })),
      edges: graph.edges,
      past: [],
      future: [],
    });
  });

  it('has a fixture with tall and short nodes, or it proves nothing', () => {
    // Precondition, and the discriminating one. A fixture where every entity
    // has the same column count cannot distinguish a layout that measures
    // height from one that assumes a constant — which is exactly the defect.
    const heights = new Set(
      graph.nodes.map((n) => estimatedNodeHeight(n.data.columns.length)),
    );
    expect(heights.size).toBeGreaterThan(10);
    expect(Math.max(...heights)).toBeGreaterThan(2 * Math.min(...heights));
  });

  it('places every node somewhere, so the sweep is not over an empty set', () => {
    useCanvasStore.getState().applyLayout('TB');
    const boxes = boxesFrom();
    expect(boxes).toHaveLength(ENTITIES);
    expect(boxes.every((b) => Number.isFinite(b.x) && Number.isFinite(b.y))).toBe(
      true,
    );
  });

  it('leaves no two nodes overlapping', () => {
    useCanvasStore.getState().applyLayout('TB');
    const collisions = overlappingPairs(boxesFrom());
    expect(collisions.slice(0, 5)).toEqual([]);
    expect(collisions).toHaveLength(0);
  });

  it('lays out within a ceiling that would catch a complexity change', () => {
    const started = performance.now();
    useCanvasStore.getState().applyLayout('TB');
    const elapsed = performance.now() - started;

    // Recorded rather than tuned: see sprint-6-progress.md for the measured
    // figure on the machine this was written on. The ceiling is deliberately
    // far above it — this fails when dagre starts behaving super-linearly at
    // this size, not when a runner is busy.
    expect(elapsed).toBeLessThan(10_000);
  });
});
