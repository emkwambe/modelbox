# ModelBox AI — Proof Log

**Purpose:** every public claim traces to a named passing test. Marketing copy is
assembled from this file, not written from memory.

**Rule (Blueprint §6, DoD 6):** a sprint appends an entry only when it makes a
claim *demonstrably* true. Entries carry an expiry condition, so a regression
invalidates the copy rather than silently making it false. No claim reaches a
public surface without a `PL-` identifier behind it (register **E2**, **G3**).

**Verifying an entry yourself:**

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -v
```

Entries are append-only. When one expires, mark it **EXPIRED** with the date and
reason; do not delete it — the history is the argument.

---

## PL-001 — Certified SQL dialects are certified by two independent grammars

**Claim:** "The four SQL dialects we certify — PostgreSQL, Snowflake, Redshift,
DuckDB — are verified against real dialect grammars on every push, not against
our own parser."

**Evidence:** `test_artifact_fidelity.py::test_ddl_dialect_grammar`, 20/20
certified cases (4 dialects × 5 gold graphs), zero unparsable segments under
`sqlfluff` 4.3.0. The same test marks `bigquery`, `databricks` and `clickhouse`
`@preview`: each rejects the emitted `CREATE TABLE` constraint body, which is why
they are labelled rather than advertised.

**Why it is stronger than it looks:** the certified/preview boundary was
originally an architect's judgement call about which dialects to support.
`sqlfluff` — a second parser with per-dialect grammars, independent of the
`sqlglot` used to *generate* the DDL — reproduces that boundary exactly. The
product line is drawn where the evidence falls, not where convenience put it.

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** on any change to `ExporterService.generate_ddl`, `_entity_create_table`,
the `sqlglot` or `sqlfluff` pin in `requirements.lock`, or the certified-dialect list.
**Usable in:** landing page, export UI dialect labels, enterprise technical review,
"why we advertise four dialects and not seven" post.

---

## PL-002 — Generated DDL executes on a real engine, not just a parser

**Claim:** "Our generated schemas don't just parse — we execute them. Every
release runs all five reference models' DDL against a live DuckDB instance and
asserts the tables that come back are the tables you modelled."

**Evidence:** `test_artifact_fidelity.py::test_ddl_executes_on_duckdb`, 5/5 gold
graphs. Each emits DDL in the `duckdb` dialect, executes it in an in-memory
database, then queries `information_schema.tables` and asserts the created set
equals the model's entity set.

**Why it is stronger than it looks:** every other artifact claim in this file
rests on a *parser* accepting output. This one rests on a database engine
accepting it and reporting back what it built. DuckDB is the only certified
dialect whose engine is embeddable, which is what makes the check possible in
CI with no infrastructure.

**Honest limit:** it proves deployability for DuckDB. PostgreSQL, Snowflake and
Redshift are certified by two grammars (PL-001), not by execution. Do not
generalise this claim to "executes on every certified warehouse."

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** on any change to `generate_ddl`/`_entity_create_table`, the `duckdb`
pin in `requirements.lock`, or the gold graph set.
**Usable in:** landing page hero, technical blog, enterprise security review.

---

## PL-003 — `main` is protected and cannot be merged into on a red build

**Claim:** "Nothing reaches our main branch without six independent checks
passing: backend tests, the artifact fidelity harness, strict TypeScript, a
production build, lint, and a single-migration-head check — plus a version
consistency gate."

**Evidence:** GitHub branch protection on `emkwambe/modelbox@main` with named
required status checks and `strict: true` (branches must be up to date before
merge). Verify with:

```bash
gh api repos/emkwambe/modelbox/branches/main/protection \
  --jq '.required_status_checks | {strict, contexts}'
