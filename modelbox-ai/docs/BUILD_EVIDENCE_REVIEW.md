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
   wide margin. **Eight** of the twelve runs have a negative lint delta —
   five of six for `claude-sonnet-4-5-20250929`, but only three of six for
   `claude-sonnet-5`, which is an even split rather than a clean win.
3. **The apparent correlation with size is partly an artefact of the
   instrument, and the raw counts overstate it.** `lint_delta` is a *raw count
   difference*, so a 12-entity graph has four times the opportunity to generate
   findings that a 3-entity graph has. Normalised per candidate entity the
   picture is weaker and the ranking moves:

   | graph | cand. entities | sonnet-4-5 Δ/entity | sonnet-5 Δ/entity |
   |---|---|---|---|
   | `aml-financial-crime` | 11 / 12 | **+1.18** | **+1.08** |
   | `banking-datavault` | 6 / 7 | −0.83 | **+0.57** |
   | `ecommerce-orders` | 4 / 4 | −1.00 | −0.50 |
   | `healthcare-ehr` | 4 / 4 | −0.50 | −1.25 |
   | `marketing-attribution` | 1 / 1 | −2.00 | −2.00 |
   | `saas-subscription` | 4 / 5 | −1.25 | **+0.20** |

   What survives: **AML is the only graph positive on both models**, at ~+1.1
   findings per entity against a range of −0.5 to −2.0 everywhere else. That is
   still the strongest negative result in the run.

   What does not survive: the "+13 versus everything else" framing, which is
   inflated by size; the claim that the two largest graphs carry all the
   positive deltas, since `banking-datavault` is negative for one model and
   positive for the other; and any clean monotone relation with entity count,
   which six graphs with one dominant outlier cannot support. Note also that
   `healthcare-ehr` and `banking-datavault` swap order under normalisation.

   **This is a defect in the instrument, not only in the reading.** A raw
   finding count also rewards omission — a model that emits fewer entities emits
   fewer findings — which is the same hole found in the repair gate at §11.6.
   Both should be normalised per entity before either number is used again.
4. **`saas-subscription` scores 0.000 across the board while containing a good
   model** — see §6.

---

## 5. What this evidence does and does not support

**Supported, with the caveat in §4.3.** The models produce *well-formed,
governance-clean* schemas for small-to-medium domains. Eight of twelve runs beat
a hand-built reference on the product's own thirteen-rule linter, and the mean
lint delta clears its threshold for both models — a real, automated, passing
signal, and the instrument D10's register row names. Two qualifications belong
with it: the split is five of six for one model and three of six for the other,
which is a weaker result than a pooled count suggests; and the underlying count
is not normalised per entity, so it rewards a model that emits fewer tables.

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

## 11. What the research changed (2026-09-03)

Three literature reviews were run against the open questions above. They
corrected §8 in four places and produced one verified defect in shipping code.
Sources are in the thread reports; the load-bearing ones are named inline.

### 11.1 Our thresholds fail the published state of the art

Chen et al., *Automated Domain Modeling with Large Language Models*, MODELS
2023, evaluates GPT-4 against expert reference models on exactly our three-level
decomposition: **classes F1 0.76, attributes 0.61, relationships 0.34.** Our
gates are 0.80 / 0.70 / 0.60 — the best published numbers in the field would
fail two of the three.

`THRESHOLD_VERSION` was fixed before the first provider call, which is the right
discipline and is not in question. What it was never checked against is whether
any system has ever cleared it. Two further points: our result *ordering*
reproduces theirs (relationships worst), which is weak evidence the metric
detects something real; and their qualitative finding is that LLM models
"rarely follow modeling best practices" — which is what our linter measures and
our F1 axes cannot see.

### 11.2 All three metric fixes were validated on false negatives only

This is the finding that most changes how the next change should be made.

Each of the three fixes in §6 was diagnosed from a **good model scoring low**.
Not one was validated against a **known-bad model that must still score low**.
A change set examined only where the score was too low raises the score by
construction — regressional Goodhart in the sense of Manheim & Garrabrant. The
monotonic rise across three fixes is therefore not evidence of three good fixes;
it is the expected signature of that selection process, and there is no reason
to expect a fourth to behave differently.

The established guardrail is contrast sets (Gardner et al., Findings of EMNLP
2020 — hand-authored minimal perturbations, model accuracy dropped up to 25
points) and CheckList's invariance/directional tests (Ribeiro et al., ACL 2020
best paper), which assert a *relation* rather than a gold answer and so cannot
be satisfied by editing the reference. Note the boundary: author-written
perturbations are sound; **model-in-the-loop adversarial filtering is not**
(Bowman & Dahl, NAACL 2021).

### 11.3 The structural-matching failure is a published, replicated result

