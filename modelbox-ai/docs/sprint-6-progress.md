# Sprint 6 — progress

*Branch `sprint/6-product-experience`. Opened 2026-09-01 at `6154e88`, which is
twenty-two commits into the sprint.*

**This file is written at every commit boundary, not at sprint end.** That rule
was bought in Sprint 5 by a session lost to a restart, in which two of three
mutants survived only in chat and were lost with it
(`sprint-5-progress.md:1-18`). This sprint broke the rule for twenty-two
commits; the reasoning behind them exists only in commit bodies, which are not
searchable by criterion and cannot record a number that later moved.

Opening late has one consequence worth stating rather than hiding: **the
baseline below is a measurement taken today, not the baseline the sprint
started from.** Where a starting figure is recoverable from git it is given;
where it is not, the row says so.

---

## Baseline, measured 2026-09-01 at `6154e88`

Each row is the output of the command beside it, run for this file. Not quoted
from another document.

| Measure | Result | Command |
| :-- | :-- | :-- |
| Frontend suite | **312 passed, 29 files** | `npx vitest run` |
| App suite | **682 passed, 41 skipped, 22 xfailed** | `.venv/Scripts/python -m pytest -q` |
| Fidelity, non-preview | **274 passed, 5 skipped, 0 xfail** | `MODELBOX_FIDELITY_STRICT=1 .venv-tools/… -m "not preview"` |
| Fidelity, preview | **22 xfailed, 2 passed** | same, `-m "preview"` |
| Ruff over `app` + `tests` | **69 findings** | `.venv/Scripts/python -m ruff check app tests` |
| `next lint` | **clean, exit 0** | `npx next lint --max-warnings 0` |
| Version stamps | **all agree: 1.10.0** | `python scripts/check_versions.py` |
| F1 colour burn-down | **332 of 358** | `BUDGET_TOTAL`, `colour.walk.test.ts:62-84` |
| F1 type sites | **147 across 20 files, ungated** | `grep -rE "fontSize: *[0-9]" src` |

### How this differs from the Sprint 5 baseline, and why

`ORIENTATION.md` §6 recorded 572 / 36 / 18, fidelity 229 / 5 / 0, and preview
18 xfail / 2 pass on 2026-08-27 at `0c6daf8`. Every one of those has moved. The
inventory moving is the thing `CLAUDE.md` says to treat as a bug until the
commit that moved it is identified, so it was identified:

* **App suite 572 → 682, fidelity 229 → 274, preview 18 → 22.** All of it is
  `e0beb47` (AML slice 1) adding a **sixth** gold graph, plus the Sprint 5 tail.
  The preview arithmetic is exact: 3 preview dialects × 6 graphs = 18, plus
  LookML's list which went from 3 names to 4. **Every one of the 22 carries a
  preview reason** (`H3/Q4` or `M3`); no new defect is hiding in the growth.
* **Ruff held at exactly 69** across two sprints. Unchanged is not the same as
  examined — these 69 findings have now survived two sprints unread.
* **Versions 1.9.0 → 1.10.0**, expected: `e5cb2a0` cut the release.

---

## Criterion status at open

| ID | State | Note |
| :-- | :-- | :-- |
| F1 | 7% colour, 0% type | 332 literals across 19 files; two files have ever been touched |
| F2 | 4 screens of 8 | `errorKind` has exactly two consumers |
| F3 | met inside the canvas | its assertion already caught a real defect (`789bacb`) |
| F4 | **no evidence of any kind** | no test, no fixture, no way to build a 500-table model |
| F5 | **MET** — recorded this commit | was finished and unrecorded |
| F6 | token layer only | the 332 literals are outside every contrast assertion by construction |
| F7 | **MET** — recorded this commit | was finished and unrecorded |

Two of seven were done and unmarked. The register carried no `**MET**` for
either, so the sprint looked further from done than it was — in the direction
that costs work rather than credibility, but wrong either way.

---

## Log

### 2026-09-01 — `8ba4f9a` The gate said "a majority of graphs"

`NEW_CODE_GRAPH_COUNT` 3 → 4. Banked in `b6a3e1a` as ">= 3 of 5 graphs" with the
published rationale "on three of five it is a systematic behaviour" — a
majority. The sixth graph made it 3 of 6, a minority, without the constant
moving. **This is the only place in the repo where the sixth graph changed a
pass/fail verdict**; every other per-graph site globs the fixture directory or
compares sets.

