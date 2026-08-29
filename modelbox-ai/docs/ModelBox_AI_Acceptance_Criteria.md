# ModelBox AI — Acceptance Criteria Register

**Version:** 1.0
**Date:** 10 August 2026
**Purpose:** Convert "dependable, valuable, sellable" from judgement into a list of
binary, falsifiable conditions with named evidence.
**Companion to:** `ModelBox_AI_Enhancement_Blueprint.md`, `ModelBox_AI_Sprint_Plan.md`

---

## How to use this

Every criterion is written so that a person who did not build the product can verify it
without asking the person who did. That is the whole test. If verification requires a
demo, a walkthrough, or a caveat, the criterion is not met.

Each carries: an ID, a statement, the evidence that proves it, and the sprint that
closes it. Status values are **MET**, **NOT MET**, or **BLOCKED**. There is no partial
credit — a criterion at 90% is NOT MET, because the 10% is what a buyer's security
reviewer will find.

Criteria marked **◆** are gate conditions: Phase I does not exit until every one is MET.

---

## A. Build integrity and reproducibility

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| A1 ◆ | CI exists, runs on every push and PR, and is required for merge to `main` | GitHub branch protection screenshot; a merge blocked by a red run | 1 |
| A2 ◆ | CI gates all six jobs: pytest, fidelity harness, `tsc --noEmit`, `next build`, `next lint`, alembic-head | `ci.yml` job list; one green run | 1 |
| A3 ◆ | A rebuild reproduces `requirements.lock` byte-identically | Two builds from `python:3.11-slim`, identical hash | 1 |
| A4 | The lock is generated on Linux, carries environment markers, and contains no Windows-only packages | `requirements.lock` inspection | 1 |
| A5 ◆ | Every known defect has a named failing test carrying its finding ID | `pytest -m "not preview"`: 76 xfail, each carrying a finding ID | 1 |
| A6 ◆ | No non-preview xfail remains at Phase I exit; each flipped test is `strict=True` | `pytest` output: 0 xfail outside `@preview` | 3 |
| A7 | Preview failures — the three Preview dialects (15) and LookML (3) — are reported separately and never counted as debt | `pytest -m preview`: 18 xfail, 2 pass | 1 |
| A8 | Version is consistent across `package.json`, `/health`, compose tags, release notes, enforced in CI | Version-check job passes | 1 |
| A9 **MET** | A tagged release builds a GHCR image that pulls and starts clean on a machine that never built it | Proof Log PL-004 — v1.6.0 pulled from GHCR, migrated, `/health` 1.6.0 | 1 |

