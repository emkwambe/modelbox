# Build evidence review — what was proven, what failed, and why

**Date:** 2026-09-03 · **Branch:** `sprint/6-product-experience` ·
**Head at writing:** `6752c1e`

This document exists because the product's central claim — *natural language in,
a correct data model out* — is the one claim the build cannot currently
evidence, while fourteen claims around it are evidenced to an unusually hard
standard. That asymmetry is worth stating plainly rather than leaving implicit
in a failing report.

It is written to be falsifiable. Every number below is traceable to a file in
the tree, and where a conclusion is an opinion rather than a measurement it says
so.

---

## 1. What "a successful build" was defined to mean

The standard was set before the work, and it is stricter than the usual one. From
`CLAUDE.md`:

> No public surface states a capability without a `PL-` id in
> `docs/marketing/PROOF_LOG.md` behind it.
>
> **A Proof Log entry requires a passing test.** Not a plausible argument, not a
> finding that is merely interesting — a named test that passes.

So "successful" was never "it works when I try it". It was: *for every claim,
name the test that would go red if the claim stopped being true.* Three
consequences follow, and all three have bound at some point in this build:

- A capability that works but has no test is **not** claimed. F5 and F7 sat
  finished and unrecorded for a whole sprint because of this.
- A capability that is half-done is **not** claimed at all. G8 was marked `MET`
  in draft with OIDC working and SAML absent; the register's no-partial-credit
  rule forced it back to `NOT MET — OIDC done, SAML outstanding` before it was
  pushed.
- A test that cannot fail for the right reason does not count as evidence
  (stop condition 4). This is the rule that most of §6 turns out to be about.

---

## 2. What was proven

Fourteen Proof Log entries, each behind a named passing test.

| id | claim |
|---|---|
| PL-001 | Certified SQL dialects are certified by two independent grammars |
| PL-002 | Generated DDL executes on a real engine, not just a parser |
| PL-003 | `main` is protected and cannot be merged into on a red build |
| PL-004 | A tagged release publishes an image that pulls and runs clean |
| PL-005 | Artifact generation is deterministic, and that is tested |
| PL-006 | Column identity is stable, and never reused |
| PL-007 | Generated dbt projects run as-is, with nothing added |
| PL-008 | Nothing reaches a model provider without being recorded first |
| PL-009 | An operator can see what left the network, and what we cannot account for |
| PL-010 | There are two independent ways to stop egress, and both are tested |
| PL-011 | Semantic layer exports compile in the tools that consume them |
| PL-012 | Data contracts are wire-stable across a schema change |
| PL-013 | Our data contracts are valid ODCS v3.1.0, and say what they mean |
| PL-014 | Generated test data satisfies the contract generated beside it |

Governance criteria, Sprint 6.5: **G9** (SCIM provisioning and de-provisioning),
**G10** (RBAC enforced at the API), **G11** (audit export), **G12** (a *tested*
restore) all `MET`. **G8** is `NOT MET` — OIDC done, SAML outstanding.

**Read the shape of that list.** Every entry is downstream of the model. Given a
graph, ModelBox provably emits artifacts that the consuming tools accept,
deterministically, with auditable egress. Not one of them says the graph was any
good.

That is not an accident of what got tested. It is what the fidelity harness is
built to do: assert artifacts against the tools that consume them, never against
substrings. It is a strong method and it has no opinion about modelling
quality.

---

## 3. What failed: D10

The criterion, verbatim from `docs/ModelBox_AI_Acceptance_Criteria.md:87`:

> A conformance report exists comparing at least one local and one cloud
> provider, scored by the linter against a threshold fixed **before** the first
> provider call.

Sprint 6 stop condition 8 adds:

> D10 closes on a cloud half **and a local half** scored under
> `THRESHOLD_VERSION` 1.1, with the paradigm-normalisation confound resolved.

Status of each component:

| component | status | evidence |
|---|---|---|
| Threshold fixed before the first call | **met** | `conformance_threshold.py`, commit `b6a3e1a`, into a tree with no code able to call a provider |
| Harness isolation | **met** | `test_conformance_isolation.py` |
| Paradigm-normalisation confound | **resolved, by accident** | the runner bypasses `SynthesisEngine`, so no graph is normalised — see §7, this is not the good news it looks like |
| Cloud half | **ran, FAILED** | 2026-09-03, two models, 12 calls, 12 successes |
| **Local half** | **never run** | `ollama-engine` / `qwen2.5-coder:32b` was never stood up |

