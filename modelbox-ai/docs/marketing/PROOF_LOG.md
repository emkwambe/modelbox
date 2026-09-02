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

**Evidence:** `test_artifact_fidelity.py::test_ddl_dialect_grammar`, 24/24
certified cases (4 dialects × 6 gold graphs), zero unparsable segments under
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
release runs all six reference models' DDL against a live DuckDB instance and
asserts the tables that come back are the tables you modelled."

**Evidence:** `test_artifact_fidelity.py::test_ddl_executes_on_duckdb`, 6/6 gold
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
All six reference models are exported twice from a real PostgreSQL 16 — DDL
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
6/6 reference models — and a seventh case, the synthetic `quality-rules`
fixture, so the claim is not resting only on graphs chosen to showcase the
product. The project handed to `dbt parse` contains **only**
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

* ~~**There is no operator-facing view yet.** The ledger is queryable SQL. "An
  operator can answer *what left our network* without engineering help" is D4
  and is not built, so this claim must not be stated as a UI capability.~~
  **Lifted 2026-08-29 — see PL-009.** Struck rather than deleted: the limit was
  true when written and the dates are what make the claim auditable.
* ~~**Attribution is not yet populated.** `model_id`, `user_id` and
  `workspace_id` exist and are nullable, and the three call sites do not yet
  pass them. Today the ledger answers *what, when, where to* — not *who*.~~
  **Lifted 2026-08-29 — see PL-009.** Rows written before that date carry no
  actor and never will; the view reports them as unattributable rather than
  omitting them.
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

## PL-009 — An operator can see what left the network, and what we cannot account for

**Claim:** "Open the egress ledger and see every request this appliance made to
a model provider: when it went, which provider and residency class, whether it
succeeded, how many tokens it cost, and which of your people caused it. Where we
cannot attribute a request, the page says so and counts it rather than leaving
it out."

**Evidence:** `test_egress_ledger_view.py`, six passing tests over the
operator-facing endpoint, and `test_egress_attribution.py`, four over the
attribution that fills it. The pair matters: the second says every call site
records an actor, the first says an operator can read it.

The load-bearing ones are `test_rows_scoping_cannot_show_are_counted_not_dropped`
and `test_a_user_with_no_workspaces_still_learns_of_unattributed_egress`, and
`test_every_call_site_attributes_its_request`.

**Why it is stronger than it looks — the view is required to admit its own
blind spot.** The ledger is workspace data, so the page is scoped by
membership, and rows written before an actor was known belong to no workspace:
scoping returns them to nobody. A view that simply omitted them would let an
operator read "one request left the network" from a ledger holding five, and the
omission is invisible exactly where a governance answer must be complete. The
count is asserted, and hard-coding it to zero — the natural way to write the
endpoint if the gap is not front of mind — fails those two tests and nothing
else.

The attribution guard is structural rather than behavioural, for the reason D3
was re-specified in this sprint: a test exercising three call sites says nothing
about a fourth. It walks the AST of every `structured_completion` call in `app/`
and names the file and line of any that omits an actor.

**Verified against the running appliance, not only in tests.** A live synthesis
on 2026-08-29 produced four attributed rows showing failover from
`anthropic_cloud` (invalid key) to `gemini_cloud`, with 2,311 prompt / 8,292
completion tokens recorded on the success — and the page reported four earlier
rows, written before the attribution wiring existed, as unattributable. The
honest case arrived on its own rather than being staged.

**Honest limits:**

* **Rows written before 2026-08-29 carry no actor**, permanently. They are
  counted, not shown, and no backfill can invent who caused them.
* **Scoping is by workspace membership, not by an operator role.** Someone who
  belongs to no workspace sees no rows — only the unattributable count. There is
  no appliance-wide "see everything" view, so a single operator cannot read the
  whole ledger from the UI unless they are a member of every workspace.
* **Metadata only.** The ledger stores a prompt's SHA-256 and length, never its
  text, and this view does not widen that. It answers *that* something was sent
  and *what it cost*, never *what was said*.
* **Token counts remain best-effort**, inherited from PL-008.

**Verified:** 2026-08-29 · **Sprint:** 5 · **Version:** unreleased
**Expires:** if the endpoint stops reporting `unattributed`, if a call site
reaches the gateway without an actor (asserted structurally, so loudly), or if
any prompt content reaches the response.
**Usable in:** security FAQ, regulated-buyer review, landing page egress
section. **Not** usable as a claim that one person can see every workspace's
egress.