§6's rejected structural matcher was not an implementation error. Valentine
(Koutras et al., ICDE 2021), benchmarking Cupid, COMA and Similarity Flooding,
concludes that "in the absence of good attribute names, the rest of the schema
information … do not actually give any useful insights." Rahm & Bernstein said
it in 2001; SemStruct (2026) finds structural nodes act as "topological conduits
rather than semantic entities."

The sharper diagnosis: **we built Similarity Flooding's propagation without its
seed.** Every established system applies structure on top of leaf-level
*linguistic* scores; we removed the linguistic layer and measured the remainder.

And the failure was **half greedy-argmax, not all structure** — a correction to
§6, which attributed it entirely to structure. Under global assignment,
`dim_plan`↔`dim_tier` is an overwhelming pair (`plan_name`↔`tier_name`,
`list_price`↔`base_price`), so `dim_tier` is claimed by a better bidder and
`dim_customer` is forced onto `dim_organisation`. The recommended path needs no
embeddings: identifier normalisation with an abbreviation dictionary (`mrr` →
monthly recurring revenue, which no general embedding model will get — see the
identifier-splitting literature, TRIS, WCRE 2012), **IDF weighting** so that
`is_current` / `effective_from` / `_key` contribute ~0, then Hungarian
assignment at column and table level, gated by `entity_type`.

Two hazards recorded for whoever builds it: `scipy.linear_sum_assignment` breaks
ties arbitrarily and the resolution can change between versions, which is a
determinism problem for us specifically; and embeddings, if added later, score
*relatedness* rather than *equivalence*, which directly attacks the "must be
able to say NO" property.

### 11.4 H3 is probably wrong — it is domain, not size

The size cliff in the adjacent literature sits at 1,000+ columns, not 12
entities; at BIRD scale irrelevant columns are nearly free (Maamari et al.,
*The Death of Schema Linking?*). Meanwhile the domain effect is large and
measured with size held roughly constant — Spider-DK (EMNLP 2021) costs
**20.2 to 32.4 points**, and the *strongest* model drops the most, because
pretrained models lean hardest on surface lexical cues that AML jargon denies.

The error shape corroborates it. BizBench (ACL 2024): of GPT-4's 44 errors,
**zero were extraction or syntax errors; 37 came from limits in business and
financial knowledge.** FinanceBench: closed-book 9% → oracle context 85%.
LegalBench: rule *recall* 59.2% vs rule *application* 82.2% — a ~31-point spread
saying the deficit is stored knowledge, not reasoning. BEAVER scores enterprise
schemas at 10.8%, and **30.1% even with oracle schema hints**: two-thirds of the
error survives free schema linking.

So H3 should be re-stated: the AML result is most likely **domain
specialisation**, and the experiment that separates it is a 2×2 — a 12-entity
commodity domain and a 4-entity AML domain. If the small AML model is already
dirty, size is exonerated.

One caveat that cuts the other way: association-layer decomposition is reported
to lift association F1 **0.119 → 0.219** (arXiv 2410.09854), and if the damage
is concentrated in the relationship layer regardless of domain, then AML is
merely large enough for that layer to fail visibly. The two predictions are
separable in the same run if it is instrumented by layer.

### 11.5 LLM-as-judge is disqualified, not merely risky

On JudgeBench (ICLR 2025), where one answer is objectively correct, prompted
GPT-4o scores **50.86 against a 50% random baseline**; one commercial evaluator
scored below chance. In software engineering, judges systematically misclassify
correct implementations as non-compliant and **get worse with more detailed
rubrics**. Even at temperature 0, 1–2% of borderline cases are non-reproducible,
which alone fails our determinism requirement. Multi-reference sets also do not
help (Freitag et al., EMNLP 2020): k references in one house style share one
vocabulary, which is precisely our failure mode.

### 11.6 A verified defect: the repair gate can be won by deleting an entity

`_repair_once` accepts a repaired graph when `len(after) < len(before)`, a raw
count of repairable issues (`synthesis_engine.py:425`). Nothing asserts the
entity or column set survived. **Dropping an entity that carries a repairable
issue reduces the count and wins the gate.**

The gate's docstring is right that an ungated repair pass is a second chance to
make the model worse; the count is simply the wrong quantity to gate on. This
costs zero provider calls to fix and is a **prerequisite** for §11.7 — without
it a repair "win" and a deleted entity are indistinguishable in the results.

### 11.6b Done, and what doing it found

Items 1–3 of §11.7 are implemented.

- **The lint instrument** now reports `lint_delta_per_entity` and
  `candidate_entity_count` beside the raw delta. The **gate still uses the raw
  count**, deliberately: `MAX_LINT_DELTA_PER_GRAPH` was fixed before the first
  provider call, and switching it while looking at the score it would move — in
  the flattering direction, since normalisation shrinks the AML penalty most —
  would be a fourth metric change of exactly the kind §11.2 warns about. It
  changes no verdict on the current candidates either way.
