# Sprint 6 — Product Experience, and the Claim Underneath It

*Written 2026-09-01, mid-sprint, against `sprint/6-product-experience` at
`17e6ff2`. Every prior sprint had its brief before the first commit; this one has
twenty-two commits and no brief, so this document is written late and says so.
Its measurements were taken for it, not quoted from a progress doc.*

**Scope note.** Sprint 6's only written definition of done is one sentence four
sprints old — `ModelBox_AI_Sprint_Plan.md:218-219`: *"every screen uses tokens
rather than ad-hoc values; no unstyled error or empty state remains; `next lint`
passes in CI; contrast verified."* It omits F3, F4 and F5 entirely. That
sentence is superseded by the Definition of Done at the end of this file.

---

## 0. Where this sprint actually is

Measured 2026-09-01. Frontend suite 312 passed / 29 files. Backend 682 passed,
41 skipped, 22 xfailed. Fidelity non-preview 274 passed, 5 skipped, **0 xfail**.
Ruff 69. Versions all 1.10.0.

| ID | State | The honest one-line version |
| :-- | :-- | :-- |
| F1 | **7% colour, 0% type** | 332 of 358 literals remain; 147 bare font sizes have no detector at all |
| F2 | **4 screens of 8** | boundaries exist and route; four screens still hand-roll state |
| F3 | **met inside the canvas** | and the assertion already caught a real defect (`789bacb`) |
| F4 | **nothing** | no test, no fixture, no way to build a 500-table model |
| F5 | **met** | register does not say so |
| F6 | **token layer only** | no rendered-screen sweep; the 332 literals are outside every contrast assertion by construction |
| F7 | **met** | `.eslintrc.json` committed, CI job blocking since v1.6.0 |

Two of the seven are finished and unrecorded. One has no evidence of any kind.

**The thing this sprint has not touched.** All twenty-two commits are frontend.
The product's main function — natural-language requirements to a data model —
has no quality number attached to it, because D10 is still open from Sprint 5.
Sprint 6 is polishing the surface of a capability whose accuracy nobody has
measured. Tasks 6 and 7 below exist to correct that, and if the sprint has to be
cut, they are the last things to cut, not the first.

---

## Task 0 — The progress document, and the register

`sprint-5-progress.md:1-18` states the rule this sprint is breaking: *"This file
is written to at every commit boundary, not at sprint end"* — a rule bought by a
session lost to a restart, in which two of three mutants survived only in chat.
Twenty-two commits of this sprint's reasoning currently exist only in commit
bodies.

1. Open `docs/sprint-6-progress.md` with the §0 table above as its baseline, and
   write to it at every commit boundary from here.
2. Mark **F5** and **F7** `**MET**` in the register, each naming its evidence —
   F5 the `ExportPanel.status.test.tsx` parameterised suite and the
   `artifact_status.py` manifest; F7 the `frontend-lint` CI job with
   `--max-warnings 0`.
3. Correct **A7**. It reads "the three Preview dialects **(15)** and LookML
   **(3)** … **18** xfail, 2 pass". The true figures are 18, 4 and **22**: the
   AML graph added three DDL preview xfails and one LookML. `AML_Slice_1_Scope.md:108-117`
   predicted the inventory would move at that commit and asked for the note to
   be written before the run. It was not. No test asserts these counts, which is
   why nothing caught it.

**Definition of done:** the register states nothing that the commands in §0
contradict.

---

## Task 1 — Close the five-graph drift

`aml-financial-crime` made the gold set six. The fixture layer absorbed this
correctly — every per-graph test globs the directory or compares sets, and the
anti-transcription drift guard covers the sixth graph like the other five. The
residue is prose, and some of it is contractual.

1. **`docs/marketing/PROOF_LOG.md`** — five `5/5` and "all five reference
   models" claims. E2/G3 make these public-surface claims; they are now false.
2. **`frontend/public/content/USER_GUIDE.md`** — "5 gold-standard starter
   scenarios", **shipped to users inside the app**. Second copy at
   `docs/USER_GUIDE.md`.
3. **`CLAUDE.md:145`**, **`ORIENTATION.md:96,136-139`** (the enumeration and the
   `5/5` ratio), `synthetic/README.md:3`, and the source comments in
   `exporter_service.py:635`, `synthesis_engine.py:81`,
   `test_cross_artifact_consistency.py:88`.
4. **`docs/marketing/conformance-report.json`** — produced under
   `THRESHOLD_VERSION 1.0` by a metric its own run invalidated, holding five
   graphs and entity F1 0.288. Delete it or move it out of `marketing/`. The
   1.0→1.1 bump makes it *detectable*; it does not make it harmless while it
   sits in the directory reserved for public claims.