```

Workflow: `.github/workflows/ci.yml`. Runs on every branch and every pull
request as of v1.6.0; it previously ran only on `main` and PRs into `main`, so
feature branches were unguarded until a PR opened.

**Why it is stronger than it looks:** CI existed before v1.6.0 and had run 59
times, green. It gated `pytest`, `tsc --noEmit` and `next build` — and the
backend suite asserted exporter output by *substring*, so a semantic-layer
exporter that `dbt parse` rejects on 5/5 models passed every one of those 59
runs. The claim worth making is not "we have CI"; it is "our CI checks each
artifact against the tool that consumes it," and the fidelity job is what makes
that true.

**Honest limit:** `enforce_admins` is off and no reviewer approval is required,
so a repository administrator can still bypass. Suitable for "changes are gated,"
not for "changes are impossible to force."

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** if branch protection is relaxed, a required check is removed from the
context list, or the fidelity job stops running with `MODELBOX_FIDELITY_STRICT=1`.
**Usable in:** enterprise procurement questionnaire, engineering-practices page,
"the audit is the test suite" post.

---

## PL-004 — A tagged release publishes an image that pulls and runs clean

**Claim:** "Tag a release and you get container images on GHCR that start,
migrate, and serve on a host that did not build them."

**Evidence:** tag `v1.6.0` triggered `.github/workflows/release.yml`, which built
and pushed `ghcr.io/emkwambe/modelbox-backend:1.6.0` and
`…-frontend:1.6.0`. Neither image existed locally — `docker rmi` reported *No
such image* before the pull, so the artifact tested is the runner's, not a local
build. Pulled, started against the appliance Postgres, and observed:

- Alembic ran to head inside the container.
- The healthcheck went healthy in ~10s.
- `/health` returned `{"status":"ok", … "version":"1.6.0"}` — the same value
  stamped in `backend/app/__version__.py`, `package.json` and the compose tags.
- The retired masking flag still fails startup *in the published image*, exiting
  1 with the error naming `AIRGAPPED=true`.

**Honest limit:** the *images* were never built on this host, but the *host* has
built the project. This proves the published artifact is self-sufficient — it
does not prove a first-run experience on a machine with no toolchain, no build
cache and no prior Docker layers. Register **A9** is satisfied; the stronger
unassisted-install claim is **G1**, Sprint 5.

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** on any change to `docker/Dockerfile.backend`, `release.yml`, or the
container start command.
**Usable in:** install documentation, enterprise evaluation guide, "how we ship"
post.

---

## PL-005 — Artifact generation is deterministic, and that is tested

**Claim:** "The same model always produces the same bytes. Our exporters are
pure functions of the model — verified across a live database migration on every
release, not assumed."

**Evidence:**
`test_migration_0013_populated.py::test_artifact_generation_is_deterministic`.
All five reference models are exported twice from a real PostgreSQL 16 — DDL
across 7 dialects, dbt, Cube, LookML, MetricFlow, ODCS, Avro, Protobuf, three
dictionary formats, two seed formats — in **separate processes**, and every
artifact compared by SHA-256. Separate processes matter: Python randomises
string hashing per process, so a comparison inside one interpreter would not
detect an emitter that depended on set or dict iteration order.

*Evidence pointer updated 2026-08-11.* This was originally asserted by comparing
against the previous release's output across a migration. That fused
determinism with "no emitter changed since the last release", which is not a
property — see register verification standard 6. Determinism is still tested;
it now has its own test.

**Why it is stronger than it looks:** every other claim in this file depends on
it. "Exports parse in their own toolchain" and "Protobuf tags do not move" both
presuppose that generation is reproducible; if an emitter depended on dictionary
iteration order, an unsorted glob, a clock or a hash seed, every fidelity verdict
would be a coin flip that happened to land the same way twice. That assumption
was load-bearing and untested until now.

**Honest limit:** it proves determinism across a migration on one machine within
one run. It is not a cross-platform or cross-version reproducibility claim.

**Verified:** 2026-08-11 · **Sprint:** 2 · **Version:** unreleased
**Expires:** on any change to `ExporterService`, `SynthesisEngine.get_model`, or
`GraphRepository`, and on any new migration that does not re-run this gate.
**Usable in:** technical blog, enterprise evaluation, "the audit is the test
suite" post.

---

## PL-006 — Column identity is stable, and never reused

**Claim:** "Rename a column, reorder your model, delete a field — the identity
we assign each column never changes and is never handed to a different column.
That is what makes an exported contract safe to depend on."

**Evidence:** `test_ir_roundtrip_sprint2.py`, nine passing properties, of which
three carry the claim: `test_stable_id_is_immutable_across_reorder`,
`test_stable_id_survives_a_rename`, and
`test_stable_id_is_never_reused_after_delete`. Backfill of existing data is
verified separately against real PostgreSQL in
`test_migration_0013_populated.py::test_backfill_assigns_ordinal_ranked_stable_ids`.

**Why it is stronger than it looks — the test was proven to discriminate.**
The no-reuse property is the one a plausible-looking implementation appears to
satisfy: deriving the identity counter from the surviving columns rather than
storing it passes every other assertion and only fails on the sequence *delete
the highest column, save, add a column, save*. That implementation was written
deliberately and run against the suite: **eight of nine tests passed, and only
the no-reuse proof failed.** The test can fail for the reason it claims to
test, which register verification standard 1 requires and which correction C7
showed is not automatic.

**Honest limit:** identity is per entity. Dropping an entity discards its
counter, so an entity recreated under the same name restarts at 1 — asserted
deliberately in `test_dropping_and_recreating_an_entity_restarts_ids`, because
a dropped and recreated table is a new contract rather than a continuation.

**Verified:** 2026-08-11 · **Sprint:** 2 · **Version:** unreleased
**Expires:** on any change to `GraphRepository._persist_columns`,
`_match_existing`, or `_next_free_id`.
**Usable in:** data-contract positioning, Protobuf/wire-compatibility claims
once Sprint 3 consumes the field, "the fix that recreates the bug" post.

---

## PL-007 — Generated dbt projects run as-is, with nothing added

**Claim:** "Export a dbt project and it runs. You supply your warehouse
connection; we supply everything else — models, tests, sources, package
dependencies. No hand-editing to make it parse."

**Evidence:** `test_artifact_fidelity.py::test_dbt_project_is_self_contained`,
5/5 reference models. The project handed to `dbt parse` contains **only**
exporter output plus `dbt_project.yml` and `profiles.yml` — the two files that
are genuinely the consumer's, because only they know their warehouse.

**Why it is stronger than it looks:** the harness previously synthesised a
sources file, because the exporter emitted none and every other dbt defect
would have been masked behind that single failure. When the exporter began
emitting its own, dbt raised `DuplicateResourceNameError` — proving the
scaffolding had been *conflicting*, not merely redundant, and forcing its
deletion rather than its retirement. The property is therefore the strong form:
self-contained because nothing else is present, not because an extra file
happened to agree.

That is also the clearest demonstration of why this suite verifies against real
toolchains rather than assertions. No assertion we could have written would
have distinguished those two cases; dbt distinguished them immediately.

**Honest limit:** `dbt parse` proves the project resolves — models, sources,
tests, dependencies. It does not execute against a warehouse, so it does not
prove the SQL returns what you expect. `dbt build` on generated seed data is
Sprint 4 (register B13).

**Verified:** 2026-08-11 · **Sprint:** 3 · **Version:** unreleased
**Expires:** on any change to `generate_dbt_project`, or if the harness ever
writes a file into the project that the exporter did not emit.
**Usable in:** landing page, export UI, "why we test against tools not strings".

---

## PL-008 — Nothing reaches a model provider without being recorded first

**Claim:** "Every request this appliance makes to a language model is written
to an append-only ledger *before* it is sent. If the ledger cannot be written,
the request is not made. And no code outside the single gateway can reach a
provider at all — that is enforced structurally, not by review."

**Evidence:** `test_egress_choke_point.py`, five tests carrying the claim:

| Property | Test |
| :-- | :-- |
| No module outside the gateway imports a provider SDK | `test_no_module_outside_the_gateway_imports_a_provider_sdk` |
| The scan is not vacuous — the gateway does import one | `test_the_gateway_itself_does_import_one` |
| Exactly one function reaches the provider client | `test_only_one_function_reaches_the_provider_client` |
| The ledger write precedes every statement that reaches it | `test_the_attempt_write_precedes_every_client_statement` |
| A ledger that cannot write stops the request | `test_a_ledger_that_cannot_write_stops_the_request` |

Schema and durability: `test_migration_0015_egress_audit.py`, against a
populated PostgreSQL 16, verified with raw SQL rather than through the ORM.

**Why it is stronger than it looks:** the register originally asked for "a test
proves no path bypasses the ledger", which is a negative over the whole call
graph. No amount of sampling earns it — a test exercising three call sites says
nothing about a fourth added next year. So the claim was converted from
behavioural to structural: if no module outside the gateway can *import* a
provider SDK, and exactly one function inside it touches the client, and the
ledger write precedes every statement in that function which reaches the
client, then completeness holds by construction. The import scan walks the AST,
so a deferred `import openai` inside a function body — the realistic shape of a
bypass — is caught too, which was confirmed by mutation.

All four structural claims were proven failable by mutation before being
relied on. See `docs/sprint-5-progress.md`.

**Honest limits**, each of which would otherwise be read into the claim:

* **There is no operator-facing view yet.** The ledger is queryable SQL. "An
  operator can answer *what left our network* without engineering help" is D4
  and is not built, so this claim must not be stated as a UI capability.
* **Attribution is not yet populated.** `model_id`, `user_id` and
  `workspace_id` exist and are nullable, and the three call sites do not yet
  pass them. Today the ledger answers *what, when, where to* — not *who*.
* **Token counts are best-effort.** Read off the provider response when it is
  shaped as expected, recorded as null when it is not. Recording "unknown"
  honestly beats inventing a number, but they are not a billing record.
* **A failed *outcome* write does not fail the request**, deliberately: by then
  the request has already left, and the ATTEMPT row stands alone saying exactly
  that. A lone ATTEMPT means "we tried and cannot say what happened", not "this
  did not happen".

**Verified:** 2026-08-12 · **Sprint:** 5 · **Version:** unreleased
**Expires:** if any module outside `llm_gateway.py` gains a provider import, if
a second function reaches the provider client, or if the ledger write stops
preceding it. All three are asserted, so expiry is loud rather than silent.
**Usable in:** security FAQ, landing page egress section, regulated-buyer
review. **Not** usable as a claim about a ledger UI.

---

## Claims explicitly NOT yet provable

Recorded so nobody reaches for them early. Each becomes an entry when its test
passes.

| Prospective claim | Blocked on | Sprint |
| :-- | :-- | :-- |
| "Semantic layer exports compile in dbt" | B1 — 24 xfails; MetricFlow parses on 0/5 graphs | 3 |
| "Data contracts are wire-stable" | H6 — Protobuf tags shift when a column is inserted | 3 |
| "Our contracts are valid ODCS" | H2 — stamped v0.9.3, missing required v3.1.0 fields | 3 |
| "Generated test data satisfies the generated contract" | H1 — seed ignores declared lengths and quality rules | 4 |
| "We can *show you* everything that left your network" | D4 — the ledger exists and is recorded (PL-008), but there is no operator-facing view; it is queryable SQL only | 5 |
| "Governed contracts and semantic layers, not just schemas" | B1 + H2 together | 3 |
