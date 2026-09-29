/**
 * F4, the half that can be a gate: selecting one column re-renders two nodes.
 *
 * `vitest.config.mts` already states the division this file lives on — jsdom
 * cannot measure layout, so these assertions prove the **re-render** defect is
 * fixed and say nothing about whether the canvas feels usable. The smoothness
 * half is a recorded profiling run on named hardware and must not be read off
 * this file.
 *
 * **Why a count rather than a duration.** A render count is an integer. It is
 * identical on a developer laptop and a loaded CI runner, it cannot flake, and
 * it fails for exactly one reason. A frame rate on a shared runner is none of
 * those things, and a threshold loose enough not to flake is loose enough to
 * miss the defect. The register asks for a profiling run; this is the part of
 * that run which can be a required job.
 *
 * **The defect being measured.** `EntityNode` subscribed to the store twice in
 * ways that cannot be memoised:
 *
 *   - `s.validation?.issues.filter(...) ?? []` constructs a **new array on
 *     every store notification**. zustand v4 compares with `Object.is`, so the
 *     subscription fired on every write in the application — a drag frame, a
 *     rename, an undo push — and the `?? []` meant it fired even when there was
 *     no validation report at all.
 *   - `s.selectedColumn` is an object, so selecting a column in *one* entity
 *     changed the identity every node was watching.
 *
 * Either alone re-renders all N nodes. `React.memo` cannot help with either,
 * because the component genuinely did re-subscribe — which is why the fix is
 * the selectors, and the memo is only what stops the cascade afterwards.
 *
 * **Mutation results, 2026-09-01.** Both arms were run against the fixed
 * component, one at a time, and they kill *different* assertions — which is the
 * useful part, because it shows the two selectors are independent defects
 * rather than one defect described twice.
 *
 * | Reverted | Killed by |
 * | :-- | :-- |
 * | the `issues` selector (`?? []` inside the selector) | **both** the selection test (500 ≰ 2) and the unrelated-write test (500 ≠ 0) |
 * | the `selectedColumn` object subscription | the selection test only (500 ≰ 2); the unrelated-write test still passes |
 *
 * So the unrelated-write assertion is the one that pins the `issues` selector
 * specifically, and nothing else in this file does. Delete it and reverting
 * that selector would still be caught — but only by an assertion that a second
 * mutation also trips, which is how a test stops being able to say *which*
 * thing broke.
 */

import { ReactFlowProvider } from '@xyflow/react';
import { act, render } from '@testing-library/react';
import { Profiler, type ComponentProps, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useCanvasStore } from '@/store/canvasStore';
import { makeLargeGraph } from '@/test/fixtures/largeGraph';

import EntityNode from './EntityNode';

/**
 * F4's own number. Kept at 500 rather than a convenient 20, because a
 * re-render storm is invisible at small N and this is the criterion's figure.
 * Columns are held narrow — the DOM size is not what is under test here, and a
 * 40-column fixture would spend the whole budget building rows in jsdom.
 */
const ENTITIES = 500;

const graph = makeLargeGraph({
  entities: ENTITIES,
  minColumns: 3,
  maxColumns: 5,
});

const propsFor = (node: (typeof graph.nodes)[number]) =>
  ({
    id: node.id,
    type: 'entity',
    data: node.data,
    selected: false,
    dragging: false,
    isConnectable: false,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  }) as unknown as ComponentProps<typeof EntityNode>;

/** Renders per node id, counted by React itself rather than by a wrapper. */
const renders = new Map<string, number>();

function countRendersOf(id: string, node: ReactNode): ReactNode {
  return (
    <Profiler
      key={id}
      id={id}
      onRender={() => renders.set(id, (renders.get(id) ?? 0) + 1)}
    >
      {node}
    </Profiler>
  );
}

function Canvas() {
  return (
    <ReactFlowProvider>
      {graph.nodes.map((node) =>
        countRendersOf(node.id, <EntityNode {...propsFor(node)} />),
      )}
    </ReactFlowProvider>
  );
}

const totalRenders = (): number =>
  [...renders.values()].reduce((a, b) => a + b, 0);

describe('EntityNode re-render containment at 500 entities', () => {
  beforeEach(() => {
    renders.clear();
    useCanvasStore.setState({
      nodes: graph.nodes,
      edges: graph.edges,
      validation: null,
      selectedColumn: null,
      selectedNodeId: null,
    });
  });

  it('mounts every entity, so the measurement is not of an empty tree', () => {
    // Precondition. A fixture that silently produced nothing would make every
    // assertion below pass by rendering no components at all — the failure
    // shape this repository has shipped four times.
    render(<Canvas />);
    expect(renders.size).toBe(ENTITIES);
    expect(totalRenders()).toBe(ENTITIES);
  });

  it('re-renders two nodes when one column is selected, not five hundred', () => {
    render(<Canvas />);
    renders.clear();

    act(() => {
      useCanvasStore.getState().selectColumn('dim_attribute_1', 'attribute_1');
    });

    // Two: the entity gaining the selection, and — on a later selection — the
    // one losing it. Never the other 498, which have no stake in it.
    expect(totalRenders()).toBeLessThanOrEqual(2);
  });

  it('re-renders nothing when a store write touches no node it owns', () => {
    render(<Canvas />);
    renders.clear();

    // The original defect in its purest form: a write to an unrelated slice.
    // Under the old selector every node re-rendered here, because the issues
    // array was rebuilt and compared unequal on any notification whatsoever.
    act(() => {
      useCanvasStore.setState({ dialect: 'snowflake' });
    });

    expect(totalRenders()).toBe(0);
  });

  it('still re-renders for a validation report, so narrow is not deaf', () => {
    render(<Canvas />);
    renders.clear();

    act(() => {
      useCanvasStore.setState({
        validation: {
          is_valid: false,
          issues: [
            {
              severity: 'error',
              code: 'MISSING_PK',
              message: 'no primary key',
              entities: ['dim_attribute_3'],
              entity_name: 'dim_attribute_3',
              column_name: null,
            },
          ],
        },
      });
    });

    // The discriminating half. A component that simply stopped reading
    // validation would satisfy every assertion above and fail this one — so
    // "narrow" cannot be "deaf" wearing a better name.
    expect(renders.get('dim_attribute_3')).toBe(1);

    // And an honest statement of what the fix does *not* do: a new report is a
    // new object, so every node re-evaluates whether it is named. That is
    // correct and it is rare — validation runs on demand, not per frame. The
    // storm this file exists to kill was on writes that name no entity at all.
    // Narrowing this further means indexing issues per entity in the store,
    // which is a larger change than the defect warranted.
    expect(totalRenders()).toBe(ENTITIES);
  });
});
