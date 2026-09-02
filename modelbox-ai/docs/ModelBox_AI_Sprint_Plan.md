# ModelBox AI — Sprint Plan

**Companion to:** `ModelBox_AI_Enhancement_Blueprint.md`
**Findings referenced:** `docs/PROJECT_STATE_REPORT.md` §9
**Cadence:** one sprint per named duration, ending in green CI, a tag, and a verified
appliance image. Standing DoD in Blueprint §7 applies to all sprints.

Finding IDs (B1–B3, H1–H8, M1–M10) are the audit's. Every task below carries one so
that scope is traceable and nothing enters a sprint without provenance.

---

# PHASE I — DEPENDABLE

## Sprint 1 — Credibility and Gates
**Duration:** 1 week · **Blocked by:** nothing · **Decisions needed first:** Q2

The premise: nothing else can be trusted until the build is gated and the documents stop
asserting things that are false. This sprint deliberately fixes almost no product
defects — it makes them visible and permanent.

**Scope**

| ID | Task |
|---|---|
| B2 | Create `.github/workflows/ci.yml` — pytest, `tsc --noEmit`, `next build`, alembic-head check on push and PR |
| B2 | Create `.github/workflows/release.yml` — the GHCR workflow `README.md:112-124` already documents |
| — | **`backend/tests/test_artifact_fidelity.py`** — every §4 finding as an `xfail` test, parameterised across the five gold graphs, invoking real toolchains (Blueprint §2) |
| — | `backend/requirements-dev.txt` for the fidelity toolchain; CI installs it into a separate environment from the app requirements |
| H8 | `requirements.lock` generated from the verified clean `.venv`; `Dockerfile.backend` switched to install from it |
| B3 | Make the masking flag honest: fail startup when `MASK_METADATA_IN_PROMPTS=true`, delete the claim from `README.md:106` and `model_router.yaml:20-21` |
| B3 | `logging.dictConfig` at app startup so the existing egress `logger.info` actually emits |
| M5 | Reconcile version stamps across `package.json`, `/health`, compose image tags, release notes; add a CI check |
| M10 | Documentation reconciliation — remove the six shipped-features-listed-as-gaps from ROADMAP, the `hvac` dependency claim, DuckDB introspection, the `topological_order` claim |
| — | Move the four unimplemented research docs to `docs/research/` with status headers |
| M9 | ESLint config only (pulled forward from Sprint 6; the `next lint` job runs `continue-on-error` until Sprint 6) |
| — | Three synthetic defect-reproduction fixtures for findings no correct model can express (H1/M7, B1 role-playing dimension, H6 filename) |

**Definition of Done**

- CI green on `main` and required for merge.
- `pytest` reports a known, documented count of xfails, each carrying a finding ID:
  **76 non-preview** (the Sprint 3 burn-down) and **18 `@preview`** (labelled, not
  scheduled). `MODELBOX_FIDELITY_STRICT=1` in CI so none of it can pass by skipping.
- No document asserts a capability the code lacks — verifiable by re-reading §2 of the
  audit against the updated docs.
- `requirements.lock` committed, **generated inside `python:3.11-slim`** so it carries
  Linux environment markers and no Windows-only packages; a rebuild reproduces it
  byte-identically. (Appendix A was a fifteen-package spot check, not a
  specification — byte-identical reproduction is the property that matters.)
- Startup fails loudly with masking enabled.
- Proof Log seeded with its first entries (CI exists; dependency set is reproducible).

**Explicitly out of scope:** every exporter fix. Sprint 1 records defects; it does not
repair them.

---

## Sprint 2 — IR Foundation
**Duration:** 1.5 weeks · **Blocked by:** Sprint 1 · **Decisions needed first:** Q6, Q8

Everything downstream queues behind this. Four exporters currently guess at nullability
and guess differently; the IR cannot express what they need.

**Scope**

| ID | Task |
|---|---|
| Q8 | Consolidate `GraphRepository._persist` and `SynthesisEngine._persist_graph` into one path — *first*, before H4 doubles the edit surface |
| H4 | `ColumnSchema`: add `is_nullable`, `is_unique`, `default_value`, `check_expression` |
| Q6 | `ColumnSchema.stable_id` — allocated at first persist, never reused (Blueprint §3, Q6) |
| B1 | Entity-level `agg_time_column` (or column-level `is_agg_time_dimension`) so MetricFlow can express `defaults.agg_time_dimension` |
| — | One additive Alembic migration for all of the above; nullable with defaults |
| — | Canvas controls in `ColumnSemanticEditor.tsx` for the new fields |
| — | LLM synthesis prompt updated to populate nullability and the agg time dimension |
| — | Round-trip tests modelled on `test_column_semantics_roundtrip.py` |
| M6 | Resolve `ColumnSchema.references` — wire it into the ODCS/dbt emitters as a column-level FK target, or delete it |