## B. Artifact correctness — the core claim

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| B1 ◆ | Every certified artifact parses in its **own** toolchain on all five gold graphs — not a string assertion | `test_artifact_fidelity.py`, 5/5 per emitter | 3 |
| B2 ◆ | MetricFlow output passes `dbt parse` on 5/5 graphs | `test_metricflow_parses_in_dbt` | 3 |
| B3 ◆ | Emitted DDL **executes** on at least one certified engine, not merely parses | `test_ddl_executes_on_duckdb`, 5/5 | 1 (locked), 3 (held) |
| B4 ◆ | All four certified dialects pass sqlfluff dialect grammar with zero unparsable segments | `test_ddl_dialect_grammar`, 20/20 | 3 |
| B5 ◆ | Preview dialects are visibly labelled **before** export — grouped in the picker, with a standing warning while selected — and in the docs | `ExportPanel.tsx` picker optgroups + preview banner; README dialect section | 3 |
| B6 ◆ | Protobuf tags **are** the stable identities, gaps included; and do not move when a column is inserted | `test_protobuf_tags_are_the_stable_ids` (primary), `test_protobuf_tags_stable_on_insert`, 5/5 each | 3 |
| B7 ◆ | ODCS output validates as ODCS v3.1.0 — correct `apiVersion`, required `version` and `status` present, no foreign-spec `info:` block | `test_odcs_*`, 5/5 | 3 |
| B15 ◆ | ODCS quality entries use v3.1.0 vocabulary **and carry the constraint's meaning** — conformance and correctness asserted separately, because a valid contract can say the wrong thing | `test_odcs_quality_entries_use_v3_vocabulary` (conformance), `test_odcs_carries_the_meaning_of_each_declared_constraint` (correctness). A mutant emitting a well-formed `nullValues` rule in place of the declared pattern passes the first and fails the second | 4 |
| B8 ◆ | `required` in ODCS reflects declared nullability, not primary-key status | `test_odcs_required_reflects_nullability` | 3 |
| B9 ◆ | DDL emits in topological order; a deliberately non-parent-first model still deploys | `test_ddl_order_is_topological` | 3 |
| B10 | No Cube measure aggregates a key column — primary **or** foreign — and BOOLEAN columns are typed boolean. LookML is Preview and out of scope | `test_cube_no_measure_over_key`, `test_cube_boolean_dimensions_are_boolean` | 3 |
| B11 | A dbt project emitted with quality rules resolves — `packages.yml` present **and accepted by dbt** | `test_dbt_declares_packages_yml` (hands the project to dbt), `test_dbt_parses[quality-rules]` | 3, corrected 4 |
| M12 | Every dialect the backend accepts is reachable from the export UI, and every dialect the UI offers is one the backend certifies | `test_export_ui_offers_exactly_the_dialects_the_backend_supports` | 3 |
| B14 | A dbt project emitted with no hand-written scaffolding parses standalone — the exporter declares the sources its own models reference | `test_dbt_project_is_self_contained`, 5/5 (H9) | 3 |
| B12 | dbt output raises zero deprecation warnings, including for a project that declares packages | `test_dbt_no_deprecations`, 6/6 (M11, M14); `scripts/refresh_dbt_packages.py` fails on a redirected package (M15) | 3, extended 4 |
| B13 ◆ | Generated seed data passes the contract the same model exports — `dbt build` succeeds on own fixtures | `test_dbt_build_succeeds_on_generated_seed_data` (primary — seeds, runs and tests in DuckDB), `test_seed_respects_*` | 4 |

## C. IR completeness

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| C1 ◆ | A model with every field populated survives save → reload → export with zero loss | Round-trip test | 2 |
| C2 ◆ | Nullability, uniqueness, default, and check are expressible and reach every consuming emitter | `test_default_and_check_reach_an_emitter` — asserted by *meaning*, not by substring: `default_value` reaches SQL `DEFAULT`, and an enumerated `check_expression` reaches the ODCS `invalidValues` rule and the dbt `accepted_values` test. Reopened in Sprint 4 (M13), when the claim proved false for two of the four | 2–4 |
| C3 ◆ | Column identity is stable across canvas reorder | `stable_id` persistence test | 2 |
| C4 | A renamed column reports as a rename, not drop-plus-add | Diff engine test | 4 |
| C5 | Removing a foreign key produces a breaking-change statement | Diff engine test (currently yields zero) | 4 |
| C6 | Exactly one persistence path exists | `_persist_graph` removed; single code path | 2 |
| C7 | `ColumnSchema.references` is consumed by the ODCS `foreignKey` emitter | ODCS output contains property-level FK | 2–3 |
| C8 | Existing persisted models load unchanged after migration | Migration verified against a populated DB, not empty | 2 |