5. Leave the dated records alone — release notes, sprint logs, the state report.
   Changing them rewrites history. A dated note is the correction there.

**Not in scope:** a test that asserts the prose. Prose drift is caught by
reading, and a test over English is a worse instrument than the reading.

---

## Task 2 — F4, made assertable

The criterion says "Canvas remains usable at 500 tables", evidenced by a
"profiling run". There is no profiling run, no benchmark, and **no way to
produce a 500-table model** — the largest fixture is 28 entities across all six
templates, and the backend's synthetic generator makes rows, not tables.

Four defects were verified in the code before this plan was written. None is a
tuning question:

| Where | What |
| :-- | :-- |
| `EntityNode.tsx:72-78` | the validation selector returns `.filter(...) ?? []` — a new array on every store notification. zustand ^4.5.0 compares with `Object.is`, so **every** store write re-renders **every** node, and the `?? []` means it does so even with no validation report at all |
| `EntityNode.tsx:67` | not wrapped in `React.memo` — though this changes nothing until the selector is fixed |
| `canvasStore.ts:39,183` | `NODE_HEIGHT = 160` is passed to dagre for every node regardless of column count. A 40-column node is ~600px tall. **This is a correctness bug that will present as a performance complaint** |
| `canvasStore.ts:~205` | `structuredClone(nodes)` + `structuredClone(edges)` on every mutation, `HISTORY_LIMIT = 50` |

**Split the criterion, because timing and structure have different
reliability.**

**2a — Deterministic gates (CI).** These are integers, machine-independent, and
currently false:

* A synthetic N-entity graph factory. This is the prerequisite for everything
  else in the task and does not exist in any form.
* **Render-count invariant** — with a 500-node fixture, dispatch one
  `selectColumn` and assert `EntityNode` renders `<= 2`. Today that number is
  500. This is the highest-value assertion in the sprint: unfakeable, cannot
  flake, and goes red the moment someone reintroduces a broad selector.
* **Layout overlap invariant** — after `applyLayout` on the 500-node fixture,
  assert zero bounding-box overlaps using *real* node heights. Pure geometry;
  catches the `NODE_HEIGHT` defect.
* **`dagre.layout()` wall time** on a fixed fixture with a loose ceiling. Pure
  CPU, no browser, no paint — the one timing number stable enough to gate.
  **Measure before optimising:** if it is 200ms a web worker is premature; if it
  is 5s it is mandatory. Nobody knows which, and the only public number
  (1,000 nodes ≈ 3 minutes) is via cytoscape and is an upper bound, not dagre's.

**2b — The recorded run (not a gate).** Drag FPS and interaction-to-next-paint
on a shared runner are dominated by neighbour load; a threshold is either so
loose it catches only catastrophe or it flakes weekly. Record a scripted
benchmark on named hardware, commit the output, cite it with the machine and
browser version stated. That is a real profiling run and it satisfies the
criterion honestly — it is not a CI gate, and the register should say which half
is which.

**Order matters.** Fix the selector first; `React.memo` does nothing before it.
Then measure. Then virtualise (`onlyRenderVisibleElements`, level-of-detail
below zoom ~0.5) **only if the numbers justify it** — that conditional is
already the sprint plan's own at `Sprint_Plan.md:213`.

**A caution from the record.** No public report exists of React Flow at 500
nodes with 10-40 child rows each. A maintainer's position is that this scale
wants a canvas approach. It is entirely possible the measurement says the
criterion is not reachable in the current architecture — in which case the
honest outcome is a narrowed criterion with a stated ceiling, not a quiet pass.

Also outstanding here: `store/canvasStore.ts` is 521 lines with **no test file**
(`PROJECT_STATE_REPORT.md:325`, M9 partially closed). The fixture built for 2a
makes that test cheap.

---

## Task 3 — F1, both halves

**Colour: 332 of 358 remain.** Two files have ever been touched. The single
biggest entry, `app/trainer/page.tsx` at 65, is 20% of the burn-down and
untouched. Convert by screen, not by file, so a screen leaves in a state F2, F3
and F6 can all assert against at once.

**Type: no gate exists, and the stated count is wrong.** The colour walk's
header claims 158 bare font sizes; the measured figure is **147 across 20
files** (61 × `13`, 39 × `12`, 17 × `11`), unchanged since the burn-down opened.
The `type` ramp exists and is tested, but **no component imports it** — its only
consumers are the ten `components/ui` primitives via `--mb-type-*`. Build the
type detector and budget on the colour walk's own pattern, and fix the header's
count while doing it. Note the detector gaps that colour does not have:
`font-size` also appears 20× in `.css`, and `fontWeight` / `lineHeight` /
`letterSpacing` are unmeasured.

