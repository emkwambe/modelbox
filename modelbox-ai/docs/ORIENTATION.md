# ModelBox AI — Orientation

*What this repository is, where each thing lives, and how to check any of it
yourself. Written 2026-08-27 against `sprint/5-governance` at `0c6daf8`.*

**This document makes no capability claims.** Every statement below is either a
location (`file:line`), a command you can run, or a quotation of another
document — and where a document and the tree disagree, that disagreement is
recorded rather than smoothed over. Capability claims live in
`docs/marketing/PROOF_LOG.md` behind a `PL-` id, and nothing here creates one.

---

## 0. The first thing to get right: where the repository root is

The git root is **`modelbox/`**, one level above the project directory
`modelbox/modelbox-ai/`. The root holds `.github/`, four founding specification
documents, and `modelbox-ai/` — which is the entire application.

```
modelbox/                                  ← git root (origin: emkwambe/modelbox)
├── .github/workflows/{ci,release}.yml      ← CI lives HERE, not under modelbox-ai/
├── DataModelAI Blueprint.md
├── Dependencies & Tech Stack Specification.md
├── ModelBox AI PRD & TRD Specification.md  ← v1 spec, superseded by docs/PRD_TRD_v2.md
├── ModelBox AI Use Cases.md
└── modelbox-ai/                            ← 215 of the repo's 223 tracked files
```

This matters more than it looks. Running `ls .github` from `modelbox-ai/`
returns nothing, and the state-report audit concluded from exactly that command
that the project had no CI at all — a finding that reached three sections of the
audit before being withdrawn as **correction C1**
(`docs/PROJECT_STATE_REPORT.md:26`). The workflows were tracked the whole time,
and the CI had run 59 times.

**I reproduced the same error while writing this document**, from the same
directory, and caught it only by running `git rev-parse --show-toplevel` — the
command C1 names as the one that would have prevented it. That is the single
most useful orientation fact in the repo, so it is first: *check the toplevel
before concluding a file is absent.*

---

## 1. What the product is

An LLM-agnostic data modeling and governance workspace, shipped as a single-node
Docker appliance. Natural language in; a validated entity graph on a canvas; and
production artifacts out — DDL across seven dialects, dbt projects, data
contracts, semantic layers, dictionaries and seed data. It also reverse-engineers
live warehouses, lints for governance, and diffs model versions.

Two things distinguish it structurally from a code generator, and both shape the
codebase:

- **Every artifact is emitted from one typed intermediate representation**, so a
  field is either expressible in the IR or invisible to every exporter at once.
- **Every provider call is a governed egress event.** Residency, failover and an
  append-only ledger are in the request path, not bolted beside it.

---

## 2. The map

### Backend — `modelbox-ai/backend/` (~9,300 lines of `app/`)

Layered FastAPI: `api/v1/endpoints` → `services` → `models` (SQLAlchemy) with
`schemas` (Pydantic v2) as the contract between them.

| Module | Lines | What it owns |
| :-- | --: | :-- |
| `services/exporter_service.py` | 1539 | Every artifact. DDL via SQLGlot, dbt, Cube, LookML, MetricFlow, ODCS, Avro, Protobuf, dictionaries |
| `schemas/data_model.py` | 866 | **The IR.** `EntitySchema` / `ColumnSchema` / relationships — the file to read first |
| `services/introspection.py` | 841 | Reverse-engineering: Postgres, MySQL, Snowflake, BigQuery, Databricks, DuckDB |
| `models/metadata_store.py` | 659 | 13 tables — users, workspaces, models/entities/columns/relationships, jobs, connections, api keys, trainer, `egress_audit` |
| `services/graph_engine.py` | 595 | NetworkX linter — **13 codes** — plus topological ordering |
| `services/llm_gateway.py` | 570 | The single egress choke point: routing, residency, failover classification, ledger writes |
| `services/seed_generator.py` | 497 | Synthetic rows that must satisfy the contract exported from the same model |
| `services/diff_engine.py` | 292 | Version-to-version breaking-change detection |
| `services/egress_ledger.py` | 244 | Append-only record, written *before* the request leaves |