## D. Governance and egress — the regulated-buyer gate

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| D1 ◆ | No claim of masking survives anywhere in the product or docs | Grep of README, router config, UI | 1 |
| D2 ◆ | Startup fails loudly if a governance flag is set that the code does not honour | Startup transcript | 1 |
| D3 ◆ | Every outbound LLM request is recorded in an append-only ledger **before it is sent**, and no module outside the gateway can reach a provider at all | **Primary (structural):** `test_no_module_outside_the_gateway_imports_a_provider_sdk` + `test_only_one_function_reaches_the_provider_client` + `test_the_attempt_write_precedes_every_client_statement`. **Supporting:** `test_a_ledger_that_cannot_write_stops_the_request`; `test_migration_0015_egress_audit.py` (raw SQL, populated DB). PL-008 | 5 |
| D4 ◆ **MET** | An operator can answer "what left our network, when, to whom" from the UI without engineering help | Proof Log **PL-009** — `/settings/egress`, reachable from the Studio nav, driven on the running appliance: four attributed rows showing failover from `anthropic_cloud` to `gemini_cloud` with real token counts. Two halves, both asserted: `test_egress_attribution.py` (structural — every call site into the gateway names an actor, or the AST scan fails with file and line) and `test_egress_ledger_view.py` (the view, including that rows scoping cannot show are **counted rather than dropped**). *"To whom"* was the half missing: the identity columns existed from migration 0015 and every call site left them null | 5 |
| D5 ◆ | A task pinned to an egress class cannot fail over outside it, and a task with no pin is a configuration error rather than an allowance. **The permitted set comes from a declared containment map, explicitly not from an ordering over class names** | `test_egress_residency_and_failover.py` — `test_a_pin_strips_non_compliant_failover_targets` (the named mutation), `test_an_eu_pin_does_not_admit_apac_and_an_apac_pin_does_not_admit_eu` (kills the scalar implementation), `test_the_residency_check_lives_in_the_calling_function` (structural), `test_a_task_without_a_pin_is_a_configuration_error`, `test_the_production_router_pins_every_task` | 5 |
| D6 ◆ | Air-gapped mode runs end-to-end **with every provider key set to a sentinel**, uses none of them, and refuses any route that would | `test_airgap_routing.py` — `test_an_airgapped_run_sends_no_cloud_key`, `test_stripping_is_what_makes_a_fall_through_task_local` (the discriminating case), `test_a_route_that_would_use_a_cloud_key_is_refused_at_resolution`, `test_the_sentinels_are_actually_present` | 5 |
| D7 | Every air-gapped provider resolves to a service in the compose file **or is declared bring-your-own**, and no air-gapped primary is BYO | `test_every_airgapped_provider_exists_or_is_declared_byo`, `test_no_airgapped_primary_is_bring_your_own`, `test_the_shipped_local_runtime_is_reachable_from_the_backend` | 5 |
| D8 | Failover distinguishes auth failure, rate limit, and validation failure, and an **unclassified** failure abandons the chain rather than being retried as transient | `test_failures_classify_distinctly` (four inputs, four outputs), `test_an_unmapped_failure_abandons_the_chain`, `test_every_classification_has_a_declared_failover_decision`, `test_an_auth_failure_is_reported_ahead_of_a_rate_limit` | 5 |
| D9 | JWT validates `aud` and `iss`; a token minted for another audience is rejected | Security test | 4 |
| D10 | A conformance report exists comparing at least one local and one cloud provider, scored by the linter against a threshold fixed **before** the first provider call | **The generated report**, not the script — a harness that has never produced a number proves the method, not the claim. Threshold: `scripts/conformance_threshold.py` (commit `b6a3e1a`, into a tree with no code able to call a provider). Harness isolation: `test_conformance_isolation.py` | 5 |

**D3 was re-specified in Sprint 5, and the new wording governs.** It previously
read "a test proves no path bypasses it", which is a negative over the whole
call graph and cannot be earned by sampling: a test exercising three call sites
says nothing about a fourth added next year. Same error as B6 and B11 — a
criterion written past what its evidence could establish.

The evidence is therefore structural, and that is why three tests are named as
primary rather than one. Together they say: nothing outside the gateway can
import a provider SDK, exactly one function inside it reaches the client, and
the ledger write precedes every statement in that function that does. Ledger
completeness then follows by construction rather than by enumeration, and it
fails loudly the day someone adds a sixth provider. A behavioural coverage test
remains useful but cannot be the primary evidence for a universal.

**D5's wording was a defect in this register, found in Sprint 5.** "Max egress
class" encodes an ordering into a domain that has none. Over `local`,
`cloud_eu`, `cloud_apac` and `cloud`, any total order asserts either
`cloud_eu ≤ cloud_apac` or the reverse, and **both are false as residency
controls**: an EU-pinned task must not fail over to APAC, and an APAC-pinned
task must not fail over to the EU. A scalar comparison therefore gets exactly
one of the two wrong — silently, and in the permissive direction.

