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

---

## 5. Never run

- **The local half of D10.** No accuracy evidence of any kind for local
  inference, which is a large part of the air-gapped positioning.
- **The repair pass against a real provider.** Built this sprint, gated, tested
  in isolation, never exercised on provider output.
- **A size-versus-domain experiment.** The AML failure is confounded: it is both
  the largest graph and the most specialised domain, and nothing run so far
  separates those.

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

1. **Run the pipeline into the measured path**, as a 2×2 over size and domain,
   instrumented by layer (~40 provider calls). It fixes §4's first entry, gives
   the repair pass its first evidence, and separates the two live explanations
   for AML in the same run — the domain-modelling literature predicts damage
   concentrated in the relationship layer regardless of domain; the
   finance/legal benchmarks predict a small AML model is *already* dirty. They
   disagree, and they point at different sprints.
2. **Deterministic cycle and orphan repair** (0 calls). Models cannot perceive
   the property — cycle detection on hard graphs runs near chance — so it
   belongs in an algorithm. Restrict to unambiguous cases; minimum feedback arc
   set is NP-hard.
3. **The matcher fix** (identifier normalisation, IDF weighting, Hungarian
   assignment), now that §2's negative controls exist to guard it.
4. **The local half of D10**, without which the criterion cannot close.

Zero-call items already done this sprint: the repair gate's deletion hole, the
lint instrument's per-entity normalisation, and the negative-control suite
itself.