Allowed under the file's own a-priori rule because the ground is the
denominator, not a score: no run exists under the rewritten metric to have
fitted it to, and the direction is stricter. Left as a count rather than a
computed majority deliberately — deriving it from `len(GOLD_IDS)` would let it
move without a decision, which is the property that file exists to deny.

`THRESHOLD_VERSION` 1.0 → 1.1, so the first run's report cannot be compared
across the change by accident. (That report has since moved to
`docs/marketing/superseded/` — see the Task 1 entry below.)

### 2026-09-01 — `17e6ff2` Two guards scoped to the instance that provoked them

**The conformance identity check covered four of six graphs and passed green.**
It ran on a hand-written four-name list; `marketing-attribution` was never in
it and `aml-financial-crime` did not join it. Derived from the fixture directory
now, with a floor assertion so an empty glob cannot make every case vacuous.

Expanding it immediately earned a failure the list had been hiding:
`marketing-attribution` returns `None` on the relationship axis, because it is a
single-table OBT model and the empty-set fix excludes an axis with nothing to
judge rather than handing it a free 1.0. **That is the metric working.** So the
*axis* is inapplicable, not the graph — whose entity and column identity checks
apply perfectly well and now run. Both arms of that rule are asserted reachable
from the fixtures, or the `None` branch would never execute and the assertion
would be indistinguishable from `== 1.0`.

**`schema_reasoning_and_erd` declared a primary the appliance does not ship.**
Sprint 5 closed exactly this defect for the air-gapped table, and
`test_no_airgapped_primary_is_bring_your_own` guards it — iterating
`airgapped_overrides` only. The identical shape sat untouched in the default
`task_routing` table, where ERD synthesis and constraint checking pointed at
`vllm-server.internal`. It never surfaced because it failed over: the cost was a
dead connection and a ledger failure on every call, not an outage.

Primary is `anthropic_cloud` now, `airgapped_vllm` kept last for operators who
run their own. `local_ollama` would not serve — `ollama-engine` is behind the
`airgap` compose profile and is not up by default.

Both routing tables are now asserted non-empty, so a renamed key cannot make
either comprehension pass by iterating nothing.

### 2026-09-01 — `6154e88` The sprint brief, twenty-two commits late

`docs/SPRINT_6_PROMPT.md`. Measured rather than quoted; F4 split into
CI-gateable integers and a recorded benchmark; Tasks 6 and 7 added for the
product's main function, which twenty-two frontend commits had not touched.

Records a confound found while writing it: **`_normalize_relationships` repairs
Fact→Dimension cardinality before `GraphEngine.validate` runs, and covers
Kimball only.** Any relationship number is therefore post-repair for two gold
graphs and pre-repair for four. That is standard 4's shape — a measurement that
cannot distinguish two rules because one already fixed the output — and it must
be resolved before the conformance runs, not after.

### 2026-09-01 — Task 0

This file. Plus:

