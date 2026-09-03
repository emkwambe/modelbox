# Outstanding issues

**As of 2026-09-03, branch `sprint/6-product-experience`.** Companion to
`BUILD_EVIDENCE_REVIEW.md`, which argues the evidence; this one is the list.

Every entry names where it is recorded in the tree, so nothing here depends on
remembering a conversation. Ordered by kind, not priority — §7 has the priority
argument.

---

## 1. Register criteria not met

| id | state | what is missing |
|---|---|---|
| **D10** | **open, two ways** | The cloud half **ran and failed** (2026-09-03, 12 calls, both models FAIL on all three F1 axes). The **local half has never been attempted** — `ollama-engine` / `qwen2.5-coder:32b` was never stood up, and Sprint 6 stop condition 8 names it. Fixing the first does not close the criterion. |
| **G8** | **NOT MET** | OIDC done and tested; **SAML 2.0 outstanding**. No partial credit by register rule. |
| **F1** | **partial** | Colour: **22 literals remaining of 332** (310 converted, 7 files). Type: **253 of 254 remaining** — one declaration converted, and the burn-down is gated but not worked. Blocked on the type-ramp weights decision (§3). |
| **F2** | **4 screens of 8** | Four screens still hand-roll state; `errorKind` has two consumers. Three unbuilt states are recorded as deferred. |
| **F4** | **no evidence of any kind** | No test, no 500-entity fixture, no way to build one, no benchmark. Stop condition 4 accepts *either* the full evidence set *or* a narrowed criterion stating the measured ceiling. Neither exists. |
| **F6** | **MET at a stated breadth** | Token layer only. The remaining colour literals sit outside every contrast assertion by construction, so the WCAG claim does not cover rendered screens. Recorded honestly rather than overclaimed — listed here so the limit is not forgotten. |

Met and not at issue: F3, F5, F7, G9 (SCIM), G10 (RBAC), G11 (audit export),
G12 (tested restore).

---

## 2. Open defects with a failing test behind them

These are strict `xfail`s — they turn the suite **red** the moment they are
fixed and the marker is not removed, so the inventory cannot silently overstate
progress.

| where | defect |
|---|---|
| `test_conformance_metric.py` | **A total rename scores 0.000.** A model identical to gold in every entity, type, key and relationship, differing only in vocabulary, is scored as having produced nothing. This is `saas-subscription` in the real run. |
| `test_metric_negative_controls.py` | **F1 is insensitive to deletion on large graphs.** Dropping 2 of 12 entities from the AML model scores entity F1 **0.909**, clearing the 0.80 gate. The same proportional loss on a three-entity graph scores 0.500 and fails, so the gate's strictness depends on graph size and nothing about the threshold says so. |
| `test_artifact_fidelity.py` | Six audit findings still open on the burn-down: **B6, H3, H11, H12, M14, Q4**. Inventory unmoved this sprint (274 passed, 5 skipped). |

---

## 3. Decisions blocking work

Each of these is a judgement call, not a task. Nothing proceeds on them without
an answer.

| decision | blocks | the tension |
|---|---|---|
| **Type-ramp weights** | 253 F1 conversions | The ramp has to be settled before 20 files can be converted mechanically. |
| **Violet palette entry** | the last 16 colour literals | They are a brand colour with no token. Either the palette gains an entry or the criterion narrows. |
| **Playwright, or a narrowed F4** | all of F4 | A 500-table benchmark needs a browser harness; the alternative is stating the measured ceiling. |
| **SAML for G8** | G8 | The only thing between OIDC-done and the criterion. |
| **Severity-ordered repair gate** | nothing; it is a live behaviour question | Ordering on `(errors, warnings)` would accept trading a `DANGLING_REF` for two `MISSING_PK`s — arguably right, since a dangling reference does not build and a missing key does. It also makes the gate **more permissive**, and `test_a_repair_that_trades_one_defect_for_two_is_discarded` exists because the opposite was decided deliberately. Written and backed out; see `synthesis_engine.py`. |
| **Normalising the lint gate** | nothing yet | `lint_delta_per_entity` is now reported; the **gate still uses the raw count**. Switching it is a `THRESHOLD_VERSION` change, and it would move the score in the flattering direction, so it must be argued on its own terms rather than taken while looking at the number. |
| **Scaling `MIN_ENTITY_F1`** | the xfail in §2 | Same shape: fixing deletion-insensitivity means changing a threshold that was fixed before the first provider call. |
| **Embeddings for the matcher** | closing the total-rename defect | The cheap structural alternative was built, measured and rejected. The research path (identifier normalisation, IDF weighting, Hungarian assignment) needs no embeddings and should be tried first. |

---

## 4. Known-wrong things not yet fixed