**Definition of Done**

- A model with every new field set survives `POST /model/{id}/graph` → reload → export
  with zero loss, proven by test.
- Existing persisted models load unchanged; the migration is verified against a
  populated database, not an empty one.
- The canvas can set every new field, and the synthesis engine populates them.
- No exporter behaviour changes yet — this sprint adds capability, Sprint 3 consumes it.

---

## Sprint 3 — Exporter Truth
**Duration:** 2 weeks · **Blocked by:** Sprint 2 · **Decisions needed first:** Q4

The sprint where the xfail inventory turns green. Success is measured entirely in the
harness.

**Scope**

| ID | Task |
|---|---|
| B1 | MetricFlow, all four defects: missing `label`; `ref('{name}')` → `ref('stg_{name}')`; aggregation vocabulary mapping (`avg` currently crashes dbt); `defaults.agg_time_dimension` from the Sprint 2 field |
| B1 | MetricFlow foreign-entity naming — name after the parent's primary entity with `expr` carrying the local column, so role-playing dimensions (`ship_to_customer_sk`) join correctly |
| H5 | DDL emission order → `GraphEngine.topological_order`, with the existing `NetworkXUnfeasible` fallback |
| H6 | Protobuf tags from `stable_id`, never `enumerate()`; fix `NUMERIC → double`; sanitise filenames |
| H2 | ODCS: correct `apiVersion` to the current v3 line (verify via context7); `required` from `is_nullable` |
| H3/Q4 | Dialect certification — verify `postgres`, `snowflake`, `redshift`, `duckdb` deployable; label the other three "Preview" in UI and docs |
| M3 | Cube: exclude key columns from measures; add the missing `BOOLEAN` branch. LookML is Preview — no longer in scope |
| M7/H9 | Make the emitted dbt project self-contained: declare the sources its own models reference, and emit `packages.yml` when quality rules produce `dbt_expectations` tests |
| M11 | Nest generic-test arguments under `arguments:` — dbt 1.11 deprecates top-level arguments |
| — | **SafeSQL Pro over ModelBox's own output** — every emitted DDL statement and dbt model scanned as a harness step (takes the slot vacated by LookML). Scope during Sprint 3 planning |

**Definition of Done**

- Every **non-preview** xfail flipped to a pass and its marker removed (they are
  `strict=True` from creation, so an unremoved marker turns CI red), or explicitly
  deferred with written rationale in the sprint retro. Target: 76 -> 0.
  `@preview` xfails are labelled, not debt, and are excluded.
- 5/5 gold graphs parse in every certified emitter's native toolchain.
- A Protobuf tag-stability test inserts a column and asserts no existing tag moves.
- Preview dialects are visibly labelled in the export UI — no silent downgrade.
- Proof Log gains the strongest claims the product has: exports that compile, contracts
  that are wire-stable.

---

## Sprint 4 — Data and Security Correctness
**Duration:** 1 week · **Blocked by:** Sprint 2 (H1 needs the constraint fields)

**Scope**

| ID | Task |
|---|---|
| H1 | Seed generator honours the contract the same model exports — `min_value`, `max_value`, `regex_pattern`, declared length |
| H7 | JWT `aud` and `iss` validation, with config fields and tests (ROADMAP T8) |
| M2 | Diff engine covers relationships, PKs, and governance; rename-vs-drop discrimination using `stable_id` |
| M1 | Persist `suggested_metrics` so the diff engine's formula branch is reachable — or delete the dead branch |
| M8 | Compose profile that omits cloud keys and isolates the network under `AIRGAPPED` |

**Definition of Done**

- `dbt build` succeeds on generated seed plus generated tests for all five gold graphs —
  the product's own fixtures stop failing its own contracts.
- Removing an FK produces a breaking-change statement (currently yields zero).
- A renamed column reports as a rename, not a drop-plus-add.
- An RS256 token minted for a different audience is rejected.

---