So D10 is open for two independent reasons, and it is worth keeping them apart:
the cloud half **ran and failed**, and the local half **has never been
attempted**. Fixing the first does not close the criterion.

---

## 4. The evidence of failure, in full

Twelve real provider calls, six gold graphs against each of two models, all
twelve successful. Thresholds are `MIN_ENTITY_F1` 0.80, `MIN_COLUMN_F1` 0.70,
`MIN_RELATIONSHIP_F1` 0.60, `MAX_LINT_DELTA_PER_GRAPH` 2.0.

### Verdicts

| model | entity F1 | column F1 | relationship F1 | lint Δ/graph | verdict |
|---|---|---|---|---|---|
| `claude-sonnet-4-5-20250929` | 0.434 | 0.119 | 0.260 | **−0.833** | FAIL |
| `claude-sonnet-5` | 0.381 | 0.123 | 0.240 | **+1.500** | FAIL |

Three axes fail badly. **The fourth passes, and it is the one the register
actually names.**

### Per graph — `claude-sonnet-4-5-20250929`

| gold graph | entity | column | relationship | lint Δ | new codes |
|---|---|---|---|---|---|
| `aml-financial-crime` | 0.261 | 0.035 | 0.000 | **+13** | CYCLIC_FK, MISSING_DESCRIPTION, PII_EXPOSURE |
| `banking-datavault` | 0.800 | 0.400 | 0.500 | −5 | NAMING_CONVENTION |
| `ecommerce-orders` | 0.857 | 0.211 | 0.800 | −4 | — |
| `healthcare-ehr` | 0.250 | 0.069 | 0.000 | −2 | — |
| `marketing-attribution` | *excluded* | 0.000 | *excluded* | −2 | — |
| `saas-subscription` | **0.000** | 0.000 | 0.000 | −5 | — |

### Per graph — `claude-sonnet-5`

| gold graph | entity | column | relationship | lint Δ | new codes |
|---|---|---|---|---|---|
| `aml-financial-crime` | 0.250 | 0.064 | 0.000 | **+13** | MISSING_DESCRIPTION, ORPHAN_ENTITY |
| `banking-datavault` | 0.546 | 0.267 | 0.400 | +4 | NAMING_CONVENTION |
| `ecommerce-orders` | 0.857 | 0.316 | 0.800 | −2 | — |
| `healthcare-ehr` | 0.250 | 0.091 | 0.000 | −5 | — |
| `marketing-attribution` | *excluded* | 0.000 | *excluded* | −2 | — |
| `saas-subscription` | **0.000** | 0.000 | 0.000 | +1 | MISSING_PK |

### What jumps out of the per-graph tables

1. **`aml-financial-crime` is the real failure.** Twelve entities, the largest
   graph, and the only one where both models are dramatically *worse* than the
   reference: +13 linter findings each, including `CYCLIC_FK` and
   `PII_EXPOSURE` on one and `ORPHAN_ENTITY` on the other. These are not naming
   disagreements. A cyclic foreign key is wrong on any reading, and unmarked PII
   in an AML schema is the most expensive kind of wrong this product can produce.
2. **Every other graph lints cleaner than the hand-built gold**, mostly by a
   wide margin. Nine of the twelve runs have a negative lint delta.
3. **The failure correlates with size.** The two largest graphs (aml at 12
   entities, banking at 4 hubs/links/sats) carry all the positive lint deltas;
   the three-entity graphs are clean.
4. **`saas-subscription` scores 0.000 across the board while containing a good
   model** — see §6.

---

## 5. What this evidence does and does not support

**Supported.** The models produce *well-formed, governance-clean* schemas for
small-to-medium domains. Nine of twelve runs beat a hand-built reference on the
product's own thirteen-rule linter. That is a real, automated, passing quality
signal, and it is the instrument D10's register row names.

**Supported.** Quality degrades with graph size, and degrades into *substantive*
errors rather than stylistic ones. The AML result is the strongest negative
finding in the whole run and it does not depend on any contested metric.

**Not supported, either way.** Whether the models produce the *right* model for
a described domain. The three F1 axes were intended to answer this and cannot,
for the reasons in §6 and §7.

**Not measured at all.** Local inference. The air-gapped deployment story —
which is a large part of the product's positioning — has no accuracy evidence of
any kind.

---

## 6. Three instrument defects, found in sequence