| issue | why it matters |
|---|---|
| **The conformance harness bypasses the product.** `run_provider_conformance.py:154` calls the gateway directly; `SynthesisEngine.synthesize()` runs four steps and the harness runs one. Relationship normalisation and the Task 7 repair pass — both shipped, both aimed at the axes that failed — have never been evaluated on provider output. | Every D10 number describes a bare model with a good prompt, not this product. |
| **`test_conformance_sends_the_prompt.py` is too narrow.** It asserts an argument at a call site. The defect recurred one level up: the call site itself is not the product's entry point. | The guard written to stop this class of error did not stop the next instance of it. |
| **Our thresholds were never calibrated.** 0.80 / 0.70 / 0.60 against a published state of the art of 0.76 / 0.61 / 0.34 (Chen et al., MODELS 2023). Fixing the threshold before the first call was right; checking whether anything has ever cleared it was never done. | A gate nothing can pass reports failure regardless of quality. |
| **`aml-financial-crime` produces substantive errors.** +1.1 findings per entity on both models — the only graph positive on both — including `CYCLIC_FK` and unmarked `PII_EXPOSURE` on one, `ORPHAN_ENTITY` on the other. | The strongest negative result in the run, and it depends on no contested metric. Unmarked PII in an AML schema is the most expensive thing this product can get wrong. |
| **Three pre-existing lint errors** in `backend/scripts/refresh_dbt_packages.py` (RUF100, unused `noqa` directives). Untouched by this sprint's work. | Small, but they are the only lint errors in the tree. |
| **The repair pass never fires.** Across 48 draws, 28 through the pipeline, **zero** of its six target codes occurred. What the model actually produces — `PII_EXPOSURE` (18), `FAN_OUT_RISK` (15), `ORPHAN_ENTITY` (13), `MISSING_DESCRIPTION` (10) — is excluded from repair, each for a stated reason. | Task 7 shipped as "the best supported intervention available" and addresses failures this model does not make. Its gate and tests are sound; the target set is empty in practice. |
| **`PII_EXPOSURE` is unaddressed and recurring.** 10 of 10 AML draws, 18 of 48 overall. Deliberately excluded from repair because classifying personal data is the user's decision. | The most serious repeatable failure gets no automated help. A **flagging** pass — surface suspected PII for a human to confirm — is a different intervention and is not ruled out by that argument. |
| **`agg_time_column` is discarded on nearly every fact table.** The model points it at an INTEGER surrogate date key (ordinary Kimball); the schema requires a real date/time type. Happens in both domains at both sizes, and the system prompt states the rule explicitly. | The semantic-layer export loses its time dimension. The validator is right *for MetricFlow*; the fix is probably to resolve the time dimension through the date FK rather than demand it on the fact. |
| **The reference-free instrument is severity-blind.** `findings_per_entity` weights a missing description equal to unmarked PII in an AML schema, which inverts the ranking between cells. | The same defect as the raw-count problem in §2, one level up — and built *after* that one was found and written up. |

---

## 5. Never run

- **The local half of D10.** No accuracy evidence of any kind for local
  inference, which is a large part of the air-gapped positioning.
- **Relationship normalisation, measured.** The size × domain run was
  reference-free, so it says nothing about the axis normalisation targets.
  Whether it moves relationship F1 is still unknown.

Two entries were struck on 2026-09-03, recorded rather than deleted:

- ~~The repair pass against a real provider.~~ Run — 28 pipeline draws, and it
  never fired. That is an answer, not a pass; see §4.
- ~~A size-versus-domain experiment.~~ Run — 48 draws. Size drives finding
  *volume*, the domain drives *severity*. `BUILD_EVIDENCE_REVIEW.md` §12.

---

## 6. Unvalidated assumptions

- **H2 is load-bearing and rests on one engineer's reading.** The claim that
  `saas-subscription`'s 0.000 is a good model badly scored — which motivates
  most of the metric work — has never been checked by anyone who did not build
  this. The negative-control suite does **not** test it. If that reading is
  wrong, several conclusions in `BUILD_EVIDENCE_REVIEW.md` go with it.
- **No benchmark exists** for dimensional, Data Vault or OBT model generation;
  no AML data-modelling evidence of any kind; no validated result on grounding
  in a financial reference ontology. Confirmed by three literature reviews.
- The reviews hit their search budget and worked by direct fetch, so non-arXiv
  venues — OAEI in particular — are thinner than ideal.

---

## 7. What to do next, and why in this order

**Revised 2026-09-03, after the size × domain run.** ~~Item 1 was "run the
pipeline into the measured path".~~ Done — and it removed two items below as
well as itself.

1. **Weight the reference-free instrument by severity** (0 calls). Until this
   exists, every number the linter produces ranks a missing description equal
   to unmarked PII, and the cell ordering in `BUILD_EVIDENCE_REVIEW.md` §12
   flips depending on which reading you take. Cheapest fix, and it invalidates
   nothing already measured — the per-draw codes are all preserved, so the
   existing 48 draws can be re-scored offline exactly as the D10 candidates
   were.
2. **Decide what to do about `PII_EXPOSURE`** — the only substantive failure
   that recurs (18 of 48 draws, 10 of 10 on AML) and the one deliberately shut
   out of repair. A *flagging* pass that surfaces suspected PII for a human to
   confirm is a different intervention from a repair pass and is not excluded
   by the argument that classification is the user's decision. **Decision, not
   a task.**
3. **Retarget or retire Task 7's repair pass.** Its six codes have never
   occurred in 48 draws. Options: widen it to codes that do occur (weighing the
   S5-2 invention risk each was excluded for), replace it with deterministic
   repair for `ORPHAN_ENTITY` and `FAN_OUT_RISK`, or keep it as a guard against
   defects a weaker local model might produce — which the local half of D10
   would be the evidence for. Do not simply delete it before that run.
4. **The matcher fix** (identifier normalisation, IDF weighting, Hungarian
   assignment), guarded by the negative controls in §2.
5. **The local half of D10**, without which the criterion cannot close — and
   which is now also the evidence base for item 3.

~~Deterministic cycle and orphan repair.~~ Deprioritised: no `CYCLIC_FK`
occurred in 48 draws, so the cycle half addresses nothing observed. The orphan
half survives — `ORPHAN_ENTITY` appears in 13 draws — and belongs in item 3.

Zero-call items already done: the repair gate's deletion hole, the lint
instrument's per-entity normalisation, the negative-control suite, the repair
telemetry, and `build_graph` extracted so a harness can measure the product.
