# ModelBox AI — Enhancement Blueprint

**Version:** 1.0
**Date:** 10 August 2026
**Author:** Architecture / PM
**Inputs:** `docs/PROJECT_STATE_REPORT.md` (audit, branch `audit/state-report`), `docs/ModelBox_AI_Brand_Design_System.md`, `docs/ModelBox_AI_Marketing_Content_Plan.md`, repo at `3050058`
**Status:** Proposed. Section 3 requires founder sign-off before Sprint 2.

---

## 1. The one-sentence problem

ModelBox AI has a good spine and a credibility deficit.

The audit is unambiguous on both halves. The layering is clean, the IR is genuinely
universal, the migration chain is linear, 143 tests pass, and the Trainer has zero
drift against the linter — `test_trainer_labs.py` asserting set equality between lab
flaws and linter output is the strongest engineering artifact in the repo. That is a
real foundation and it should not be rebuilt.

Against that: a documented, PRD-committed exporter produces output that dbt rejects on
5 of 5 gold graphs; three documents assert a CI pipeline that does not exist; a
governance flag advertised in the README is an identity function with no audit record.
Every one of those defects reached `main` through a green local test run, because the
tests assert on strings and no artifact was ever handed to its own parser.

The strategic reading: **the product's problem is not capability, it is verifiability.**
Everything in this blueprint is organised around closing the gap between what ModelBox
claims and what can be demonstrated — because that gap is simultaneously the engineering
debt, the enterprise sales blocker, and the reason the landing page cannot yet be
written honestly.

---

## 2. The organising mechanism: the audit becomes the test suite

The single highest-leverage change is not any individual fix. It is converting the
audit's findings into executable, permanently-enforced tests **before** fixing them.

Concretely, in Sprint 1 every §4 fidelity failure becomes an `xfail`-marked test in a
new `backend/tests/test_artifact_fidelity.py`, parameterised across the five gold
graphs, invoking each artifact's real toolchain:

Delivered in Sprint 1 as `backend/tests/test_artifact_fidelity.py`. Actual state
after implementation — amended against the estimates this section was drafted
with, because the harness found more than the audit did:

| Artifact | Verification | Sprint 1 state |
|---|---|---|
| DDL (per dialect) | `sqlglot` re-parse, `sqlfluff` dialect grammar, **real DuckDB execution** | re-parse 35/35 pass; grammar 20/20 certified pass, 15 `@preview` xfail; DuckDB executes 5/5 |
| dbt | `dbt parse` in a generated project | 5/5 parse; xfail H9 (not self-contained), M11 (deprecations), M7 (packages.yml) |
| MetricFlow | `dbt parse` with semantic models | 24 xfail (B1) |
| Cube.js | executed in a `vm` sandbox with Cube's globals shimmed | 5/5 valid; 6 xfail (M3) |
| LookML | none exists offline — **Preview**, structural assertions only | 3 xfail, `@preview`, excluded from burn-down |
| ODCS | ODCS **v3.1.0** fundamentals (spec confirmed via context7) | 15 xfail (H2, H2-ext, H2/H4) |
| Avro | `fastavro.parse_schema` | 15/15 pass — locked in |
| Protobuf | `protoc` compile + tag-stability probe | 5/5 compile; 10 xfail (H6) |
| Seed | generated rows validated against the model's own contract | 2 xfail (H1) |

**Totals: 107 pass, 4 skip, 94 xfail — of which 76 are the Sprint 3 burn-down
and 18 are `@preview`.** Run the burn-down with `pytest -m "not preview"`.

Two properties, both amendments made during implementation and adopted:

- **`strict=True` from creation** (supersedes §7.3's original "strict on flip").
  A fix therefore turns CI red via XPASS until the marker is removed, closing
  the window in which a repaired defect still reads as debt.
- **`MODELBOX_FIDELITY_STRICT=1`**, set by the CI tools job. Tests skip when a
  toolchain is absent so the module is usable in the app venv; with the flag
  set, a missing toolchain is a hard failure. A gate that silently skips is
  worse than no gate, because it reports green having verified nothing.

This inverts the usual dynamic. Today a defect is invisible until a customer finds it.
After Sprint 1, every known defect has a named, failing test with a finding ID, and
**sprint completion is defined as xfails flipping to pass** — a burn-down anyone can
read from CI output rather than from a status document. It also makes regression
structurally impossible: once `strict=True` xfail flips green, it can never silently
revert.

This costs roughly two extra days in Sprint 1 and removes the need for status reporting
across the remaining sprints. Claude Code's suggested sequence placed the harness in
Sprint 3, alongside the fixes. Moving it to Sprint 1 is the one substantive change I am
making to that sequence, and the reason is that CI landing without artifact gates would
lock in current behaviour as the baseline — the pipeline would go green over a
non-functional MetricFlow exporter and certify it.

---

## 3. Decisions required — recommendations against the audit's eight open questions

These are architect recommendations. Founder holds the veto on all eight; items marked
**blocking** must be settled before the named sprint starts.

### Q1 — Air-gapped runtime: ship vLLM or repoint to Ollama? **(blocking Sprint 5)**

**Recommendation: repoint `airgapped_overrides` at `local_ollama`; demote vLLM to a
documented BYO endpoint.**

The air-gapped route's primary is `airgapped_vllm` and the compose file has no such
service, so the flagship regulated-industry path currently resolves to nothing. Ollama
is already in the compose file and runs on laptop-class hardware, which is what a
single-node appliance implies. Shipping a vLLM container means owning GPU driver
support in customer environments — a support burden disproportionate to a pre-revenue
product. vLLM remains fully supported as a customer-supplied endpoint, documented, with
a conformance report (§4) proving it works.

### Q2 — What is "masking" supposed to mean? **(blocking Sprint 1)**

**Recommendation: retire the masking claim entirely. Replace the governance story with
air-gap + egress ledger + BYO endpoint.**

This is the most consequential call in the document, so the reasoning in full.

Masking schema identifiers is theatre when the same request carries the source PRD
verbatim. If `customer_churn_risk_score` is tokenised to `col_a7f3` but the requirements
document accompanying it says "we need to track each customer's churn risk score," no
confidentiality has been gained — the semantics leaked in the payload the masking did
not touch. Reversible tokenisation is a materially larger build than one-way redaction
(the docstring says one thing, the README another), and at the end of it the product
would be defending a control that does not hold.

The three controls that *do* hold are the ones already half-built: air-gapped mode where
nothing leaves at all, per-task egress class so residency is enforced rather than
assumed, and an append-only ledger recording exactly what left, when, to whom. That is a
stronger and more honest procurement answer than masking, and it is what regulated
buyers actually ask for. Sprint 1 makes the flag honest — fail startup if
`MASK_METADATA_IN_PROMPTS=true` with no implementation, and delete the claim from
`README.md:106` and `model_router.yaml:20-21`. Sprint 5 builds the ledger.

If masking must survive for a specific buyer conversation, scope it to one-way redaction
of identifiers *and* refuse to send free-text requirements in the same request — but
that is a different product behaviour and should be specified as such.

### Q3 — Does `POST /trainer/grade` have real users? **(blocking Sprint 8)**

**Recommendation: assume none; delete the 3-invariant rubric and grade everything
through the 12-code linter.** The product is pre-launch with no external instructors.
If that is wrong, this becomes a migration rather than a deletion — founder to confirm.

### Q4 — Which dialects do we certify? **(blocking Sprint 3)**

**Recommendation: certify `postgres`, `snowflake`, `redshift`, `duckdb`. Label
`bigquery`, `databricks`, `clickhouse` as "Preview — not deployment-verified" in both UI
and docs.**

This converts H3 from three-to-four days of per-dialect constraint work into roughly a
day of labelling, and it is more honest than the status quo, which advertises seven
dialects and deploys on four. Promote a dialect out of preview when a customer needs it,
with the fidelity harness proving deployability as the gate. Advertising less and
delivering all of it is the correct posture for a product selling contract reliability.

**Amended in Sprint 1 — the certification boundary is now evidence, not judgement.**
`sqlfluff`, which carries real per-dialect grammars, independently reproduces exactly
this split: `postgres`, `snowflake`, `redshift` and `duckdb` parse with zero unparsable
segments; `bigquery`, `databricks` and `clickhouse` each reject the emitted `CREATE
TABLE` constraint body. DuckDB additionally *executes* the emitted DDL on all five gold
graphs, so at least one certified dialect is proven deployable rather than merely
parseable.

**LookML also drops to Preview.** It is proprietary, no offline parser exists — so it is
permanently unverifiable in the harness — and the install base does not justify Sprint 3
effort. The emitter stays behind a Preview label rather than being deleted, and M3
narrows to Cube only. The Sprint 3 slot this vacates goes to running **SafeSQL Pro over
ModelBox's own emitted DDL and dbt models** as a harness step: a real security gate on
generated SQL, dogfooding a sibling product, and a Proof Log claim no competitor can
make. To be scoped in Sprint 3 planning.

### Q5 — Should quality rules emit `CHECK` constraints in DDL? **(non-blocking)**

**Recommendation: no by default; add an opt-in export flag, defaulted off.** Changing
the failure mode from "test fails in CI" to "insert rejected at runtime" is a
customer-hostile default. Offer it, do not impose it.

### Q6 — Is `ordinal_position` the stable column identity? **(blocking Sprint 2)**

**Recommendation: no. Introduce an explicit, persisted `stable_id` on `ColumnSchema`,
allocated once at first persist and never reused.**

`ordinal_position` is a display concern and `graph_repository.py:99-101` already falls
back to list position when it is null, so it cannot carry identity. An explicit stable
identity is worth more than the Protobuf fix that motivates it:

- **Protobuf tags (H6)** become wire-stable by construction.
- **The diff engine (M2)** gains the ability to distinguish a *rename* from a
  *drop-plus-add* — currently impossible, and the single most common false-positive
  breaking change in schema diffing.
- **Column-level lineage** becomes expressible later without another migration.

One field, one migration, three problems. This is the highest-value addition in the
blueprint that the audit did not itself propose.

### Q7 — Are the RealityDB / SafeSQL seams live commitments? **(non-blocking)**

**Recommendation: mark as removed scope in `PRD_TRD_v2.md:59, 208-215`.** Zero code
references. Founder owns both products, so this may be a deliberate future seam — if so,
say so in the PRD with a target release rather than leaving it as an unqualified
commitment.

### Q8 — One persistence path or two? **(blocking Sprint 2)**

**Recommendation: consolidate first, before H4 touches both.** `GraphRepository._persist`
and `SynthesisEngine._persist_graph` are duplicated column-by-column and the code itself
acknowledges it. Roughly a day, and it removes a class of drift that H4 would otherwise
double.

---

## 4. Architectural positions carried forward

Beyond the audit's findings, four positions shape the sprints.

**Determinism is the product thesis, and the paradigm translator violates it.**
The audit confirmed that `ParadigmTranslator.transform` routes a specifiable
transformation — hub/link/satellite decomposition, fact/dimension identification —
through the LLM. That costs reproducibility, provenance, air-gapped quality, and
testability, on the feature that most differentiates ModelBox from a schema generator.
This is not a defect and does not belong in the correctness sprints; it is a product
investment, scheduled as a decision gate after Sprint 5 (§5). The recommended first
increment is Data Vault only, because hub/link/satellite decomposition is the most
mechanical of the three paradigms and produces the clearest provenance trace.

**"LLM-agnostic" is currently an architectural claim with nothing measuring it.**
A provider conformance harness — the five gold graphs synthesised through each
configured provider, scored by the existing 12-code linter, emitted as a report — makes
the claim demonstrable, gives regulated buyers a defensible answer about local-model
quality, and reuses machinery that already exists. Scheduled in Sprint 5 alongside the
ledger, since both serve the same buyer.

**The appliance, not Vercel, is the deployment target.** Standing Definition of Done
across other Mpingo projects ends in `vercel deploy --prod`. That does not apply here:
ModelBox ships as a tagged Docker image verified by `docker compose up` plus smoke. The
marketing site is the exception and may deploy to Vercel or Cloudflare Pages
independently. This is stated explicitly because the mismatch would otherwise surface as
a failed DoD check every sprint.

**Research documents are inputs, not commitments.** Four breakdowns landed in `docs/`
that were never implemented. §2 of the audit is built to hunt exactly this pattern, and
unshipped research reading as specification is how the current claim-drift arose. Move
them to `docs/research/` with a `Status: research input, not implemented` header, and
reserve `README.md`, `PRD_TRD_v2.md`, and release notes for promises the code keeps.

---

## 5. Phase structure

Sequenced to the stated priority: **functional and dependable first, value
communication second, course last** — with marketing notes captured continuously
(§6) rather than deferred.

| Phase | Sprints | Theme | Duration |
|---|---|---|---|
| **I — Dependable** | 1–5 | Claims true, IR complete, exporters verified, governance real | ~7 weeks |
| *Gate* | — | Paradigm determinism: build now or defer? | — |
| **II — Respected** | 6–7 | Product UI and landing page worthy of the engineering | ~2.5 weeks |
| **III — Taught** | 8 | Curriculum reconciliation and expansion | ~1 week |

**Phase I** is non-negotiable ordering. Sprint 2's IR work gates Sprint 3's exporters;
Sprint 1's harness gates everything by defining "done."

**The gate after Sprint 5** is a genuine decision point. Deterministic paradigm
transformation is the strongest differentiator in the product and also the largest
remaining build. Deferring it to after Phase II is defensible if the near-term goal is a
credible public launch; building it first is defensible if the near-term goal is
enterprise pilots where reproducibility is the purchase criterion. This depends on the
90-day wedge question that is still open.

**Phase II is deliberately after Phase I, not because design matters less, but because
the landing page cannot be written honestly until Phase I lands.** The strongest claim
available — "generates governed contracts and semantic layers, not just schemas" — is
false today for MetricFlow and ODCS. Writing that page now would manufacture exactly the
claim-drift the audit spent 1,400 lines documenting.

---

## 6. The Proof Log — how value communication gets built during engineering

Marketing content should not be written from memory at the end. It should accumulate as
a byproduct of verification.

Create `docs/marketing/PROOF_LOG.md`. Every sprint's Definition of Done includes
appending any claim the sprint made *demonstrably true*, in a fixed shape:

```markdown
## PL-014 — MetricFlow exports parse in dbt
**Claim:** "Semantic layer exports that actually compile — verified against dbt on
every release."
**Evidence:** `test_artifact_fidelity.py::test_metricflow_parses[*]`, 5/5 gold graphs,
CI run #NN.
**Verified:** 2026-09-·· · **Sprint:** 3 · **Expires:** on any change to the emitter
**Usable in:** landing page hero, LinkedIn technical post, enterprise security review
```

Three properties make this worth the overhead. Every marketing claim traces to a named
test, so the landing page is assembled from proven statements rather than aspirational
ones. Claims carry expiry conditions, so a regression invalidates the marketing copy
rather than silently making it false. And the technical LinkedIn content the marketing
plan calls for — the "State of Data Modeling" authority series — writes itself from the
engineering log, which is the only sustainable model for a solo founder.

The `_LAB_SCHEMA.md` convention already in the repo is the precedent: a small, enforced
contract between two subsystems that prevents drift. The Proof Log is the same idea
applied between engineering and marketing.

---

## 7. Standing Definition of Done

Applies to every sprint unless explicitly amended in the sprint spec.

1. Every behavioural change has a test; no fix lands without one that would have caught
   the original defect.
2. CI green across all jobs: backend pytest, artifact-fidelity harness, `tsc --noEmit`,
   `next build`, `next lint`, alembic-head check. `next lint` runs
   `continue-on-error` through Sprint 5 and becomes blocking in Sprint 6 (F7) —
   a new ESLint config failing CI on day one would only train everyone to
   ignore the pipeline.
3. No new `xfail` without a finding ID. Every defect xfail is `strict=True`
   **from creation**, so a fix turns the run red via XPASS until the marker is
   removed and the inventory can never overstate remaining work. *(Amended in
   Sprint 1; the original formulation applied strict only once an xfail
   flipped, which left a window where a repaired defect still read as debt.)*
   Failures that are labelled rather than repaired — Preview dialects and
   LookML, per Q4 — carry `@pytest.mark.preview` and are excluded from the
   burn-down. Sprint completion is defined against non-preview xfails only.
4. Version stamps consistent across `package.json`, `/health`, compose image tags, and
   release notes — enforced by a CI check once Sprint 1 lands.
5. Documentation updated in the same PR. No aspirational claims: if the code does not do
   it, the doc does not say it.
6. `docs/marketing/PROOF_LOG.md` updated with any newly verifiable claim.
7. Appliance verified locally: `docker compose -f docker/docker-compose.appliance.yml up
   -d` followed by the smoke path, before the tag is cut.
8. Tag cut from green `main`; GHCR image built and pulled once to confirm.

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sprint 2 IR migration breaks existing persisted models | Medium | High | Additive columns only, nullable with defaults; round-trip test before canvas work; `test_column_semantics_roundtrip.py` is the template |
| Fidelity harness proves slow, tempting its removal from CI | Medium | High | Run the full matrix nightly and a fast subset per push; never remove the gate |
| Unpinned dependency resolution changes exporter behaviour mid-sprint | High | Medium | `requirements.lock` in Sprint 1; monthly refresh PR |
| Phase II slips indefinitely under correctness work | Medium | Medium | Phase II is time-boxed at 2.5 weeks and starts on a date, not on a condition |
| Scope creep from the four unimplemented research docs | High | Medium | `docs/research/` quarantine; any promotion to roadmap requires an ADR |
| Course work is deferred so long the Trainer's zero-drift property decays | Low | Medium | Fidelity harness covers the linter; lab set-equality test already guards it |

---

## 9. What success looks like at the end of Phase I

A prospective enterprise buyer can be handed the appliance and, without assistance:

- generate a model, export every certified artifact, and have each one parse in its
  native toolchain on the first attempt;
- run entirely air-gapped with a local model, and see a conformance report showing what
  that costs in quality versus a cloud provider;
- read an append-only ledger of everything that has ever left their network;
- point the tool at their existing warehouse and get a governance audit with a
  remediation backlog.

None of those four is true today. All four are within seven weeks. That set — not any
individual feature — is the enterprise sale, and it is also the entire content of the
landing page that Phase II writes.