The name is kept because it is what the product configuration says. The
semantics are not: `egress_policy` declares, per pin, the exact set of classes
it admits. The criterion is amended rather than left to be caught by a test,
because a criterion that misstates the property will be implemented from its own
text — and the register is supposed to be the thing that does not lie.

Related to standard 9: the ordering was a *consequence* that holds in the easy
cases (`local` really is admitted everywhere, `cloud` really is the top) and
fails on the pair that matters.

## E. Claim integrity — the trust gate

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| E1 ◆ | Re-running §2 of the audit against current docs surfaces zero false claims | Re-audit pass | 1 |
| E2 ◆ | No public surface states a capability without a Proof Log ID behind it | Proof Log cross-reference | 7 |
| E3 ◆ | Every Proof Log entry names a passing test and an expiry condition | `PROOF_LOG.md` review | ongoing |
| E4 | Release notes enumerate known open defects with test IDs rather than omitting them | Release notes for the Sprint 1 tag | 1 |
| E5 | Research documents are quarantined and cannot be read as specification | `docs/research/` with status headers | 1 |
| E6 | The PRD carries no unqualified commitment the code does not keep | PRD reconciliation | 1 |

## F. Product experience

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| F1 | Every screen draws colour and type from brand tokens; no ad-hoc values | Token audit of the frontend | 6 |
| F2 ◆ | No unstyled empty, loading, error, or permission-denied state remains | State inventory walkthrough | 6 |
| F3 | Pass/fail state uses semantic colour consistently — Emerald validated, Rose breaking, Amber preview | UI review | 6 |
| F4 | Canvas remains usable at 500 tables | Profiling run | 6 |
| F5 | Export surface shows per-artifact validation status drawn from the fidelity harness | Screenshot | 6 |
| F6 | Contrast meets the brand system's own WCAG standard | Automated contrast check | 6 |
| F7 | `next lint` passes with a committed ESLint config | CI job | 1 (config), 6 (clean) |

## G. Commercial readiness

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| G1 ◆ | An evaluator can install the appliance and export a working artifact without assistance | Unassisted install transcript from someone who has never seen it | 5 |
| G2 ◆ **MET** | A security reviewer's standard questions — what leaves, where it goes, how to stop it — are answerable from documentation alone | `docs/SECURITY_FAQ.md`, one section per question, every capability statement carrying a `PL-` id (PL-008 what leaves, PL-010 how to stop it, PL-009 what is recorded). `test_security_faq_cites_real_proof.py` fails if the FAQ cites an entry that does not exist, if an answer section states capabilities citing nothing, or if the "what we do not claim" section loses its disclosures — so E2 is enforced on this surface rather than promised. **Limit:** no external reviewer has read it yet; that would be stronger evidence than the document's own structure | 5 |
| G3 ◆ | Every landing page claim traces to a Proof Log ID | Claim-to-test map | 7 |
| G4 | Brownfield path works: point at a warehouse, get a governance audit and remediation backlog | Introspection walkthrough | 5 |
| G5 | The differentiator line — governed contracts and semantic layers, not just schemas — is true and stated | Product surface | 3 (true), 7 (stated) |
| G6 | Pricing and licensing model exists in writing | Commercial doc | Phase II |
| G7 ◆ | The 90-day wedge is decided and written down: appliance-to-enterprise or Trainer-as-GTM | Decision record | before Phase II |

## H. Curriculum

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| H1 | One grading path; the 3-invariant rubric is retired | `trainer_service` review | 8 |
| H2 | All 12 linter codes are taught and gradeable | Curriculum coverage test | 8 |
| H3 | Lab set-equality against linter output is preserved | `test_trainer_labs.py` still passes | 8 |
| H4 | At least one lab derives from a real defect this programme fixed | Lab content | 8 |

---

## Verification standard

Three times in Sprint 2 an assertion was written that could not have failed for
the reason it claimed to test. Stated once here rather than rediscovered again.

There are now fourteen, and **ten were earned rather than designed** — written
after something went wrong, not before. That ratio is the most useful fact
about this list: it is a record of how verification actually fails here, not a
theory of how it might. Treat a new one as evidence about the *category* rather
than the instance.

