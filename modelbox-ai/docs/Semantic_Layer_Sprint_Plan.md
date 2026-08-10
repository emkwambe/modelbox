# Semantic Layer — Sprint Plan

Reconciles the semantic-layer review with the shipped appliance. Ordered by
dependency; each sprint is independently shippable, CI-gated, and live-verified,
matching the established rhythm (implement → test → tsc/pytest → commit → CI →
deploy → smoke-test).

**Key code facts that shaped this plan:**
- `ColumnSchema` already has `is_metric` + `aggregation`; `EntitySchema` has
  `grain`; `SuggestedMetric` has `formula`. The MetricFlow/Cube/LookML exporters
  **already consume** these — so "declaring measures" is a UI/persistence gap,
  not a backend one.
- The diff lives in `DiffEngine.diff` (`services/diff_engine.py`), not
  `GraphEngine`.
- The linter stores each relationship's cardinality but never validates it — no
  fan-out check exists.

---

## Sprint 1 — Fan-out / cardinality-risk lint  *(backend; foundational)*

**Goal:** catch the #1 semantic anti-pattern at design time.
**Scope:** add a `FAN_OUT_RISK` warning to `GraphEngine.validate` — flag
many-to-many (`N:M`) relationships and joins between two `FACT` entities (the
duplicate-row trap that inflates `SUM`s). Warning-only; never invalidates.
**Deliverables:** rule + unit tests (positive/negative), surfaces on node cards
via the existing badge/overlay.
**Verify:** unit tests; live re-validate a model with an `N:M` edge → amber flag.
**Effort:** Low. **Depends on:** nothing.
**Bonus:** becomes the auto-grader primitive for Sprint 4.

## Sprint 2 — Visual Semantic Metric Builder  *(frontend + light backend)*

**Goal:** let users declare measures/dimensions explicitly instead of relying on
export-time heuristics.
**Scope:**
- Canvas node-card column editor: toggle a column as **MEASURE** with a default
  aggregation (`SUM`/`COUNT`/`COUNT_DISTINCT`/`AVG`/`MIN`/`MAX`) or mark it a
  **DIMENSION**. Backed by the existing `is_metric` + `aggregation` fields;
  persisted through the existing `PUT /model/{id}/graph`.
- Small export touch-up: emit `time_granularities` on time dimensions and a
  simple metric per declared measure so MetricFlow/Cube/LookML output is
  immediately usable. (No fabricated business filters — those need context.)
**Deliverables:** UI editor + store wiring; exporter enhancement + tests.
**Verify:** declare a measure on the canvas → export MetricFlow → measure/metric
appears; tsc + build; live smoke test.
**Effort:** Med. **Depends on:** nothing (but unblocks Sprints 3 & 4).

## Sprint 3 — Semantic diff & breaking-change impact  *(backend)*

**Goal:** warn when a physical change breaks an *in-model* semantic definition.
**Scope:** extend `DiffEngine.diff` to emit `SEMANTIC_BREAK` notices when a
dropped/renamed/type-changed column is (a) a declared measure (`is_metric`) or
(b) referenced by a `SuggestedMetric.formula`. **In-model only** — no external
dashboard/consumer tracking (explicitly out of scope to avoid a registry pivot).
**Deliverables:** diff-engine extension + tests; surfaced in the Diff panel
alongside breaking changes.
**Verify:** diff two models where V2 drops a measure column → `SEMANTIC_BREAK`
listed; unit + endpoint tests; live check.
**Effort:** Med. **Depends on:** Sprint 2 (needs declared measures).

## Sprint 4 — Semantic "Spot the Flaw" Trainer  *(course/Trainer; part of Step 3)*

**Goal:** teach semantic-layer quality via graded challenges.
**Scope:** new Trainer scenarios — fan-out traps (graded by Sprint 1's lint),
grain mismatches, missing aggregation/filter on measures (graded via declared
semantics from Sprint 2). Requires a semantic-flaw content type + graders.
**Deliverables:** assignment templates + invariant graders; ties into the
Semantic Layer course module (Module 2).
**Verify:** load a flawed semantic assignment → grader detects the seeded flaws.
**Effort:** Med-High. **Depends on:** Sprints 1 & 2. **Schedule with Step 3.**

---

## Backlog (optional, not scheduled)

- **GraphQL schema export** — the one missing format from the doc's Feature 4; a
  thin new exporter. Do only if a consumer asks.

## Explicitly out of scope (creep guard)

- Semantic-layer **registry** with dashboard/consumer impact tracking,
  metric owners/tiers/lifecycle, and runtime RLS/CLS access control. ModelBox
  models & exports; it is not a metric store or a runtime security engine.

## Sequence

**Sprint 1 (fan-out lint) → Sprint 2 (metric builder) → Sprint 3 (semantic diff)
→ Sprint 4 (Trainer, with Step 3).** Sprints 1–3 are product; Sprint 4 is course.