## Sprint 5 — Governance That Holds
**Duration:** 1 week · **Blocked by:** Sprint 1 · **Decisions needed first:** Q1, Q2

The enterprise sale, built.

**Scope**

| ID | Task |
|---|---|
| B3 | Append-only `egress_audit` table — model id, user, workspace, task, provider, egress class, prompt SHA-256, token counts, timestamp — written from the single gateway choke point |
| B3 | Ledger view in the UI: what left, when, to whom, under what classification |
| — | Per-task `max_egress_class` enforced in `resolve_route`, so residency is a constraint rather than a global boolean |
| — | Typed failover: auth failure, rate limit, and schema-validation failure handled distinctly instead of one catch-all |
| Q1 | Repoint `airgapped_overrides` at `local_ollama`; document vLLM as BYO |
| — | **Provider conformance harness** — five gold graphs synthesised per configured provider, scored by the 12-code linter, emitted as a report (Blueprint §4) |

**Definition of Done**

- Every outbound request appears in the ledger; a test asserts no gateway path bypasses
  it.
- A task pinned to an EU-sovereign provider cannot fail over to another egress class.
- Air-gapped mode runs end-to-end with no cloud keys present in any container.
- A conformance report exists comparing at least one local and one cloud provider.

---

## ◆ Decision Gate — after Sprint 5

**Deterministic paradigm transformation: build now, or after Phase II?**

The audit confirmed `ParadigmTranslator.transform` routes a specifiable transformation
through the LLM. Recommended first increment if built: Data Vault only —
hub/link/satellite decomposition is the most mechanical of the three paradigms — with a
provenance trace explaining every derivation, and a lossless round-trip test as the CI
gate. Estimated 2–3 weeks.

Build now if the near-term goal is enterprise pilots where reproducibility is the
purchase criterion. Defer if the near-term goal is a credible public launch. This
resolves against the 90-day wedge question.

---

# PHASE II — RESPECTED

## Sprint 6 — Product UI Credibility Pass
**Duration:** 1.5 weeks · **Blocked by:** Sprint 3

The brand system is written and unusually complete — full token set, type scale,
semantic colour mapping, accessibility standards. This sprint applies it rather than
redesigning anything.

**Scope**

- Brand tokens into Tailwind config as the single source: Navy `#0A1628`, Blue `#2563EB`,
  Cyan `#06B6D4`, the semantic mapping, Inter and JetBrains Mono, the documented type
  scale.
- Semantic colour applied where it carries meaning rather than decoration — Emerald for
  passing validation, Rose for breaking changes, Amber for preview-dialect warnings.
  The product's core loop *is* pass/fail state; the palette should carry it.
- The states an enterprise evaluator hits and that demo screenshots never show: empty
  workspace, synthesis in progress, partial failure, permission denied, air-gapped mode
  with no provider reachable.
- Canvas polish for the 500-table case — virtualisation and worker-side layout if
  profiling justifies it.
- Export surface redesign: certified versus preview dialects, per-artifact validation
  status drawn from the fidelity harness. This is the screenshot that sells the product,
  and after Sprint 3 it can be truthful.
- Accessibility pass to the brand system's own WCAG standard; ESLint config (M9) and a
  canvas-store smoke test.

**Definition of Done:** every screen uses tokens rather than ad-hoc values; no
unstyled error or empty state remains; `next lint` passes in CI; contrast verified.

---

## Sprint 6.5 — Enterprise Access
**Duration:** 1.5 weeks · **Blocked by:** Sprint 5 (workspaces, API keys, ledger)
**Added:** 2026-09-02, from buyer research. See `docs/sprint-6-progress.md`.

**Why this exists, and why it is numbered between two sprints rather than
appended.** Buyer research put the largest funded opportunity in EU/UK banking
and insurance **regulatory remediation** — bought from an MRA / consent-order /
SREP-finding budget rather than a tooling budget, which is the difference
between a three-year commitment and a one-year pilot that dies. Every artifact
this product already proves is well matched to that buyer.

And it is unreachable. **A bank's architecture review board rejects the appliance
on identity and auditability before it ever evaluates an emitter.** Before this
entry, the words SSO, SAML, SCIM, RBAC and audit export appeared **nowhere** in
this plan or in the acceptance register — the gap was not unscheduled, it was
unnamed. Sprint 7 assembles a landing page for a segment that cannot buy;
sequencing this first is what makes Sprint 7 worth doing.