Four of the fourteen (8, 11, 12, 14) are now variations on one theme: a test
that passes without the thing it names ever happening. That they were found
separately, in unrelated code, is the argument for looking specifically for this
shape rather than waiting to trip over it.

1. **Verify from outside the layer under test.** A backfill checked through the
   ORM can be satisfied by a mapping bug; check it with raw SQL. An emitter rule
   checked on data where the old and new rules agree proves nothing; supply a
   discriminating case (correction C7).
2. **A test must verify its own preconditions.** An exit code means a command
   ran, not that it achieved its purpose.
3. **Compare against the previous release, not against the current tree.** The
   "before" side of a migration or compatibility test is produced from a git
   worktree at the last tag, so new fields left unset cannot mask a difference.
4. **A skipped gate must be loud, not absent.** Any test depending on something
   outside the working tree — a toolchain, a container, a git tag, a network
   service — can silently degrade to a no-op and report green having verified
   nothing. Two independent instances in Sprints 1–2, reached from unrelated
   directions: a failed `dbt` install would have skipped fourteen fidelity
   gates, and a shallow CI checkout has no tags, so the migration verification
   would have found no `v1.6.0` worktree and skipped itself. Guard each with a
   strict environment flag (`MODELBOX_FIDELITY_STRICT`,
   `MODELBOX_MIGRATION_STRICT`) that turns absence into failure, and remove the
   cause where you can (`fetch-depth: 0`).

5. **A round-trip test cannot see a defect the round-trip itself corrects.**
   If the path under test normalises its input on the way through, the assertion
   measures the repair rather than the thing being tested. Assert at
   construction as well as after a save.

   Worked example, Sprint 2. `_primary_keys_are_never_nullable` was a Pydantic
   `field_validator`, and Pydantic does not validate a field that was never
   supplied — so it did nothing whenever `is_nullable` was omitted, which is
   every LLM response and every gold graph. The round-trip test passed anyway,
   because reloading constructs `ColumnSchema` with every field explicit and
   the rule fired on the way back. The IR was wrong at construction and correct
   after a save. `POST /model/synthesize` returns the model **directly**, so a
   freshly synthesised primary key stayed nullable and Sprint 3 would have
   emitted no `NOT NULL` for it — silently defeating H4, the whole purpose of
   the sprint that introduced the field.

6. **A gate asserting a relationship to a previous release must state the
   condition under which that relationship holds.** Otherwise its premise
   expires and the gate becomes a schedule dependency rather than a property.

   Sprint 3 found the pattern twice. The migration test asserted every artifact
   was byte-identical to the previous release's output — true only while no
   emitter changes, which was Sprint 2 by design and false in Sprint 3 by
   design. It fused three properties with different lifetimes: *the migration
   preserves the persisted model* (permanent), *emitters are deterministic*
   (permanent), and *emitters match the previous release byte for byte* (a
   schedule dependency). Split into the first two, each stating its scope. The
   same shape produced the sprint's stale 76 → 0 target.

7. **When fixing a defect found through tool output, check whether the tool
   reported the whole class or only its loudest instance.** Evidence can look
   complete merely because it is the only evidence visible.

   Sprint 3: the audit recorded M11 as "generic-test arguments must nest under
   `arguments:`", because that is what dbt warned about on every parse. dbt had
   *also* renamed the block key from `tests:` to `data_tests:` in 1.8, but
   deprecated it far more quietly. A fix addressing only the loud half would
   have shipped and kept warning. Same shape as a non-discriminating test: the
   visible evidence was a partial description of the defect.

8. **A test over fixtures that do not exercise the feature passes vacuously.**
   Distinct from a non-discriminating test, and it wears the same green: there,
   two rules produce identical output; here, the feature is never reached at
   all.

   Sprint 3: the gold graphs carry no `references` values, so a test asserting
   that foreign keys reach the ODCS contract would have passed on five models
   declaring zero foreign keys. The remedy is the general pattern — mutate the
   fixture to populate the field from information the graph already contains
   (there, the relationship edges), then assert the round-trip. Check that the
   fixture *can* fail before trusting that it didn't.

