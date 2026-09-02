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

### 2026-09-01 — Task 3, F1's type half gets a gate, and the gate finds a spec defect

`type.walk.test.ts`, the colour walk's twin. It counts **four** properties, not
just `fontSize`: a `type` token supplies size, weight, line height and tracking
together, so counting only size would let a tokenised size sit beside a
hand-written `fontWeight: 600` and read as converted. Opening budget **254**
across 20 files (264 total, less `tokens.ts`, which owns the values).

The walk and the comment stripper moved to `@/test/sourceWalk` rather than being
copied. A second hand-maintained comment stripper is the arrangement
`EntityNode`'s own accent-palette comment describes as guaranteeing one copy is
eventually wrong — and it is the piece most able to fail quietly, because a
stripper that eats too much makes *both* burn-downs under-count, and an
under-count reads as progress.

**Mutation:** two bare declarations added to a file outside the budget fail the
unbudgeted sweep, reported as `test/fixtures/largeGraph.ts (2)`.

**Two corrections to the colour walk while there.**

* Its header claimed **158** bare font sizes. The measured figure is **147**,
  an over-count of eleven, unchanged since the gate opened.
* `'has 332 colour literals left'` asserted `toBeLessThanOrEqual(332)`. That
  does catch a budget entry edited upwards — the total rises past 332 — but it
  cannot keep the name true: as conversions land the total falls, the assertion
  still passes, and the number in the test's own name silently becomes a lie.
  Both burn-downs now compare against a fixed `OPENED_AT` and are named without
  a figure.

#### The finding: the type ramp cannot express the product's own type

Building the detector produced a measurement nobody had: of the **64** places
that set a size *and* a weight in one style object, **exactly four match a step
in the ramp** — the four at 11/600.

| In the code | × | Nearest ramp step |
| :-- | --: | :-- |
| 13 / 600 | 20 | `uiSmall` 13 / **400** |
| 12 / 600 | 11 | `caption` 12 / **500** |
| 11 / 700 | 5 | `uiXSmall` 11 / **600** |
| 13 / 700 | 4 | `uiSmall` 13 / **400** |
| **11 / 600** | **4** | **`uiXSmall` — the only exact match** |

The UI-density pair was specified at weights 400 and 600; the call sites use 600
and 700 almost throughout. **So type conversion is not the mechanical exercise
colour conversion was** — 60 of the 64 sites either change weight visibly or
need a step that does not exist.

This reframes F1's type half from "0% converted" to "blocked on a specification
decision", which is a different and more honest status. It is recorded in
`ModelBox_AI_Design_Tokens.md` as the specification's defect rather than the
call sites': the ramp is the authority, so a ramp the product cannot express
itself in is the ramp's problem. It joins the violet-600 tier label as an open
design decision.

Frontend suite 31 files / 320 tests → **32 / 346**. `tsc` clean, lint clean.
Colour burn-down unmoved at 332 — this task built the instrument for the other
half and deliberately converted nothing, because the first honest conversion
needs the decision above.

### 2026-09-01 — Task 3, the first screen converted

`app/settings/egress/page.tsx`, chosen because the plan says convert by screen
rather than by file — so a screen leaves in a state F1, F2, F3 and F6 can all
assert against at once.

**Colour 30 → 0.** The entry is deleted from the budget rather than left at
zero; the unbudgeted sweep then holds it there, which is stricter than an entry
saying "should be none". Burn-down **332 → 302**. Type 17 → 16 (253 left) — the
rest of that file's type is blocked on the ramp decision above.

Both gates behaved as designed: the conversion turned them **red**, demanding
the budget be lowered, exactly as a burn-down that cannot be beaten silently
should.

**Two hand-rolled states became primitives**, which is F2 and F3 work on the
same screen. The amber box was `#fffbeb` / `#fde68a` / `#92400e` — three values
from Tailwind's amber ramp, none of them this product's, with the foreground
never measured against the ground it sat on. `Banner` derives both from the
`preview` role at an alpha the badge tests hold to the floor.