---

## PL-010 — There are two independent ways to stop egress, and both are tested

**Claim:** "You can stop this appliance talking to any external model provider in
two ways that do not depend on each other. Set `AIRGAPPED=true` and every task
resolves to a local runtime, with cloud providers stripped at route resolution
rather than declined later. Or set `MODELBOX_ALLOW_PROVIDER_CALLS=0` and the
gateway refuses before it constructs a client at all. Neither requires deleting
your API keys, and the air-gapped path is tested with every key present."

**Evidence:** `test_airgap_routing.py`, nine passing tests, and
`test_egress_choke_point.py` for the fail-closed gate —
`test_provider_call_without_the_opt_in_is_refused` and
`test_the_refusal_precedes_any_network_attempt`.

**Why it is stronger than it looks — the air-gap suite runs with the keys
loaded.** The obvious way to test air-gapped mode is to unset the credentials,
which proves nothing: a run with no keys cannot reach a provider whatever the
routing does. `test_the_sentinels_are_actually_present` asserts every provider
key is populated with a recognisable sentinel *first*, and
`test_an_airgapped_run_sends_no_cloud_key` then asserts none of them is sent. The
discriminating case is
`test_stripping_is_what_makes_a_fall_through_task_local`: it distinguishes a task
that is local because the routing stripped its cloud options from one that merely
happens to fall through to a local provider, which is the difference between a
control and a coincidence.

`test_a_route_that_would_use_a_cloud_key_is_refused_at_resolution` pins *when*
the refusal happens. Refusing at resolution rather than at the call means the
request is never assembled; the second gate is placed ahead of client
construction for the same reason, since a refusal issued after the SDK has opened
a connection is not a refusal.

**Why the two are independent, and why that matters to a reviewer.**
`AIRGAPPED` is the residency control: it changes which providers a task may
resolve to. The opt-in is a fail-closed library switch: it stops the gateway
regardless of routing or keys. A reviewer can therefore verify one without
trusting the other, and neither is the same mechanism wearing a different name —
`test_airgapped_remains_the_residency_control` asserts the deployment keeps them
distinct.

**Honest limits:**

* **Air-gapped mode needs a local runtime to be useful.** With `AIRGAPPED=true`
  and no local engine running, tasks resolve local-only and then fail. That is
  the correct behaviour and it is not a silent fallback to cloud, but it means
  the mode is a deployment choice, not a switch to flip casually.
* **D7 is about shipping what the defaults name.** Every air-gapped provider
  resolves to a compose service or is declared bring-your-own, and no air-gapped
  primary is BYO — asserted, after a sprint in which the default pointed at a
  container the appliance does not ship.
* **This says nothing about a compromised host.** These are controls over what
  the application does, not a sandbox. An operator with shell on the box can
  make network calls the appliance did not.
* **Neither control encrypts anything.** They govern whether a request is made,
  not what a network observer sees.

**Verified:** 2026-08-29 · **Sprint:** 5 · **Version:** unreleased
**Expires:** if `AIRGAPPED` stops stripping cloud providers at resolution, if the
opt-in stops preceding client construction, or if the two flags collapse into
one. All three are asserted.
**Usable in:** security FAQ, regulated-buyer review, air-gap positioning.
**Not** usable as a claim about host hardening or transport security.

---

## PL-011 — Semantic layer exports compile in the tools that consume them

**Claim:** "Export a semantic layer and the tool parses it. MetricFlow models
resolve inside a real dbt project; Cube schemas are valid JavaScript. Not
'looks right' — parsed by dbt and by a JS engine."

**Evidence:** `test_artifact_fidelity.py::test_metricflow_parses_in_dbt`, 6/6
reference models, and `::test_cube_is_valid_js`, 6/6. MetricFlow is not checked
in isolation: the semantic models are placed in a generated dbt project and
`dbt parse` resolves them together with the models they reference, so a
semantic model naming a table the project does not contain fails. Nine further
MetricFlow tests hold the details that make the parse meaningful rather than
merely successful — `::test_metricflow_declares_agg_time_dimension`,
`::test_metricflow_measures_require_an_aggregation_time_axis`,
`::test_metricflow_ref_matches_dbt_model_name`,
`::test_metricflow_semantic_model_has_primary_entity`,
`::test_metricflow_foreign_entity_names_parent_primary`,
`::test_metricflow_names_avoid_reserved_granularity`,
`::test_metricflow_agg_vocabulary_is_valid`, `::test_metricflow_metrics_have_label`.