The linter's thirteen codes, all in `graph_engine.py`: `CYCLIC_FK`,
`MISSING_PK`, `DANGLING_REF`, `NAMING_CONVENTION`, `MISSING_GRAIN`,
`MISSING_DESCRIPTION`, `PII_EXPOSURE`, `FAN_OUT_RISK`, `MISSING_SLA`,
`INVALID_RANGE`, `INVALID_REGEX`, `PATTERN_EXCEEDS_LENGTH`, `ORPHAN_ENTITY`.

Seven API routers (`api/v1/router.py`): auth, jobs, models, transform,
workspaces, trainer, connectors. Fifteen Alembic migrations, `0001` → `0015`,
linear.

### Frontend — `modelbox-ai/frontend/` (~6,700 lines of `src/`)

Next.js 14 App Router, six routes: `/`, `/canvas`, `/docs`, `/trainer`,
`/settings/api-keys`, `/settings/connectors`. Zustand for canvas state
(`store/canvasStore.ts`, 508 lines). `lib/templates.ts` is load-bearing beyond
the UI — the six gold reference graphs are **extracted** from it into the test
fixtures, never transcribed, with a drift guard.

### Configuration and deployment

`config/model_router.yaml` is where the governance model is actually declared —
see §4. `docker/docker-compose.appliance.yml` defines UI, backend, worker,
LiteLLM proxy, Postgres 16, Redis 7, and an `airgap`-profiled Ollama engine.
Image tags and `backend/app/__version__.py` are both `1.9.0`, and a CI job
enforces that they agree.

---

## 3. The verification apparatus — the part that is unusual

This repo spends more of itself on proving things than on doing them, and an
orientation that skips this will misread every code review.

**Two Python environments, never mixed.** `backend/.venv` runs the application
and `pytest`; `backend/.venv-tools` runs the artifact fidelity toolchain. dbt
downgrades `protobuf` and `pathspec` and removes `mypy`, so installing one into
the other silently changes what a fidelity verdict means (`CLAUDE.md`,
*Environments*).

**Two suites.**

```bash
cd backend
.venv/Scripts/python -m pytest -q                                   # the app suite
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest \
    tests/test_artifact_fidelity.py -m "not preview" -q             # the burn-down
```

`test_artifact_fidelity.py` (52 test functions) asserts artifacts against **the
tools that consume them** — `dbt parse`, `dbt build`, `protoc`, `fastavro`,
`sqlfluff`, DuckDB execution — never against substrings. It carries the audit's
burn-down as `strict=True` xfails, so a fix that leaves its marker in place turns
the run red. `MODELBOX_FIDELITY_STRICT=1` converts a missing toolchain into a
failure rather than a skip.

**Six gold graphs.** `backend/tests/fixtures/gold/` — `aml-financial-crime`,
`banking-datavault`, `ecommerce-orders`, `healthcare-ehr`,
`marketing-attribution`, `saas-subscription`. Every emitter is asserted 6/6
against them. They are a curriculum and marketing asset: defect reproductions go
in `fixtures/synthetic/` instead.

`aml-financial-crime` arrived in `e0beb47` (AML slice 1) after this document was
written. Nothing in the fixture layer needed changing for it — every per-graph
test globs the directory or compares sets — which is why the count moved in the
prose and the documentation before it moved anywhere else.

**Fourteen verification standards** (`docs/ModelBox_AI_Acceptance_Criteria.md`),
of which the register says ten were *earned* — written after something went
wrong. Four of them (8, 11, 12, 14) are one shape restated: **a test that passes
without the thing it names ever happening.** If you write a test here, that is
the failure mode you are being asked to rule out.

327 test functions across 33 files.

---

## 4. Governance and egress, as actually declared

`config/model_router.yaml:112` — the containment map, which is the whole design:

```yaml
egress_policy:
  local:      ["local"]
  cloud_eu:   ["local", "cloud_eu"]
  cloud_apac: ["local", "cloud_apac"]
  cloud:      ["local", "cloud_eu", "cloud_apac", "cloud"]
```

The permitted set per pin is **declared, never inferred from an ordering over
class names.** Any total order asserts either `cloud_eu ≤ cloud_apac` or the
reverse, and both are false as residency controls: an EU-pinned task must not
fail over to APAC, nor the reverse. A scalar comparison gets exactly one of them
wrong, silently, in the permissive direction. This was found in Sprint 5 as a
defect *in the register's own wording*, and the criterion (D5) was amended rather
than left for a test to catch.