**A correction worth recording, because I nearly shipped it.** The comment I
first wrote for the error path claimed `#dc2626` measures 4.26:1 and therefore
*failed* the 4.5:1 body floor. Computed, it is **4.62:1** on this page's
`neutral-50` ground — it passes. `breaking.onLight` is 6.01:1, not the 5.92:1 I
also asserted. Both numbers were invented to justify a change that is correct
for a different reason: `#dc2626` is Tailwind's red-600, one of the two literals
`status-colour.test.tsx` bans by name and the most-repeated colour in the
frontend at 22 occurrences, and `StatusText` carries the assertive announcement
with the tone instead of leaving `role="alert"` to a call site that must
remember it. The comment now says that, with the measured figures.

This is the failure mode `CLAUDE.md` opens with — claiming a measurement not
performed — arriving in a code comment rather than in a test, where nothing
would have caught it.

Frontend 32 files / 346 → 32 / **345**: one fewer because a parametrised budget
case disappeared with the entry. `tsc` clean, lint clean.

### 2026-09-01 — Task 3, second screen, and an unmeasured surface

`components/editor/ExportPanel.tsx`, 26 → 0. Burn-down **302 → 276**. Entry
deleted rather than zeroed, as before.

**The find: the product has two dark surfaces and only declared one.**
`surface.dark` is navy `#0A1628` (canvas node headers). The export panel is
`neutral-900` `#0F172A`, and an earlier conversion had already put the `onDark`
semantic variants on it — an undeclared pair, which is exactly what naming the
surface is supposed to make unreachable. Because it was undeclared **nothing
measured it**: the status colours on the one dark surface a user reads
paragraphs on were never asserted. `surface.panel` now names it, with five pairs
declared against it, all passing.

`neutral-400` is one of them, deliberately. The palette warns it can never carry
body text — that warning is about *light* grounds, where it is 2.35:1. On the
panel it is **6.96:1**, and a declared pair is the only thing that can say so
rather than leaving a reader to assume the warning is universal.

Declared rather than repainted: the two grounds differ by **1.6%** in luminance
and every pair clears its floor on both, so moving the panel to navy would have
been a visual change made to satisfy a list rather than a reader.

**A conversion that lowers contrast, stated as such.** The panel's error text
was `#f87171` (Tailwind red-400) at **6.45:1**; `breaking.onDark` is **4.86:1**.
The token is worse on this axis. Both clear the 4.5:1 floor, and the reason to
take it anyway is that a product with two reds has no red — the panel would
otherwise disagree with every other failure in the product about what failure
looks like. Where that trade is *not* available the floor wins and the token
moves instead; that is what `neutral-400` → `neutral-500` did inside
`EntityNode`. Recording the direction because the previous entry recorded me
inventing numbers in the other one.

Frontend 32 files / **349 tests**. `tsc` clean, lint clean.

### 2026-09-01 — Task 3, third screen

`app/settings/api-keys/page.tsx`, 25 → 0. Burn-down **276 → 251**. Three screens
now converted; 81 of the original 358 literals are gone.

**A real contrast defect, not a branding one.** The empty state — *"No API keys
yet."* — was `#94a3b8`, which is `neutral-400` exactly, and `neutral-400`
measures **2.56:1** on white. That is user-facing prose at roughly half the body
floor, and it is the same defect `EntityNode`'s data-type label had. Moved to
`neutral-500` (4.76:1), not to the token it matched, for the reason recorded
there: a contrast failure behind a token name is worse than one in a literal,
because it looks decided.

Worth noting what found it. The burn-down does not measure contrast — it counts
literals. This surfaced because converting a literal forces someone to name the
token, and naming the token is where "2.56:1" becomes visible. That is an
argument for the burn-down that is not about tidiness.

The amber secret panel now derives its ground and border from
`toneColor`/`toneTint` at the `preview` role, the same helpers `Banner` uses, so
the pair cannot drift. The delete button's `#dc2626` border and text became
`breaking.onLight` — 4.83:1 → 6.29:1 on white.