**Why it is stronger than it looks:** this claim was on the "not yet provable"
list from Sprint 3, blocked on finding **B1 — MetricFlow parsed on 0 of 5
graphs**, with 24 xfails behind it. It is listed here now because those xfails
are gone, not because the wording softened: the burn-down is `strict=True` from
creation, so every one of them had to be *removed* by a fix that turned the run
red first. The non-preview fidelity leg stands at **0 xfail**.

The distinction between parsing and resolving is the whole point.
`test_metricflow_ref_matches_dbt_model_name` exists because a semantic model
that parses while pointing at a model name the project never emits is a file
that satisfies a parser and breaks a warehouse.

**Honest limit:** **LookML is excluded and is not covered by this claim.** It
carries `@pytest.mark.preview` and a live defect (`M3` — `SUM()` emitted over a
foreign key), and preview dialects are labelled rather than scheduled. "Semantic
layer" here means MetricFlow and Cube. `dbt parse` also resolves rather than
executes: it proves the project is coherent, not that a metric returns the
number a business expects.

**Verified:** 2026-09-01 · **Sprint:** 3 (fix), 6 (claimed) · **Version:** 1.10.0
**Expires:** if any MetricFlow or Cube test regains an xfail, or if LookML is
folded into the claim without leaving preview.
**Usable in:** landing page, semantic-layer positioning, export UI.
**Not** usable as a claim about LookML.

---

## PL-012 — Data contracts are wire-stable across a schema change

**Claim:** "Insert a column into the middle of a table and your Protobuf
contract does not break. Field tags are assigned from server-side stable ids,
not from column order, so a consumer built against yesterday's contract still
decodes today's data."

**Evidence:** `test_artifact_fidelity.py::test_protobuf_tags_stable_on_insert`
and `::test_protobuf_tags_are_the_stable_ids`, 6/6 reference models each, with
`::test_protobuf_compiles` (6/6) handing the output to `protoc`. The insert test
is the load-bearing one: a column is added mid-table and every pre-existing
field's tag is asserted unchanged.

**Why it is stronger than it looks:** this was blocked on **H6 — Protobuf tags
shift when a column is inserted**, which is the defect that makes wire
compatibility a lie rather than a limitation. Tag stability cannot be asserted
by reading one emitted file; it is a property of two, and only a test that
mutates a schema and re-emits can see it. `stable_id` is allocated once by the
server and never reused, which is what gives the emitter something order-
independent to key on — the same field the diff engine uses to tell a rename
from a drop-plus-add.

**Honest limit:** wire stability is claimed for **Protobuf**, where tags are the
compatibility mechanism. Avro is verified to parse (`::test_avro_parses`) but
its compatibility rules are resolution-based rather than tag-based and are not
asserted here. And this is stability across *insertion*: dropping a column is a
breaking change in any encoding, which is what the diff engine reports rather
than something an exporter can prevent.

**Verified:** 2026-09-01 · **Sprint:** 3 (fix), 6 (claimed) · **Version:** 1.10.0
**Expires:** on any change to tag assignment in the Protobuf exporter, or if
`stable_id` ever becomes reusable.
**Usable in:** landing page, contract/governance positioning, integration docs.

---

## PL-013 — Our data contracts are valid ODCS v3.1.0, and say what they mean

**Claim:** "Contracts export as Open Data Contract Standard v3.1.0 — the current
version, with the required fields, and with quality rules that carry the meaning
of the constraint they came from."

**Evidence:** `test_artifact_fidelity.py::test_odcs_apiversion_is_current` and
`::test_odcs_conforms_to_v3_fundamentals`, 6/6 reference models;
`::test_odcs_required_reflects_nullability` and
`::test_odcs_declares_foreign_keys_as_relationships`, 6/6; and the pair the
register calls out as B15 — `::test_odcs_quality_entries_use_v3_vocabulary`
(conformance) with `::test_odcs_carries_the_meaning_of_each_declared_constraint`
(correctness).

**Why it is stronger than it looks:** blocked on **H2 — stamped v0.9.3, missing
required v3.1.0 fields**, so the previous output was a document claiming a
standard it did not meet, which is worse than emitting nothing.

