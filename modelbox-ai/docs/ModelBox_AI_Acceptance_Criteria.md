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
| B5 ◆ | Preview dialects are visibly labelled in the export UI and docs — no silent downgrade | Screenshot; docs section | 3 |
| B6 ◆ | Protobuf tags do not move when a column is inserted | `test_protobuf_tags_stable_on_insert`, 5/5 | 3 |
| B7 ◆ | ODCS output validates as ODCS v3.1.0 — correct `apiVersion`, required `version` and `status` present, no foreign-spec `info:` block | `test_odcs_*`, 5/5 | 3 |
| B8 ◆ | `required` in ODCS reflects declared nullability, not primary-key status | `test_odcs_required_reflects_nullability` | 3 |
| B9 ◆ | DDL emits in topological order; a deliberately non-parent-first model still deploys | `test_ddl_order_is_topological` | 3 |
| B10 | No Cube measure aggregates a key column, and BOOLEAN columns are typed boolean | `test_cube_no_measure_over_key`, `test_cube_boolean_dimensions_are_boolean` | 3 |
| B11 | A dbt project emitted with quality rules resolves — `packages.yml` present | `test_dbt_declares_packages_yml` | 3 |
| B14 | A dbt project emitted with no hand-written scaffolding parses standalone — the exporter declares the sources its own models reference | `test_dbt_project_is_self_contained`, 5/5 (H9) | 3 |
| B12 | dbt output raises zero deprecation warnings | `test_dbt_no_deprecations`, 5/5 (M11) | 3 |
| B13 ◆ | Generated seed data passes the contract the same model exports — `dbt build` succeeds on own fixtures | `test_seed_respects_*`, 5/5 | 4 |

## C. IR completeness

| ID | Criterion | Evidence | Sprint |
|---|---|---|---|
| C1 ◆ | A model with every field populated survives save → reload → export with zero loss | Round-trip test | 2 |
| C2 ◆ | Nullability, uniqueness, default, and check are expressible and reach every consuming emitter | Field presence in DDL, ODCS, Avro, Protobuf output | 2–3 |
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
| D3 ◆ | Every outbound LLM request is recorded in an append-only ledger; a test proves no path bypasses it | `egress_audit` coverage test | 5 |
| D4 ◆ | An operator can answer "what left our network, when, to whom" from the UI without engineering help | Ledger view screenshot | 5 |
| D5 ◆ | A task pinned to an egress class cannot fail over outside it | Residency enforcement test | 5 |
| D6 ◆ | Air-gapped mode runs end-to-end with no cloud keys present in any container | `docker compose` with air-gap profile; env inspection | 5 |
| D7 | Air-gapped route resolves to a service that exists in the compose file | Route resolution test | 5 |
| D8 | Failover distinguishes auth failure, rate limit, and validation failure | Typed exception handling test | 5 |
| D9 | JWT validates `aud` and `iss`; a token minted for another audience is rejected | Security test | 4 |
| D10 | A conformance report exists comparing at least one local and one cloud provider, scored by the linter | Generated report artifact | 5 |

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
| G2 ◆ | A security reviewer's standard questions — what leaves, where it goes, how to stop it — are answerable from documentation alone | Security FAQ doc | 5 |
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
the reason it claimed to test. Stated once here rather than rediscovered again:

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
