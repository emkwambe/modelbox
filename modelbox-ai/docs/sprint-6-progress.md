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

`THRESHOLD_VERSION` 1.0 → 1.1, so `docs/marketing/conformance-report.json`
cannot be compared across the change by accident.

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

---

## Carried, and why each is still open

| Item | Why it is open |
| :-- | :-- |
| **D10** — two conformance runs | Instrument is repaired and verified; the runs need a provider opt-in and a spend decision. The cloud half must pin `claude-sonnet-4-5-20250929` to isolate the metric change from a model change |
| **F4** — everything | Needs a synthetic N-entity fixture before any measurement is possible |
| **Task 7** — linter-feedback repair | `synthesis_engine.py:150-159` computes the report, logs a count, discards the issues |
| Two Docker-backed migration gates | Nine tests, never run — `8b10c4b` records "an argument, not a run". Docker is available again (29.6.1) |
| Data dictionary fidelity gate | Does not exist; three formats held at `UNVERIFIED` because of it |
| Violet-600 tier label | Needs a design decision, not a conversion (`colour.walk.test.ts:73-74`) |
| Canvas store smoke test | 521 lines, no test file (`PROJECT_STATE_REPORT.md:325`) |
| Five-graph prose drift | ~14 live documents, including five contractual `5/5` claims in `PROOF_LOG.md` and a `USER_GUIDE.md` shipped inside the app |

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