Frontend 32 files / **348 tests**. `tsc` clean, lint clean.

### 2026-09-01 — Task 3 complete: the colour burn-down is 332 → 22

Fourteen remaining files converted. **All 22 that are left are deliberate**, and
the budget now says which of the two reasons applies to each.

| Left | Why |
| --: | :-- |
| 6 | `app/global-error.tsx` — the one file where an unreachable token is correct. It catches a throw in the root layout, which is exactly when `ui.css` may never have loaded. Its own header made this call before the burn-down existed. Held at 6 rather than deleted, so the exemption stays bounded |
| 16 | Violet — `#7c3aed` with its `#f5f3ff` tint and `#ddd6fe` border, in five places plus the tier label. **The palette contains no violet.** `entityAccent.HUB` is `#9333EA`, but that is an *entity type* accent; spending it on a Requirements Library button would conflate two vocabularies that happen to share a hue |

So F1's colour half is finished except for one design decision, and the decision
is now stated as one colour, one tint and one border rather than as sixteen
scattered literals.

**Two genuine contrast failures were removed on the way**, both invisible to
every contrast test because neither pair was ever declared:

* `#16a34a` as text — **3.30:1** on white, named in the burn-down's own opening
  paragraph as failing — in `app/page.tsx` and `DiffPanel.tsx`. Now
  `validated.onLight` at 5.5:1.
* `#94a3b8` as text at 11–12px in four canvas and settings files — **2.56:1**.
  Now `neutral-500`. The conversion script treated `color: '#94a3b8'`
  differently from every other use of the same literal for exactly this reason:
  as a border or a ground it is fine, as text it is half the floor.

**A bug the compiler caught that nothing else would have.**
`app/canvas/page.tsx` had `const actionBtn = (color: string) => ...`. The moment
the file imported the token module, `color.white` inside that function silently
resolved to a property of the string parameter — a shadowed name that is still a
valid expression. `tsc` failed it; no test would have. The parameter is `accent`
now.

Two mechanical faults in my own conversion, both caught before commit: a
template-literal wrapper (`` `${color.blue}` ``) left by an over-broad
substitution, unwrapped only where the template's entire content was a single
expression; and an import inserted *inside* a multi-line `import type { … }`
block by an "insert after the last import line" heuristic, which `tsc` rejected
as a syntax error.

Frontend 32 files / **339 tests** (fewer cases because thirteen budget entries
disappeared). `tsc` clean, lint clean.

### 2026-09-01 — Task 7, the linter's findings reach the model

`synthesis_engine.py` computed a full `ValidationReport`, logged the error
*count*, and discarded the issues. They reached the canvas for a human to fix by
hand and never reached the model that produced them. This is the one form of
self-correction with evidence behind it: a model critiquing itself gets worse; a
model handed an **external** deterministic verdict does not.

**The plan said "errors only". That did not survive the severity map.** Exactly
two of the thirteen codes are `error` — `CYCLIC_FK` and `DANGLING_REF`.
`MISSING_PK` is a *warning*, and so is the entire invented-constraint family
(`INVALID_RANGE`, `INVALID_REGEX`, `PATTERN_EXCEEDS_LENGTH`). Keying on severity
would have excluded the most mechanically fixable defects in the linter while
admitting nothing else.

So the partition is drawn where it actually lies: **a code is repairable when a
correct answer is objectively checkable from the graph alone.** Six codes
qualify. The seven excluded are excluded because they invite invention —
`MISSING_SLA` most of all, since "fix it" reads as "supply an SLA", which is
S5-2 arriving through the back door, and that exclusion is now an assertion
rather than a comment.

The three constraint codes are worth their place for a specific reason: an
invented `0-120` age range is repaired by *removing* it. They are the one family
where the fix direction is subtraction, which is the safest thing a repair pass
can be asked to do.

