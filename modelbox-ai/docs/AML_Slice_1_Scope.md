# AML slice 1 — scope

*Written 2026-08-29 from `ModelBox_AML_Analytics_Expansion_Considerations.docx`
and `02 After the AML expansion.md`, against the findings in
`AML_IR_Gap_Analysis.md`.*

**This is a scope, not a decision.** Nothing here is approved and no AML code
exists. It says what the first slice should be if the expansion proceeds, what it
would cost, and — the part worth reading first — what it deliberately does not
attempt.

---

## The framing

The expansion document's phase 1 is *"canonical AML model — establish domain
truth"*, exiting when "a complete customer→transaction→alert→case model executes
and validates".

The important property of that phase, which neither document states and which
changes the whole plan: **phase 1 is data, not code.** Party, account,
transaction, counterparty, device and KYC are ordinary relational modelling. The
IR expresses them today, unchanged. The linter grades them today. The fidelity
harness proves their exports execute today.

Everything expensive in the AML programme lives in phases 3–6 — the feature
registry, versioned detection rules, the evidence chain, the tuning lab — and all
of it is blocked on the same gap: the IR describes **schemas**, and those phases
need **definitions** (a feature with a lookback window and a version) and
**derivations** (this hit came from that rule version over that dataset
version). That is a second object family, not more fields.

So the first slice is the part with a known cost, and it is worth doing on its
own even if the rest never happens.

### Correcting my own earlier recommendation

`AML_IR_Gap_Analysis.md` recommended making the pack interface **phase 0**. On
re-reading the sequence, that is wrong in a specific way: a seam designed against
one case is a guess, and phase 1 does not need one *because it is data*. Adding a
reference model to the template library changes no core semantics and creates
nothing to isolate.

The seam becomes unavoidable at **phase 3**, when definition and derivation
objects appear and would otherwise land in `app/schemas/data_model.py` — which is
the coupling risk §13 names for itself. So: build slice 1 with no seam, and
require the seam to be designed **before** any phase-3 work, with two concrete
cases in hand rather than one imagined.

---

## The slice

**One AML reference model, shipped the way every other reference model ships.**

`frontend/src/lib/templates.ts` is the single source of truth for the
Requirements Library; `_extract_gold_graphs.mjs` mirrors it mechanically into
`backend/tests/fixtures/gold/`; `test_gold_mirror_matches_templates_ts`
re-extracts and diffs so the mirror cannot fall behind; and the fidelity harness
is parametrised over those graphs, asserting every emitter against every one of
them.

Adding an AML template therefore buys phase 1's exit condition using machinery
that already exists:

1. **It appears in the product.** Users see an AML reference architecture in the
   Requirements Library beside the SaaS, e-commerce, banking, healthcare and
   marketing models. That is the demo, with no demo built.
2. **Its exports are proven to execute**, not asserted to look right — DDL on
   DuckDB, `dbt build`, `protoc`, `fastavro`, `sqlfluff`, ODCS v3.1.0.
3. **It is graded by the shipped linter**, so a Trainer lab over it stays in
   lock-step with the appliance by construction.

Concretely, the slice is:

- **One canonical AML model** covering party, KYC profile, account, transaction,
  counterparty, device/identifier, and the analytical outputs the domain needs
  — detection hit, alert, investigation, disposition — as entities with declared
  grain, PII classification, and quality rules where the domain genuinely states
  them.
- **A second paradigm from the same domain.** The banking template is already
  Data Vault; the AML one should be Kimball, so the pair demonstrates the
  multi-paradigm claim on one subject rather than across unrelated subjects.
- **A Trainer lab** over the model, teaching the AML-specific reading of codes
  the linter already emits — a fact table with no grain is a different mistake
  when the fact is a transaction.
- **Documentation** of what each entity means, in the vocabulary a bank's data
  architect uses.

### Exit conditions

Named, and every one is an existing gate rather than a new claim:

| Condition | How it is checked |
| :-- | :-- |
| The model is in the library and the mirror matches | `test_gold_mirror_matches_templates_ts` |
| Every emitter produces artifacts that execute for it | `test_artifact_fidelity.py`, parametrised over the new graph |
| It is lint-clean, deliberately | `GraphEngine.validate` returns no issues; asserted |
| Its lab grades against the shipped linter | `test_trainer_labs.py` set-equality |
| Nothing in the core changed | the diff touches no file under `app/` |

That last row is the one to hold the slice to. **If slice 1 requires a change to
`app/`, the slice has been scoped wrong** — it means an AML concept has reached
the horizontal core, and the seam conversation must happen first.

### One thing will move, and must move loudly

The fidelity harness is parametrised over the gold graphs. A sixth graph means
every emitter is asserted against a shape none of them has seen, and **new
xfails are a likely and legitimate outcome** — an AML transaction table with two
foreign keys to the same party entity is precisely the role-playing case carried
open since Sprint 3.

That is a feature, not a risk to hide: it is standard 11 working as intended, and
finding it on a reference model is far cheaper than finding it in a customer's.
But the inventory must be expected to move at that commit, and the progress note
must say so before the run rather than after.

---

## What this slice does not do

Stated because the expansion document's §10 "minimum credible release" is
*larger than this*, and pretending otherwise would be the overclaim the whole
programme guards against.

§10 asks additionally for a synthetic dataset with embedded typologies, five
typology scenarios with ground truth, a reusable feature layer, five transparent
detections, a network view, an alert/investigation view with provenance, and a
threshold back-test report. **Every one of those needs phases 2–6**, and phases
3–6 need the IR work above. They are a second release, and calling this one
"minimum credible" would misdescribe it.

What this slice honestly is: **the domain model, proven deployable.** That is
phase 1, and it is the only phase whose cost is currently knowable.

## What must not be built, at any point

From §7, unchanged and worth restating where the work happens: no production
transaction-processing platform, no sanctions/PEP screening, no SAR filing
gateway, no enterprise case-management suite, no autonomous compliance
decisions, no claim that generated detections satisfy a regulatory obligation, no
black-box classifier presented as authoritative, and no requirement to ingest
real customer PII.

To which the market research adds one more: **do not quote the transaction-
monitoring market figure beside this product.** ModelBox does not monitor
transactions. The wedge is design and validation *before* production data
exists — a claim the vendors cannot make, unlike synthetic data, back-testing and
reference models, which they already ship.

---

## Decisions that belong to a person

1. **Is AML the direction at all?** Everything above is cheap, but cheap work in
   the wrong direction is still the wrong direction. Nothing in the analysis
   answers whether this is the vertical to spend a quarter on.
2. **FIBO alignment.** Naming the entities to the Financial Industry Business
   Ontology costs little at slice-1 scale and converts "we invented an AML
   schema" into "we generate a FIBO-aligned one". It is much more expensive to
   retrofit later. Recommended as a naming reference, not an OWL dependency.
3. **Whether an AML template belongs in the shipped library.** It is the cheapest
   path to the exit conditions, but it also puts AML in front of every user of
   the product, which is a positioning decision rather than an engineering one.
   The alternative — fixtures outside the library — costs a parallel extraction
   path and forfeits most of the free verification.

## Cost

Slice 1 is days, not weeks: one template, one lab, documentation, and whatever
the fidelity harness turns up on a new shape. It requires no new dependency, no
migration, no IR change, and no provider call.

The honest caveat is that it proves the *modelling* half of the AML story and
none of the analytical half. A reviewer shown this slice sees a well-built domain
model with executable exports. They do not see a detection, a feature, or a
tuned threshold — and the expansion document is right that those are what make
the case. This slice earns the right to build them; it does not substitute for
them.