**Scope**

- **SSO via SAML 2.0 and OIDC.** The identity providers that matter are Entra ID,
  Okta and Ping. Local password auth stays for air-gapped installs where there
  is no IdP to federate with — an appliance that *requires* an IdP is unusable
  in the one segment where air-gap is mandatory.
- **SCIM provisioning and de-provisioning.** De-provisioning is the half that
  gets audited: a leaver's access disappearing is the control, not their arrival.
- **RBAC with roles that mean something here.** At minimum: viewer, modeller,
  approver, admin. The approver role is the one a remediation programme needs,
  because it is what makes "who signed off on this model" answerable.
- **Audit-log export.** Append-only, covering authentication, authorisation
  changes, model mutations and artifact generation — in a format an operator can
  ship to Splunk or Sentinel without writing a parser. The egress ledger already
  answers *what left the network*; this answers *who did what inside the
  appliance*, and a supervisor asks both.
- **A documented availability position.** Not necessarily HA. Single-node with a
  stated RPO/RTO, a tested restore, and an honest limitation is a reviewable
  answer; silence is not. Decide and write it down.

**Explicitly out of scope:** multi-node clustering, and any attempt to match a
hyperscaler's AI-output indemnity. Both are real asks from this buyer and
neither is winnable at this size; the honest answer is that in an air-gapped
deployment the customer holds the model contract, so the provider's own
indemnity flows to them.

**Definition of Done:** a bank's standard identity and audit questionnaire can
be answered from the product rather than from a roadmap; every claim added to
the register carries a passing test; and the availability position is written
down even where the answer is "single node, restore in N minutes, tested on
DATE".

---

## Sprint 7 — Landing and Content
**Duration:** 1 week · **Blocked by:** Sprint 6, Sprint 6.5, Proof Log

**Scope**

- Landing page assembled **exclusively from Proof Log entries**. Every claim on the page
  traces to a named passing test. The hero writes itself from Sprint 3: exports that
  compile in their native toolchain, contracts that are wire-stable, a ledger of
  everything that left.
- The differentiator line the audit's own strategic reviews identified and no current
  surface states: *generates governed contracts and semantic layers, not just schemas.*
  False today; true after Sprint 3.
- Docs site from the reconciled `README`, `USER_GUIDE`, `API_REFERENCE`.
- First content batch from the marketing plan's authority series, drafted from
  engineering notes rather than invented — the "State of Data Modeling" angle is
  well-served by the fidelity findings themselves.
- Deploys to Vercel or Cloudflare Pages, independent of the appliance.

**Definition of Done:** zero claims on any public surface without a Proof Log ID; a
reviewer can trace every headline to a test.

---

# PHASE III — TAUGHT

## Sprint 8 — Curriculum Reconciliation
**Duration:** 1 week · **Decisions needed first:** Q3

**Scope**

- M4: collapse the two grading paths onto the 12-code linter; retire the 3-invariant
  rubric.
- Extend curriculum coverage from 9 codes to all 12.
- Labs for the new IR surface — nullability, constraints, stable identity — and for the
  defects this programme fixed. The MetricFlow `agg_time_dimension` failure is an
  excellent lab: a real defect, a real parser error, a verifiable fix.
- Instructor notes drawn from the Proof Log.

**Definition of Done:** one grading path; `test_trainer_labs.py` set-equality property
preserved against all 12 codes.

---

## Summary

| Sprint | Theme | Duration | Key gate |
|---|---|---|---|
| 1 | Credibility and gates | 1 wk | CI exists; defects are tests |
| 2 | IR foundation | 1.5 wk | Round-trip lossless |
| 3 | Exporter truth | 2 wk | 5/5 graphs parse everywhere certified |
| 4 | Data and security correctness | 1 wk | `dbt build` passes on own fixtures |
| 5 | Governance that holds | 1 wk | Ledger complete; air-gap real |
| ◆ | Paradigm determinism decision | — | Wedge-dependent |
| 6 | UI credibility | 1.5 wk | Tokens everywhere; states covered |
| 6.5 | Enterprise access | 1.5 wk | The priority buyer can pass its own review |
| 7 | Landing and content | 1 wk | Every claim traced to a test |
| 8 | Curriculum | 1 wk | One grading path |

Phase I is roughly seven weeks to the four capabilities in Blueprint §9. Phases II and
III add three and a half.