The F1 numbers have been wrong three times, in three different ways, and each
time the error made the product look worse than it is. This pattern is the main
reason to distrust the remaining number.

**(i) The metric measured vocabulary, not structure.** The first run
(2026-08-13) scored entities by *name equality*. `ecommerce-orders` got 0.857
and `saas-subscription` 0.000 from one model on two near-identical Kimball
tasks. Rewritten in `8c54a71` to match by column-vocabulary overlap. Report
moved to `docs/marketing/superseded/`.

**(ii) The harness did not send the product's system prompt.** The 2026-09-02
run called `structured_completion` without `system_prompt`; the argument
defaults to `None`, so nothing looked wrong. None of the modelling instructions
reached the model — not the Kimball `N:1` rule, not the 3NF bridge-table rule,
not the omission guidance. Relationship F1 came back 0.013 and every entity in
the ecommerce candidate carried an invented `tier`. The report then recorded
`MISSING_SLA` as a *systematic provider behaviour*; it was ours. Fixed, pinned
by `test_conformance_sends_the_prompt.py`, report superseded.

**(iii) The matcher rejected identical tables.** The overlap metric used a
Jaccard ratio, which scored an identical `dim_customer` pair at 0.200 — below
its own 0.50 match floor. Fixed in `55afaaf`; entity F1 moved 0.328 → 0.361 and
0.239 → 0.317 on re-scored candidates.

**And one that is still open.** `saas-subscription` scores 0.000 on both models
while containing this:

```
gold        dim_customer   dim_plan   fact_subscription_monthly
candidate   dim_organisation  dim_tier  fact_subscription_snapshot  + dim_month
```

Three tables, correct types, correct cardinalities, plus a conformed date
dimension and SCD Type 2 columns on both dimensions that the gold graph does not
carry. By any competent reading this is the *better* model. It scores zero
because gold suffixes surrogate keys `_sk` and the candidate chose `_key`,
leaving the column vocabularies disjoint so no pair clears the floor.

**A cheap fix for this was designed, measured, and rejected.** Pairing on
structural signals — `entity_type`, key topology, column data-type profile,
graph degree — solves the stated case (a total rename pairs at 1.000 with
lexical similarity 0.000) and the `entity_type` gate holds the negative guard
cleanly (a Kimball graph scores 0.000 against a 3NF one). But on the real
candidates the best structural match for `dim_customer` is **`dim_month`** at
0.861 — the customer dimension pairing to the calendar — beating the correct
`dim_organisation`. Correct pairings in `ecommerce-orders` score 0.733–0.823,
*below* that wrong 0.861. No floor admits the first and rejects the second,
because every Kimball dimension has the shape of every other one. Structure is
not merely a weak signal here; in the cases that matter it is anti-correlated
with correctness.

Recorded as a strict `xfail` in `test_conformance_metric.py` rather than fixed.
The restraint is deliberate and `conformance_threshold.py` explains why: the
runner now persists candidates, which removed the accidental guarantee that the
floor could not have been fitted to a run. The stated principle is the only
thing holding, and this would have been the fourth change to the metric.

---

## 7. The finding that matters most: the harness does not measure the product

`SynthesisEngine.synthesize()` runs four steps:

1. `structured_completion` with the system prompt
2. `_normalize_relationships` — deterministic Fact↔Dimension cardinality repair
3. `self._graph.validate` — the thirteen-rule linter
4. `_repair_once` — one repair round, kept **only if it strictly improves the
   graph**

`scripts/run_provider_conformance.py:154` calls **step 1 only**, directly against
the gateway.

So every number in §4 describes a bare model given a good prompt. Two
deterministic quality mechanisms that ship in the product were never in the
measured path — and one of them, `_normalize_relationships`, repairs precisely
what relationship F1 measures. Relationship F1 is 0.260 and 0.240 against a 0.60
threshold, with 0.000 on four of the ten scored graphs.

Task 7's repair pass was built in this sprint, has its monotonic-improvement gate
and `test_repair_pass.py` behind it, and **has never been evaluated on a single
provider output.**

This is the same defect as §6(ii) in a larger frame: the harness measured
something adjacent to the product and published it under D10's name. That it
happened again, after a test was written specifically to stop it happening, says
the guard was too narrow — `test_conformance_sends_the_prompt.py` asserts an
argument at a call site, when what needed asserting was that the call site is
the product's entry point.

---

## 8. Hypotheses going forward