**One round, and a gate.** The repaired graph replaces the original only when it
carries strictly fewer repairable issues; otherwise the original is returned
untouched, including when the provider raises. A loop would need a termination
argument there is no evidence for, and each round is a real provider call
written to the egress ledger — doubling every synthesis's egress for an
unbounded gain is not a trade a governance product makes silently.

**Mutation results.**

| Mutant | Killed by |
| :-- | :-- |
| Acceptance gate removed (`if False`) | *does not improve is discarded* and *trades one defect for two is discarded* |
| Allowlist bypassed — whole report fed back | four tests, including *a clean graph costs no second call* and *the prompt lists only repairable codes* |

The second mutant is the one worth keeping: it is the change someone makes when
they think the pass is too conservative, and it silently re-opens S5-2.

**A precondition caught my own bad fixture.** The prompt-contents test sets a
tier to make `MISSING_SLA` fire; I wrote `"critical"` where the linter checks
`TIER_1_CRITICAL`, so the issue never appeared and the test would have "passed"
its real assertion by asserting the absence of something that was never there.
The `assert ..., "fixture precondition"` line failed instead. That is standard 8
working on a test written the same afternoon as the standard was quoted.

App suite 682 → **691 passed**, 41 skipped, 22 xfailed. Ruff unchanged at 69.

**Not claimed:** no provider was called. These tests pin the gate and the prompt
contents with a scripted stub — they say nothing about whether a real model
repairs a real graph, which is a question for D10's runs and for a Proof Log
entry that does not exist yet.

### 2026-09-01 — Four claims the product had earned and was forbidden to make

`PROOF_LOG.md`'s "not yet provable" table still blocked four claims on findings
**B1, H6, H2 and H1** — all closed in Sprints 3 and 4. The tests that closed them
pass 6/6, the non-preview fidelity leg is at **0 xfail**, and by rule E2/G3 the
product still could not say any of it, because no `PL-` entry named the tests.
That is the Proof Log producing the failure it exists to prevent, pointing the
other way: not overclaiming, but forbidding true statements.

`PL-011`–`PL-014` now exist. Every cited test was collected and run before being
written down — 81 passed, 1 skipped, and the skip is `marketing-attribution`
having no foreign keys to order, which is stated in the entry rather than
omitted.

Each entry carries the limit that keeps it honest:

* **PL-011** excludes **LookML** outright — `@preview`, defect M3 — so "semantic
  layer" means MetricFlow and Cube.
* **PL-012** is Protobuf tag stability across an *insert*; Avro parses but its
  compatibility rules are not asserted.
* **PL-013** rests on the B15 pair, where a mutant emitting well-formed
  `nullValues` in place of the declared pattern passes the vocabulary test and
  fails the meaning test.
* **PL-014** rests on `test_seed_fixtures_exercise_every_declared_rule`, without
  which the suite could pass by generating data for constraints no fixture
  declares.

The differentiator line — *"governed contracts and semantic layers, not just
schemas"* — stays on the blocked list on purpose. Both its blockers are closed
and the evidence is now PL-011 + PL-013, but register **G5** puts *stating* it
in Sprint 7. The evidence being ready is not the same as the wording being
decided.

#### And the rule itself is now enforced

`CLAUDE.md` says a Proof Log entry requires a named passing test. Nothing
checked it. `test_security_faq_cites_real_proof.py` guards **FAQ → Proof Log**;
the other link — **Proof Log → tests** — was unguarded, so an entry could cite
`test_odcs_apiverison_is_current` and no run anywhere would notice. The claim
would read as evidenced and the citation would be unfollowable.

`test_proof_log_cites_real_tests.py` closes it: 55 citations, one case each so a
failure names the broken one. Mutation: misspelling a single citation fails
exactly that case.

**The scanner failed twice on itself first**, which is worth recording because
both were the same class of error:

1. It matched *file* names — `test_artifact_fidelity.py::…` — and reported eight
   missing tests that were all modules.