* **F5** and **F7** marked `**MET**` in the register with their evidence and
  their limits. F7's marker rests on a run made for it — `npx next lint
  --max-warnings 0` → `✔ No ESLint warnings or errors`, exit 0 — not on the
  commit bodies that assert it.
* **A7 corrected** from "(15) and (3) … 18 xfail" to "(18) and (4) … 22 xfail".
  Both parentheticals are per-graph products, so they moved the moment `e0beb47`
  landed. `AML_Slice_1_Scope.md:108-117` predicted this and asked for the note
  to be written *before* the run; it was not, and no test asserts these counts,
  so nothing caught it. A criterion stating a number its own command no longer
  produces cannot do the job A7 exists to do.

### 2026-09-01 — Task 1, the five-graph drift

Closed in the live documents. Three findings made it more than a number bump.

**Two claims were historical and must not have been changed.**
`PROOF_LOG.md:100` describes a semantic-layer exporter that `dbt parse` rejected
"on 5/5 models" during the 59 green CI runs *before* v1.6.0 — when there were
five graphs. `synthesis_engine.py:81` records `MISSING_SLA` firing on 5 of 5
candidate graphs in the first conformance run, which scored five. Both are
dated facts; rewriting them to six would have made them false. The second was
reworded to say whose count it is rather than left to be misread.

**Two comments asserted a property, not a count.** `exporter_service.py:635`
and `test_cross_artifact_consistency.py:88` both state that on the gold graphs
`not is_nullable` and `is_primary_key` are the *same partition* — correction C7,
and the reason the cross-artifact test needs a mutated copy to mean anything. A
sixth graph could have broken that, which would have made the mutated copy
unnecessary and the comment wrong in a way a number bump would have hidden. So
it was measured rather than assumed: loaded through `SynthesizedModel`, **all
six graphs have zero columns where the two differ**, `aml-financial-crime`
included. The property holds, the mutated copy is still mandatory, and the
comments now say six on evidence.

Worth recording how nearly that went wrong: read straight from the JSON the
same check reports 3-12 "discriminating" columns per graph, because a primary
key is not written with `is_nullable: false` in the fixture — the schema layer
supplies it. Checking the raw file would have concluded the opposite. That is
the "verify from outside the layer" standard inverted: here the layer *is* the
thing that establishes the property, so the raw file is the wrong altitude.

**`test_dbt_project_is_self_contained` runs 7 cases, not 6** — the seventh is
the synthetic `quality-rules` fixture. `PROOF_LOG.md` now says so, because "6/6
reference models plus a synthetic defect reproduction" is a stronger claim than
6/6 alone: it is not resting only on graphs chosen to showcase the product.

**Counts verified by collection before they were written**, not inferred:
`test_ddl_executes_on_duckdb` 6/6; `test_ddl_dialect_grammar` 7 dialects × 6
graphs, of which 24 are the certified 4 × 6.

**The stale report moved** to `docs/marketing/superseded/` with a README stating
what it is, why it is invalid, and why it must not be deleted — D10's method is
that the threshold predates the first call, and that file is the record of the
first call. `marketing/` is for public claims; a file of invalidated numbers in
it is the Proof Log's own failure mode pointing the other way.

**Two Docker-backed migration gates were run** while verifying `PL-006`'s
determinism claim, since it rests on one of them: `test_migration_0013_populated`
and `test_migration_0015_egress_audit`, **9 passed**. `8b10c4b` had recorded
them as "an argument, not a run". They are now a run, and that carried item is
closed.

**Left alone deliberately:** the dated records — release notes, sprint logs, the
state report. `ORIENTATION.md` §6 got a superseding note rather than edited
numbers, because it is a record of commands run on a date and editing the
numbers destroys the only thing it is for.

**Noticed, not fixed:** `docs/USER_GUIDE.md` and
`frontend/public/content/USER_GUIDE.md` are byte-identical copies with **no test
asserting they stay that way**. Both were updated here; the next editor may
update one. That is a drift guard this sprint has not written.

Suites after: app 682 / 41 / 22, fidelity 274 / 5 / **0 xfail** — both unchanged,
which is the point of touching only comments and prose. `_SYSTEM_PROMPT`'s
SHA-256 was checked directly, because the conformance record stores it as
provenance and a comment edit inside a string concatenation is exactly where
that could go wrong unnoticed.

### 2026-09-01 — Task 2, F4's gateable half

F4 had no evidence because its subject could not be built. `src/test/fixtures/
largeGraph.ts` builds an N-entity graph with deterministic, *varying* column
counts — varying because a fixture of uniform height cannot tell a layout that
measures height from one that assumes a constant, which is the defect.

**The re-render storm, fixed and pinned.** `EntityNode` had two subscriptions
that could not be memoised: `s.validation?.issues.filter(...) ?? []` built a new
array on every notification, and `s.selectedColumn` is an object every node
watched. Either alone re-renders all 500 nodes; `React.memo` could not help,
because the component genuinely did re-subscribe. Fixed by narrowing both — a
stable `s.validation` reference with the filter moved to `useMemo`, and a
selector returning this entity's selected column *name* — with `memo` last,
which is the only order in which it does anything.

Measured with React's own `Profiler` rather than a wrapper, because a wrapper
does not re-render when its child's subscription fires.

| Assertion | Before | After |
| :-- | :-- | :-- |
| renders after one `selectColumn` | 500 | **2** |
| renders after a store write naming no entity | 500 | **0** |
| renders for a new validation report | 500 | 500 — see below |

The third is deliberate and stated in the test: a new report is a new object, so
every node re-evaluates whether it is named. That is correct and rare —
validation runs on demand, not per frame. Narrowing it further means indexing
issues per entity in the store, which is more change than the defect warranted.

**Mutation results.** Both arms run against the fixed component, one at a time,
and they kill *different* assertions — which is what shows they are two defects
rather than one described twice:

| Reverted | Killed by |
| :-- | :-- |
| the `issues` selector | **both** the selection test (500 ≰ 2) and the unrelated-write test (500 ≠ 0) |
| the `selectedColumn` object subscription | the selection test only; the unrelated-write test still passes |

So the unrelated-write assertion is the only thing in the file that pins the
`issues` selector specifically.

**The layout defect was geometry, not performance.** `NODE_HEIGHT = 160` went to
dagre for every node regardless of column count, while a 40-column entity is
~750px tall — so ranks were spaced for a node a quarter of the size and the tall
ones overlapped everything beneath. Replaced with `estimatedNodeHeight(columns,
banners)` derived from `EntityNode`'s own row and header metrics. Validation
banners are excluded on purpose: a layout that moved every time the linter ran
would be worse than one a row short on a node missing a primary key.

Mutation: restoring the fixed 160 makes the overlap sweep fail with real
collisions (`fact_events_0` among them), so the assertion is not vacuous.

**dagre was measured before anything was optimised**, which was the plan's own
condition:

| Entities | Edges | `applyLayout` |
| --: | --: | --: |
| 100 | 90 | 80 ms |
| 250 | 225 | 118 ms |
| **500** | **450** | **248 ms** |
| 1000 | 900 | 635 ms |

Near-linear at this size and 248 ms at F4's number. **A web worker is therefore
premature** — the plan said measure first precisely so that could be decided
rather than assumed. The committed ceiling is 10 s, far above the measurement,
because it exists to catch a change in complexity and not a busy runner.

Frontend suite 29 files / 312 tests → **31 / 320**. `tsc --noEmit` clean,
`next lint --max-warnings 0` clean.

**Not done in this task, and still F4's larger half:** virtualisation
(`onlyRenderVisibleElements`, level-of-detail below zoom ~0.5), the
`structuredClone`-per-mutation history cost, and the recorded browser benchmark
that carries the smoothness claim. None of them should start before the
benchmark exists, or there is nothing to say they helped.

---

## Carried, and why each is still open

| Item | Why it is open |
| :-- | :-- |
| **D10** — two conformance runs | Instrument is repaired and verified; the runs need a provider opt-in and a spend decision. The cloud half must pin `claude-sonnet-4-5-20250929` to isolate the metric change from a model change |
| **F4** — everything | Needs a synthetic N-entity fixture before any measurement is possible |
| **Task 7** — linter-feedback repair | `synthesis_engine.py:150-159` computes the report, logs a count, discards the issues |
| ~~Two Docker-backed migration gates~~ | **Closed 2026-09-01** — 9 passed under Docker 29.6.1 |
| Data dictionary fidelity gate | Does not exist; three formats held at `UNVERIFIED` because of it |
| Violet-600 tier label | Needs a design decision, not a conversion (`colour.walk.test.ts:73-74`) |
| Canvas store smoke test | 521 lines, no test file (`PROJECT_STATE_REPORT.md:325`) |
| ~~Five-graph prose drift~~ | **Closed 2026-09-01** — see the Task 1 entry. Dated records left as history; a `USER_GUIDE.md` copy-drift guard remains unwritten |

---

## Mutation results

*None yet this sprint. Recorded here as an absence rather than omitted: Sprint 5
carried a mutation table per task, and the register's standard is that a test
which cannot be shown to fail for the right reason has not been shown to work.*

The two candidates already identified, to be run when their tasks land:

* **F4 render-count invariant** — revert the `EntityNode` selector fix and the
  count must return to 500. If it does not, the test is measuring something
  else.
* **Task 7 repair pass** — feed back a report with zero errors and assert no
  second call is made; feed back a report the model cannot satisfy and assert
  the original model is kept rather than a worse one.