9. **A test can pass on a *consequence* of the property rather than the
   property itself.** The correct implementation implies the consequence, so
   the assertion looks like the thing you care about — but a wrong
   implementation can satisfy it too. The subtlest of the three ways a green
   test means nothing, because unlike vacuous passing (8) and
   non-discriminating passing (1) the assertion reads as exactly right.

   Sprint 3, and it indicted a criterion in this register. B6 named
   "inserting a column moves no existing tag" as the proof of Protobuf wire
   stability. The realistic wrong implementation — sort columns by
   `stable_id`, then number by loop index — honours the field, is stable under
   reorder, and **passes that test on 5/5**, because the inserted column sorts
   last and every existing index is unchanged. It silently re-compacts the gap
   a deleted column leaves, reissuing a retired tag. The property is *tags are
   the identities, gaps included*; no-movement-on-insert is a weaker
   consequence of it. B6 now cites both, property first.

   Note also what the mutation needed before it could discriminate: the fixture
   had to be persisted so `stable_id` was not null throughout (8), and had to
   carry a deliberate gap (1). Two independent fixture properties, either of
   which alone would have made the check meaningless. A suite can be one
   fixture property away from proving nothing.

10. **An artifact can be valid and still be wrong, if it contradicts another
    artifact from the same model.** Every gate above this one asks whether one
    output satisfies its own consumer. That question cannot see a disagreement
    *between* outputs, and the disagreement is the defect the user actually
    experiences.

    Found in Sprint 4. The dbt exporter emitted an `accepted_values` test
    asserting `ACTIVE/INACTIVE/PENDING` while the seed generator, reading the
    same model's `CHECK (status IN ('PENDING','DONE'))` correctly, produced
    `PENDING` and `DONE` (H11). The contract was valid dbt. The seed was valid
    against the model. Shipped together they fail on the first run, and the
    only gate that could see it was `dbt build` — one artifact executed against
    another.

    Prefer a gate that makes two artifacts meet over two gates that check them
    separately.

11. **A gate is only as broad as the fixtures it is parameterised over, and
    that breadth must itself be asserted.** Standard 8 says a fixture must
    exercise the feature; this says something has to *check* that it still
    does, because the failure is silent and reads as success.

    Sprint 4 found four defects (H11, H12, M14, M15) in one blind spot: every
    dbt gate ran over the five gold graphs, no gold graph declares a quality
    rule, and so no project dbt had ever been handed contained a
    `dbt_expectations` test or a `packages.yml`. A malformed `packages.yml`
    that made dbt refuse to load the project shipped in a release whose dbt
    gates were all green.

    `test_seed_fixtures_exercise_every_declared_rule` is the executable form:
    it enumerates the rules the suite asserts and fails when no fixture
    declares one. It fails on a *fixture* regression rather than a code
    regression, which is a category the suite previously had no member of.

12. **A comparison against an absent or empty expected value passes vacuously.
    Assert that the expected value itself exists.** Two instances in Sprint 4,
    in unrelated code, with nothing in common but the shape:

    * `decode_access_token` pinned the JWT audience, and python-jose treats a
      *missing* `aud` claim as nothing to compare rather than as a failure. A
      token carrying no audience at all passed the audience check — the check
      succeeded on the exact input it exists to reject (D9).
    * `_upgrade_to` asserted the stamped alembic revision, but computed the
      expectation as `"" if revision == "head" else revision`. `"" in stamped`
      is unconditionally true, and every forward upgrade in that file targets
      head (M1).

    The first was found by writing the absence case *before* implementing, on
    the prior that this is where such checks usually fail. The prior was right
    and it is not about libraries — the second has no dependency involved at
    all. What generalises is the empty expectation, wherever it comes from.

    A third form, found in Sprint 5 and the hardest to see: **unreachability.**
    `allow_provider_calls` was declared with a bare `validation_alias`, which
    *replaces* the field name, so `Settings(allow_provider_calls=True)` bound
    nothing and returned the default. The flag was not absent and not empty —
    it was unsettable, while the calling code read as entirely correct. A
    security flag that appears set and is not is worse than one obviously
    missing, and the failure direction was permissive.

    So: absence, emptiness and unreachability all produce the same vacuous
    satisfaction. Assert the expected value exists **and that setting it
    changes the outcome.**