**One repair.** `colour.walk.test.ts:207` asserts `toBeLessThanOrEqual(332)`
while the test's name claims "has 332 left". The assertion correctly catches an
entry edited *upward*. What it cannot do is keep the headline true as
conversions land — the total falls, the test stays green, and the name silently
becomes a lie. Either assert equality and edit the constant with each
conversion, or take the number out of the name.

Still open and deliberately visible: the violet-600 tier label, held in the
budget at 1 because it needs a design decision rather than a conversion
(`colour.walk.test.ts:73-74`).

---

## Task 4 — F2, the four remaining screens

`errorKind` has exactly two consumers. Convert `app/page.tsx`,
`app/trainer/page.tsx`, `app/settings/egress/page.tsx` and `ExportPanel.tsx`'s
error path to `ErrorState` / `LoadingState` / `StatusText` with the
three-outcome discriminated union, including the 403 path that is worded as
permission and carries no retry button.

Three states named in the sprint's own scope text were never built
(`Sprint_Plan.md:210-212`): **synthesis in progress**, **partial failure**, and
**air-gapped with no provider reachable**. The third is not cosmetic — the
router records a chain exhausting four providers in 23 seconds, and the user
currently sees nothing meaningful while that happens.

Known limit to keep stated: `boundaries.walk.test.ts` asserts the files exist
and route correctly, and **never renders one**, because jsdom cannot reproduce
when Next invokes a boundary.

---

## Task 5 — F6, or a narrower F6

Every contrast assertion today is against tokens or the ten `ui` primitives. The
332 unconverted literals are outside all of them **by construction** — which is
exactly how `ValidationPanel`'s 3.30:1 "valid" headline survived until `789bacb`.

Either add a rendered-DOM contrast walk over the seven routes, or amend F6 to
say it is as broad as F1's burn-down and no broader. The second is acceptable;
the current wording, which implies screen coverage it does not have, is not.

`ModelBox_AI_Design_Tokens.md` also cites `tokens.spec.test.ts` and two
Python-style test names that do not exist — the file is `tokens.test.ts` with
vitest `it(...)` names. A specification that names a passing test must name the
test that passes.

---

## Task 6 — D10, carried from Sprint 5

The threshold is banked, the metric is rewritten, the isolation is verified, the
identity check now covers 6 of 6, and `NEW_CODE_GRAPH_COUNT` has been restored
to a majority at 4 with `THRESHOLD_VERSION` bumped to 1.1. **What is missing is
two runs.**

* **Cloud, pinned to `claude-sonnet-4-5-20250929`.** That identifier is still
  Active and it is the appliance's own `default_model`, so the run is
  reproducible and comparable. One variable moves — the instrument — which is
  the only way to learn how much of entity F1 0.288 was the metric.
* **Cloud, current model.** Two Sonnet generations have shipped since; the route
  asks for a "high-reasoning, large-context model" and the pin is the product's,
  not just the experiment's.
* **Local.** `ollama-engine` up, `qwen2.5-coder:32b` pulled. D10 does not close
  on a cloud half alone — that is what left it open last time.

**A methodological defect to fix before the runs, not after.**
`_normalize_relationships` deterministically repairs Fact→Dimension cardinality
**before** `GraphEngine.validate` runs, and it covers **Kimball only**. So any
relationship number is post-repair for two gold graphs and pre-repair for the
other four. Comparing across paradigms without splitting on that is standard 4's
exact shape: a measurement that cannot distinguish the two rules because one of
them already fixed the output. Either report the axis split by paradigm, or
score before normalisation, and say which.

---

## Task 7 — The lever the product already owns

`synthesis_engine.py:150-159` computes a full `ValidationReport` from the
thirteen-rule linter, logs a **count**, and discards the issues. They reach the
canvas for the user to fix by hand; they never reach the model.

This is the best-supported intervention available. Self-critique alone
degrades — GPT-4 on GSM8K falls 95.5 → 91.5 → 89.0 over two rounds, and the
survey position is that self-correction works only with reliable *external*
feedback. A deterministic linter is external feedback, and the closest published
analogue is static-analysis repair loops, which drove targeted violation classes
from 40-80% down to ~11-13%.

**Implementation, deliberately small:**

* One extra `structured_completion` call, conditional on `not report.is_valid`.
* **Errors only, never warnings.** Feeding back `MISSING_SLA` or
  `NAMING_CONVENTION` invites the model to invent a tier to silence the rule —
  reintroducing S5-2 through the back door, in the venue where an invented
  constraint ships into a data contract as fact.