2. Adding `(?!\.py)` did not fix it: the greedy `+` gave back one character to
   satisfy the lookahead, so the citation matched as `test_artifact_fidelit`.
   The word-boundary lookahead has to come first.

A scanner that cannot tell a file from a function would have made every entry in
the document look broken — a gate whose failure mode is "everything is wrong" is
as useless as one that never fires.

**Ruff moved 69 → 70** on this file (`FURB167`, `re.M`). Fixed rather than
absorbed, and back to 69 — the baseline exists so a number that moves is chased.

App suite 691 → **746 passed**, 41 skipped, 22 xfailed.

### 2026-09-01 — F6 says what it actually covers, and the hole it named is closed

F6 read *"Contrast meets the brand system's own WCAG standard"*, which implies
screen coverage the tests do not have: every assertion is against declared token
pairs or the ten `ui` primitives, and there is no page-level sweep — jsdom
computes no layout, so it could not do one honestly.

Marked **MET at a stated breadth** rather than either overclaimed or left
ambiguous. What makes the narrower claim worth having is F1: the colour
burn-down is at 22 of 358 and all 22 are recorded decisions, so nearly every
colour in the product now arrives through a pair this test measures. That is a
real change in what the criterion is worth, and it is why the honest wording is
"declared pairs" rather than "screens".

**The residual risk is named in the criterion, and then closed.** A pair can be
*used* and never *declared* — not hypothetical, since the export panel's
`neutral-900` ground was exactly that until this morning, with its status
colours unasserted while looking fully tokenised. Declaring `surface.panel`
fixed that instance; a new assertion fixes the class:

> every semantic role must be declared against every surface in `surface`,
> with light-or-dark derived from the surface's own luminance rather than from
> a hand-kept list.

Adding a surface now fails until its pairs are declared. **Mutation:** adding
`drawer: color.neutral[800]` with no `PAIRS` entries fails with *"validated on
surface.drawer is used by the product but not declared in PAIRS"*. A companion
assertion proves both branches are reachable — if every surface were light, the
`onDark` arm would never run and the loop would assert half of what it claims.

Frontend 32 files / **341 tests**. `tsc` clean, lint clean.

### 2026-09-02 — pushed, and CI was red for reasons that predate the session

The branch reached `origin` for the first time at 73 commits. **Its first CI run
failed two jobs, and both had been broken since `ea38547` — before any of this
session's work.** Neither was visible while the branch lived on one machine,
which is the argument for pushing rather than an argument against it.

**`npm ci` had been impossible since the test runner landed.** `ea38547` added
vitest and wrote a `package-lock.json` missing the per-platform esbuild optional
packages. `npm install` tolerates that; `npm ci` refuses it. So `vitest` and
`next lint` ran green locally for weeks against a `node_modules` that `npm ci`
could never have produced — every local frontend number in this document was
true and none of it was reproducible. Regenerated: 48 platform entries, and
verified with `npm ci --dry-run` (exit 0) rather than assumed.

This is the class `CLAUDE.md` already records for `requirements.lock` — *"a
Windows-generated lock pins Windows packages and omits environment markers"* —
in an ecosystem where nobody had written it down. The Python remedy is to
generate the lock inside a Linux image; the npm lock has no equivalent rule yet.

**The dbt package lock had drifted upstream.** `dbt_date` moved 0.19.0 → 0.21.0
beneath the range the exporter emits. The gate caught it and said so. The lock
was updated rather than the range tightened — the range is what customers
receive and is deliberately permissive; the lock is what the harness resolved —
and the cache was refreshed and the suite re-run **before** committing:
274 passed, 5 skipped, 0 xfail, identical to the run on 0.19.0. The verdict does
not change, which is the only thing that makes accepting the drift safe rather
than convenient.

**Second run green: all six jobs, 3m1s** (`33577877803`). That is the first
external verification any of this work has had.

No tag. Sprint 6 is not closed — D10 is open, F4's benchmark does not exist, and
F2 has screens left — and a tag would claim a close that has not happened.

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