Ranked by evidence-per-unit-cost. Each states what it predicts, what it costs,
and what would show it wrong — a hypothesis that cannot be disconfirmed is not
on this list.

### H1 — D10's numbers are low because the pipeline was bypassed

**Predicts:** running the same six prompts through `SynthesisEngine.synthesize()`
raises relationship F1 materially (normalisation targets exactly that axis) and
reduces the AML lint delta (the repair pass targets exactly those codes).
**Cost:** 12 provider calls; no new dependency; the harness change is small.
**Falsified if:** the axes move by less than the run-to-run variance, which the
existing candidates give no way to estimate — so this needs a repeat-run variance
baseline to be interpretable at all.
**Confidence:** high that it moves the number; unknown how far. This is the
single cheapest open experiment and it should be run before any further metric
work.

### H2 — F1-against-one-reference is the wrong instrument for this task

**Predicts:** a metric that admits multiple correct answers scores the same
candidates far higher, and correlates better with expert judgement than the
current one does.
**Cost:** design work, plus whatever the chosen method needs.
**Falsified if:** experts grade the `saas-subscription` candidate as poor — i.e.
if my reading in §6 is simply wrong. **This is the load-bearing assumption of
the whole document and it currently rests on one engineer's opinion.** It should
be tested against people who did not build the thing.
**Confidence:** high, and that is exactly why it needs an outside check.

### H3 — Quality degrades with domain size, and that is the real product limit

**Predicts:** a graph-size sweep shows lint delta rising with entity count, with
substantive codes (`CYCLIC_FK`, `PII_EXPOSURE`, `ORPHAN_ENTITY`) appearing only
above some threshold.
**Cost:** more prompts at varied sizes; the existing linter is the instrument, so
no metric design is needed.
**Falsified if:** the AML result is domain difficulty rather than size — AML is
both the largest graph *and* the most specialised domain, and the current run
cannot separate those. A large-but-simple domain and a small-but-specialised one
would.
**Confidence:** moderate. The signal is clear but confounded.

### H4 — The gold graphs are the wrong reference set

Six graphs, extracted from the Requirements Library, doubling as a curriculum
and marketing asset. They were not built to be an eval set, and the column-name
conventions that sink `saas-subscription` are one author's house style.
**Predicts:** a reference set built for evaluation — multiple accepted answers
per prompt, naming conventions stated in the prompt where they are load-bearing
— produces scores that move with model quality rather than with vocabulary.
**Falsified if:** stating the naming convention in the prompt does not lift
column F1. That is a cheap test and it should be run first.
**Confidence:** moderate-high. Note the constraint in `CLAUDE.md`: gold graphs
must not be edited to satisfy anything. A new eval set is additive, not a
revision.

### H5 — The claim should be narrowed rather than proven

The public surfaces currently say "**validated** models", never "accurate" ones,
and validated is a claim about the artifact pipeline, which is proven. So there
is no unbacked claim today. The honest positioning is a proven pipeline plus a
strong first draft that a modeller edits.
**Falsified if:** H1/H2 close the gap, in which case narrowing was premature.
**Confidence:** this is a fallback, not a plan. It should be the answer only if
H1–H4 fail.

---

## 9. What would actually close D10

1. A **local half**. Nothing above substitutes for it; the criterion names it.
2. A cloud half that passes its threshold — or a **narrowed criterion** stating
   the measured ceiling, which stop condition 4 already accepts as a legitimate
   outcome for F4 and would accept here.
3. Either way, the run must go through `SynthesisEngine.synthesize()`, or the
   report must say in the file that it does not measure the product.

---

## 10. Open decisions this document does not make

- **Type-ramp weights** — blocks 254 F1 conversions.
- **Violet palette entry** — blocks the last 16 colour literals.
- **Playwright** for the F4 500-table benchmark, or a narrowed criterion.
- **SAML** for G8.
- Whether to spend on embeddings for the matcher, now that the cheap structural
  alternative has been measured and rejected.

---

## Appendix — provenance

Both reports in `docs/marketing/` are **re-scored offline** from candidates
preserved during the run; they carry a `rescored` block naming the reason, and
`run_started_at` holds the original call time rather than the re-score time.
`test_rescore_is_labelled.py` asserts both properties, and that the shipped
reports report `passed: false`.

Superseded evidence is in `docs/marketing/superseded/` with a README explaining
why each file must not be read as current. Neither is cited above except as the
history in §6.