The conformance/correctness split is the part worth understanding. A contract can
use perfectly valid v3.1.0 quality vocabulary and still say the wrong thing —
and the register records the mutant that proves the two tests are independent: a
mutant emitting a well-formed `nullValues` rule in place of the declared pattern
**passes the vocabulary test and fails the meaning test**. One test alone would
have certified it.

**Honest limit:** validity is asserted against the v3.1.0 schema and vocabulary,
not against a consuming platform's interpretation of it. A contract that is
valid ODCS can still be a contract nobody agreed to — which is why the
synthesis prompt refuses to invent tiers, SLAs, ranges and patterns rather than
relying on this gate to catch them.

**Verified:** 2026-09-01 · **Sprint:** 3 (fix), 6 (claimed) · **Version:** 1.10.0
**Expires:** when ODCS publishes a version beyond 3.1.0, or on any change to the
quality-rule emitter.
**Usable in:** landing page, contract positioning, regulated-buyer review.

---

## PL-014 — Generated test data satisfies the contract generated beside it

**Claim:** "The seed data we generate satisfies the data contract we generate
from the same model — lengths, precision, nullability, uniqueness, check
expressions and quality rules. It loads, and `dbt build` passes its tests."

**Evidence:** `test_artifact_fidelity.py::test_dbt_build_succeeds_on_generated_seed_data`
— generated rows are loaded and `dbt build` runs the generated tests against
them. The per-rule assertions are `::test_seed_respects_declared_length`,
`::test_seed_respects_declared_precision_and_scale`,
`::test_seed_never_nulls_a_non_nullable_column`,
`::test_seed_values_are_unique_where_declared`,
`::test_seed_satisfies_an_enumerated_check_expression`,
`::test_seed_respects_quality_rules`, and `::test_seed_generation_order_is_fk_safe`.

**Why it is stronger than it looks:** blocked on **H1 — seed ignores declared
lengths and quality rules**, and the reason it can be claimed now is one test
that is not about seed data at all:
`::test_seed_fixtures_exercise_every_declared_rule` asserts the fixtures contain
a case for **every** rule the generator claims to honour. Without it the suite
could pass by generating data for constraints no fixture declares — a green run
proving that unexercised rules are unbroken.

That is the difference between "the seed satisfies the contract" and "the seed
satisfies the parts of the contract we happened to test."

**Honest limit:** satisfaction is asserted for the constraint families the IR
can express. It is synthetic data — statistically meaningless, and useful for
loading and testing rather than for analysis. `dbt build` runs the generated
tests, not a consumer's own.

**Verified:** 2026-09-01 · **Sprint:** 4 (fix), 6 (claimed) · **Version:** 1.10.0
**Expires:** if a constraint family is added to the IR without a fixture case,
which `test_seed_fixtures_exercise_every_declared_rule` turns red.
**Usable in:** landing page, seed/demo-data positioning, evaluation guide.

---

## Claims explicitly NOT yet provable

Recorded so nobody reaches for them early. Each becomes an entry when its test
passes.

| Prospective claim | Blocked on | Sprint |
| :-- | :-- | :-- |
| ~~"Semantic layer exports compile in dbt"~~ **now PL-011** (2026-09-01), scoped: MetricFlow and Cube only. **LookML is still blocked** — `@preview`, defect M3 | — | 3 |
| ~~"Data contracts are wire-stable"~~ **now PL-012** (2026-09-01), scoped to Protobuf tag stability across a column *insert*; Avro parses but its compatibility rules are not asserted | — | 3 |
| ~~"Our contracts are valid ODCS"~~ **now PL-013** (2026-09-01), with conformance and correctness asserted separately (register B15) | — | 3 |
| ~~"Generated test data satisfies the generated contract"~~ **now PL-014** (2026-09-01) | — | 4 |
| ~~"We can *show you* everything that left your network"~~ **now PL-009** (2026-08-29), with one wording caveat: the view is workspace-scoped, so "everything" is everything *in the workspaces you belong to*, plus a count of what cannot be attributed | — | 5 |
| ~~"Governed contracts and semantic layers, not just schemas"~~ — both blockers are closed: **PL-013** carries the contracts half and **PL-011** the semantic-layer half. It stays listed rather than becoming an entry of its own because it is the *differentiator line*, and register **G5** puts stating it in Sprint 7. The evidence is ready; the wording is a product decision | — | 3 |