A task with no `max_egress_class` is a configuration error at load, not an
implicit allow (`llm_gateway.py:301`). The ledger's `record_attempt` precedes
every statement that reaches the provider client, and the structural tests assert
that nothing outside the gateway can import a provider SDK at all — which is what
makes ledger completeness a property of construction rather than of enumeration
(register D3, `PL-008`).

---

## 5. The document system — which file is authoritative for what

Reading these in the wrong order is the main way to get a wrong picture here.

| Document | Authoritative for | Do not use it for |
| :-- | :-- | :-- |
| `PROJECT_STATE_REPORT.md` | **Finding IDs** (H/B/C/D/M/Q) cited everywhere else. Corrected in place, dated, never rewritten | Current state — it is dated 2026-08-10 |
| `ModelBox_AI_Enhancement_Blueprint.md` | Rulings and definitions of done | Status |
| `ModelBox_AI_Acceptance_Criteria.md` | **The register** — criteria A–H, their evidence, and the 14 standards | — |
| `marketing/PROOF_LOG.md` | Public claims. `PL-001`…`PL-008`, each naming a passing test and an expiry | Anything without a `PL-` id |
| `sprint-N-progress.md` | Handoff state, and the mutation results that prove a test can fail | Sprints 2 and 3 are stale — see §7 |
| `PRD_TRD_v2.md` | Forward planning; supersedes the root v1 spec | — |
| `research/` | Quarantined. Explicitly **not** specification | — |

Two conventions from `CLAUDE.md` that will bite before anything else does:

- **Never edit source through a bash heredoc, or with a regex spanning multiple
  constructs.** Four incidents in one sprint; one deleted 161 lines. The stated
  conclusion is that the reasoning was correct and *the transport corrupted it*,
  so the remedy is removing the transport, not more care. Use direct edits.
- **Never chain a verification command into a pipe that can mask an earlier
  failure.** The failure this guards is not a broken build — it is claiming
  verification you did not perform.

---

## 6. Measured state

*Commands run 2026-08-27 on `sprint/5-governance` at `0c6daf8`, Docker 29.6.1.
Not quoted from a progress doc — each row is the output of the command beside
it, run for this report.*

| Measure | Result | Command |
| :-- | :-- | :-- |
| App suite | **572 passed, 36 skipped, 18 xfailed** (162s) | `.venv/Scripts/python -m pytest -q` |
| Fidelity, non-preview | **229 passed, 5 skipped, 0 xfail** (158s) | `MODELBOX_FIDELITY_STRICT=1 .venv-tools/… -m "not preview"` |
| Fidelity, preview | **18 xfailed, 2 passed** (4s) | same, `-m "preview"` |
| Ruff over `app` + `tests` | **69 findings** | `.venv/Scripts/python -m ruff check app tests` |
| Version stamps | **all agree: 1.9.0** | `python scripts/check_versions.py` |
| Repository | 223 tracked files, 130 commits, 2026-08-09 → 2026-08-13 | `git ls-files`, `git rev-list --count HEAD` |

**Every one of these matches the baseline recorded at
`docs/sprint-5-progress.md:21` on 2026-08-12 — exactly, including the 69 Ruff
findings and the 18 preview xfails.** That table exists so a later run can tell
whether a number *moved* rather than only what it is; two weeks on, nothing has.
The app suite spins up a disposable PostgreSQL and takes ~2 minutes 42; its 36
skips are the fidelity tests, which need `.venv-tools`.