* **Cap at one round, and assert monotonic improvement:** the error count must
  strictly decrease or the original model is kept. A repair pass that can make
  things worse and has no gate is not a repair pass.
* Expect near-elimination of the mechanical classes — `DANGLING_REF`,
  `CYCLIC_FK`, `MISSING_PK`, `INVALID_REGEX`, `PATTERN_EXCEEDS_LENGTH` — and
  little or nothing on the semantic ones. Pre-register that split.

**Two smaller items in the same file, both near-zero risk:**

* `SynthesizedModel` gives the model no tokens to think before `paradigm` and
  `entities` are emitted. Add an `analysis` field declared *first* and discard
  it after validation. `_persist` reads only entities, relationships and
  metrics, so nothing downstream changes.
* `instructor.from_litellm(acompletion)` is called with no `mode=`. Tool-calling
  is the correct portable choice — it is the only mechanism available across all
  eight providers, and the pinned `kimi-k2-0711-preview` rejects
  `response_format` entirely — but it is currently a library default, not a
  decision. Pass it explicitly and assert it in a test.

**Explicitly deferred, with reasons.** Staged synthesis is the pre-registered
remedy and the best-evidenced change for the relationship layer, but the same
evidence predicts an **attribute regression** (one study: relationships
0.52 → 0.92, attributes 0.59 → 0.44). Columns are what become the data contract,
so that trade is not obviously right here. Defer until D10 produces a baseline —
and when it is attempted, attributes must be a **guarded metric**, and pass 2
must be allowed to add an entity, because an entity missed in pass 1 is
otherwise unrecoverable by construction.

Few-shot exemplars are deferred for a harder reason: **the six reference models
are the gold graphs.** Using them as exemplars and as the evaluation set would
make every conformance number meaningless.

---

## Definition of Done

1. `docs/sprint-6-progress.md` exists and has been written at every commit
   boundary since Task 0.
2. The register states nothing the §0 commands contradict — F5 and F7 marked
   met, A7 corrected to 18/4/22.
3. No public surface claims five gold graphs. The stale conformance report is
   out of `marketing/`.
4. F4 has a synthetic 500-entity fixture, a render-count invariant that is green
   only because the selector is fixed, a layout-overlap invariant, a dagre
   timing gate, and a recorded benchmark on named hardware — **or** a narrowed
   criterion stating the measured ceiling.
5. F1 has a type budget as well as a colour budget, and the header's count is
   the measured one.
6. F2's four screens carry `errorKind`; the three unbuilt states are either
   built or recorded as deferred with a reason.
7. F6 either covers rendered screens or says it does not.
8. D10 closes on a cloud half and a local half scored under `THRESHOLD_VERSION`
   1.1, with the paradigm-normalisation confound resolved.
9. Task 7's repair pass exists with its monotonic-improvement gate, or is
   recorded as deferred with the baseline that justified deferring it.

---

## Constraints

* Every claim reaching a public surface needs a `PL-` id behind a **passing
  test**. An FPS number from a laptop is not one; "one column click causes two
  renders, not five hundred" is.
* The gold graphs are a curriculum and marketing asset. Defect reproductions go
  in `fixtures/synthetic/`. The 500-entity performance fixture is synthetic and
  belongs there, not in `gold/`.
* Check the fidelity inventory at every commit boundary. It is currently 274
  passed / 5 skipped / **0 xfail** non-preview, and 22 xfail / 2 pass preview.
  If it moves, the commit that moved it is the bug — and the AML graph has
  already shown that a legitimate move looks identical to a regression until
  someone checks which commit caused it.
* No provider call without `MODELBOX_ALLOW_PROVIDER_CALLS=1` deliberately set.
  The absence of that variable is the fail-closed gate working, not an obstacle.

---

## Open decisions

These need a person, not a default:

1. **F4's ceiling.** If 500 tables is not reachable without a canvas rewrite, is
   the criterion narrowed or is the rewrite scheduled?
2. **F5's silent success.** A certified artifact currently shows *no* badge —
   the banner renders only when status is not `CERTIFIED`. Does certified
   deserve a positive affirmation?
3. **The data dictionary has no fidelity gate at all**, which is why three
   formats sit at `UNVERIFIED`. Build it, or state the deferral in the register.
4. **The violet-600 tier label** (`colour.walk.test.ts:73-74`).
5. **Two Docker-backed migration gates have never run** — nine tests, recorded
   in `8b10c4b` as "an argument, not a run". Docker is available now.