- **The repair gate** now refuses a repaired graph that has *lost* any entity or
  column. Additions are still accepted, since `MISSING_PK` is fixed by adding a
  key. Three tests, two of which go red when the check is removed.
- **The negative-control suite** is `tests/test_metric_negative_controls.py`:
  26 tests over five mutations and two positive controls, all assertions
  relational rather than absolute.

**A severity-ordered repair gate was written and backed out.** Ordering on
`(errors, warnings)` rather than a plain count would accept trading a
`DANGLING_REF` for two `MISSING_PK`s — arguably right, since a dangling
reference does not build and a missing key does. But it makes the gate *more
permissive*, `test_a_repair_that_trades_one_defect_for_two_is_discarded` exists
because someone decided the opposite deliberately, and loosening an acceptance
test as a side effect of closing an unrelated hole in it is the move this
document keeps arguing against. **Open decision.**

**Two things the suite caught immediately.**

First, a gap in the suite itself: a mutation reverting the matcher to name
equality left it entirely green, because the positive control renamed only
*columns*. A negative-control suite that cannot detect the defect the metric was
built to fix is a test passing for the wrong reason. `rename_every_table` was
added; it now catches that mutation on all four graphs, and the suite also
catches a floor dropped to 0.0.

Second, and open: **F1 is insensitive to deletion on large graphs.** Dropping 2
of 12 entities from the AML model scores entity F1 **0.909**, clearing the 0.80
gate — a model missing a sixth of itself passes. The same proportional loss on a
three-entity graph scores 0.500 and fails. The gate's real strictness therefore
depends on graph size, which nothing about the threshold says, and it is the
exact counterpart of the lint instrument's raw-count problem: both grow more
forgiving as the model grows. Pinned as a strict `xfail` rather than fixed,
because changing `MIN_ENTITY_F1` or making it scale is a threshold change and
this suite exists so the next one is argued rather than fitted.

### 11.7 Revised order of work

Superseding §8's ranking. All three reviews converge on the same first
experiment, and it is H1.

1. **Harden the monotonic gate** (0 calls). Lexicographic on severity, plus a
   non-regression check on the entity and column sets. Prerequisite for 3.
2. **Negative-control mutant suite** (0 calls, ~1 day). Programmatically damage
   our own reference models — drop the fact grain column, introduce a cyclic FK,
   merge two dimensions, denormalise a fact, strip PII markings — plus the
   `_sk`→`_key` rename as the *positive* control that must score high. It
   retroactively tests all three prior fixes. **No further metric change ships
   before this exists**, including the matcher fix, which will also raise the
   score.
3. **Run the pipeline into the measured path**, as a 2×2 over size and domain,
   instrumented by layer (~40 calls). This is H1 plus the §11.4 experiment in
   one run, and it produces numbers nobody currently has.
4. **Deterministic cycle and orphan repair** (0 calls). Models cannot perceive
   the property: cycle detection on hard graphs runs at 53.25%, near chance.
   This belongs in an algorithm, not a prompt. Restrict to unambiguous cases —
   minimum feedback arc set is NP-hard.
5. **The matcher fix** of §11.3, guarded by 2.
6. **Promote the linter to a scored, reference-free conformance gate**, and
   demote single-reference F1 to a version-over-version regression tracker —
   which is the only thing gold-standard comparison is valid for (it evaluates
   the *learner*, not the artefact).

Domain knowledge for AML is a live option but conditional: KaggleDBQA ablates it
directly and finds column descriptions **alone** gave 17.55% against a 17.96%
baseline — inert unless it changes how the model is *asked to use* them. A
glossary pasted into a prompt is not the intervention. Fine-tuning is out of
scope: FinMA-30B beats GPT-4 on financial sentiment but collapses on FinQA
(0.06 vs 0.63).

### 11.8 What the research could not tell us

- **No benchmark exists** for dimensional, Data Vault or OBT model generation.
  A 2026 review of 64 studies names standardised benchmarks as its primary
  recommendation. We are not missing one; it does not exist.
- **No AML data-modelling evidence of any kind.** The LLM+AML literature is
  entirely transaction detection, alert triage and SAR drafting.
- **No validated result** on whether grounding in a financial reference ontology
  (FIBO, BIAN) improves a generated model.
- **No accuracy-versus-entity-count curve** anywhere; the size axis is always
  confounded with dirtiness, dialect and domain. Item 3 above would produce one.
- Both threads that searched hit their WebSearch budget and worked by direct
  fetch, so non-arXiv venues — and OAEI specifically — are thinner than ideal.

**H2 remains unvalidated and load-bearing.** Nothing above tests whether the
`saas-subscription` candidate is actually a good model; that still rests on one
engineer's reading, and the negative-control suite does not check it either.

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