> **Superseded 2026-09-01.** Every row above has since moved, and the table is
> left as it was rather than re-run in place — it is a record of commands run on
> a date, and editing the numbers would destroy the only thing it is for. The
> current baseline is `docs/sprint-6-progress.md`: app suite 682 / 41 / 22,
> fidelity 274 / 5 / 0, preview 22 xfail / 2 pass, Ruff still exactly 69,
> versions 1.10.0. The cause is `e0beb47` adding a sixth gold graph plus the
> Sprint 5 tail; the preview arithmetic is exact (3 dialects × 6 graphs, plus
> LookML's list going from 3 names to 4), and all 22 carry a preview reason. The
> sentence above — "two weeks on, nothing has" — was true when written and is
> now the thing this note exists to correct.

Two notes on the skips, because a silent skip is the thing this repo distrusts
most. Under `MODELBOX_FIDELITY_STRICT=1` a missing toolchain is a hard failure,
not a skip (`test_artifact_fidelity.py:155`) — so the 5 skips in the non-preview
leg cannot be absent tooling. They are per-graph and structurally justified:
`marketing-attribution` is a single-entity OBT model with no foreign keys, so
FK-ordering assertions have nothing to assert (`:832`, `:1263`, `:1559`).

The preview leg's 2 passes are expected and are *not* counted as progress:
`@pytest.mark.preview` marks failures that are labelled rather than scheduled —
the three Preview dialects and LookML — and register A7 fixes the shape at "18
xfail, 2 pass".

---

## 7. Where the tree and the documents disagree

Recorded, not fixed — each is someone's call to make.

**Sprint 5 is genuinely open.** Tasks 0–4 are done and the code backs them.
Outstanding: Task 5's conformance run (the harness exists and ran once against
one cloud provider; the run invalidated its own metric — F1 over entity *names*,
empty-set F1 returning 1.0 into an average, and `MISSING_SLA` penalising a field
the prompt never asks for — so a metric redesign precedes the local run and D10
does not close), Task 6 (Security FAQ, G2), Task 7 (unassisted install, G1,
needs an evaluator), Task 8 (a lab from a real defect, H4), and D4's
`model_id`/`user_id`/`workspace_id` wiring, without which the ledger cannot
answer "who". The branch is not pushed to `origin` and carries no tag; Sprints
1–4 each closed with one (`v1.6.0`–`v1.9.0`).

**Register G4 is an orphan.** The register assigns it to Sprint 5 — "point at a
warehouse, get a governance audit and remediation backlog" — and it appears in no
Sprint 5 task, done or outstanding. Introspection has existed since Sprint 2;
nothing claims the walkthrough evidence.

**Three documents understate what shipped.** `sprint-3-progress.md:24` still
lists Tasks 1–7 as "in progress"/"not started" although Sprint 4 closed at 0
non-preview xfail and tagged `v1.9.0`. `Unified_Sprint_Plan.md:16` marks
Governance and Quality as "Pending" although `freshness_sla`
(`schemas/data_model.py:557`), `min_value`/`regex_pattern` (`:471`, `:477`), the
`MISSING_SLA` lint (`graph_engine.py:462`), Modules 2–5 and labs `m2_`–`m5_` all
exist. `sprint-2-progress.md:211` still lists work that `v1.7.0` closed.

**Four claims are earned in tests but unusable by the repo's own rule.** The
Proof Log's "not yet provable" table (`PROOF_LOG.md:326`) still blocks "semantic
layer exports compile in dbt", "data contracts are wire-stable", "our contracts
are valid ODCS" and "generated test data satisfies the generated contract" on
findings B1, H6, H2 and H1 — all closed in Sprints 3 and 4. No `PL-` entry names
the tests that closed them, so by rule E2/G3 the claims still cannot reach a
public surface. That is the gap the Proof Log exists to prevent, pointing the
other way.

**Small drift:** register H2 speaks of "all 12 linter codes"; `graph_engine.py`
emits 13.

**One unanswered question.** `sprint-4-progress.md:117` records a migration gate
that failed all four tests once, unreproduced, and rules: "if it recurs in Sprint
5 it stops being a watch item." Nothing in the Sprint 5 doc says whether it
recurred.

---

## 8. Orienting yourself in an hour

1. `git rev-parse --show-toplevel`. Then read `CLAUDE.md` — it is short and every
   line was bought.
2. Read `backend/app/schemas/data_model.py`. Everything downstream is a
   projection of it.
3. Read `backend/app/services/graph_engine.py` linter methods; then open
   `frontend/src/content/trainer/m1_lab1_grain_and_fanout.json` and see that the
   lab's `expected_flaws` are asserted set-equal to linter output by
   `test_trainer_labs.py`. That coupling is the repo's strongest artifact.
4. Run the app suite. Then run the fidelity suite with
   `MODELBOX_FIDELITY_STRICT=1` and watch it hand real files to `dbt` and
   `protoc`.
5. Read one Proof Log entry in full — `PL-007` is the clearest — for the house
   style: claim, named test, *why it is stronger than it looks*, honest limit,
   expiry condition.
6. Read `docs/sprint-5-progress.md` last, and only then §7 above.