13. **A guard is a claim about behaviour, and needs the same discrimination
    test as the code it guards.** Point it at something that must fail and
    confirm that it does. That is cheap, and nothing else establishes that a
    gate can fail at all.

    Stated because remedies in this codebase have three times carried the
    defect they were written to prevent: the `stable_id` high-water mark lived
    on a row its own persistence path deleted; the H4 nullability validator
    never fired on an unsupplied field; and `_upgrade_to` — written precisely
    to stop an exit code being mistaken for arrival — mistook an exit code for
    arrival, in a new disguise. It ran on every migration test and could not
    fail.

    The fix is not more care when writing guards. It is that a guard which has
    never been observed failing is an untested claim, whatever it looks like.

14. **A configuration made correct stops being a test fixture for the mechanism
    that corrects it.** Coverage and correctness come into tension the moment a
    fix lands: the production config that used to contain the discriminating
    case no longer contains it, *because the case was the defect.* The
    discriminating case has to move to a synthetic fixture in the same commit as
    the fix, or the tests quietly stop testing.

    Distinct from standard 11, and worse. There, a fixture never exercised the
    feature and the gap was present from the start. Here the coverage existed
    when the test was written and erodes later — silently, in a commit that
    looks like an improvement, reviewed as an improvement, and correctly
    described as one.

    Found in Sprint 5, in tests written specifically to close a standard 12
    hole. D6 had been re-specified to set sentinel provider keys rather than
    rely on their absence. Task 3 then fixed the air-gapped routing so every
    task in `airgapped_overrides` listed local providers only — which is right,
    and which removed the only case where air-gap *stripping* did any work.
    Disabling the stripping entirely left seven of the eight new tests green.
    The suite was asserting that local-only routes resolve to local providers,
    which is true of a gateway with no air-gap enforcement at all.

    `test_stripping_is_what_makes_a_fall_through_task_local` is the remedy: a
    synthetic router with a task carrying **no** air-gapped override, so
    resolution falls through to `task_routing` and the stripping is the only
    thing standing between a cloud provider and a sentinel key. With it, the
    mutation dies twice instead of once.

    The trigger to watch for is a fix that makes a real-world input stop
    exhibiting the behaviour under test. Ask, at that moment, what still fails
    if the mechanism is removed — and if the answer is "nothing", the fixture
    left with the defect.

A criterion whose evidence violates any of these is NOT MET, whatever the test
reports.

## Stop conditions

If any of these becomes true, halt the sprint and escalate rather than working around it.

1. A fidelity test that once passed begins failing and the cause is a dependency change
   rather than a code change — the lock is not holding, and every result in the register
   is suspect.
2. The fidelity harness reports green with tests skipped rather than run — a missing
   toolchain in CI. `MODELBOX_FIDELITY_STRICT=1` must make this a hard failure; if a
   green run ever coexists with skipped fidelity tests, the gate is decorative.
3. The Sprint 2 migration cannot load existing persisted models without data loss. Every
   subsequent sprint depends on that IR.
4. A criterion is met by weakening its test rather than fixing the product. This is the
   single most likely failure mode of a self-graded register, and the reason every
   criterion names external evidence.

   Its quieter variant, found in Sprint 2: **a criterion met by a test that cannot
   distinguish the correct implementation from the current one is NOT MET.** A test
   passes for the wrong reason when the data it runs on makes two different rules
   produce identical output — nobody weakens anything, and the criterion closes on a
   defect that was never fixed. When a criterion depends on a new field, check that the
   fixtures contain a case where old and new behaviour actually differ. See correction
   C7.
5. A public claim ships without a Proof Log ID. The entire trust argument collapses on
   the first instance.
6. Phase I extends past ten weeks. The engineering is well-mapped; a large overrun means
   the scope was wrong, and the correct response is to cut scope, not to extend.

---

## Scoring

Phase I exits when **every ◆ criterion is MET**. There are 33.

Track weekly as a single number: `MET / 33`. Anything else — velocity, story points,
lines changed — is noise against this list.
