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

**Claim** (reworded 2026-09-28): "Nothing reaches our main branch without every
required check passing: backend tests, lint and type checks, the artifact
fidelity harness, strict TypeScript, a production build, migration and version
gates, a leak guard, and the black-box acceptance suite against the running
appliance. A pull request with one red required check cannot be merged."

**Exercised 2026-09-28:** a throwaway pull request (#8) whose only change was a
deliberately failing test read `BLOCKED`, and `gh pr merge` without `--admin`
refused it ("the base branch policy prohibits the merge"). It was closed
unmerged and its branch deleted.

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

**Honest limit:** ~~`enforce_admins` is off and no reviewer approval is required,
so a repository administrator can still bypass.~~ `enforce_admins` is on as of
2026-09-28 (read back with the command above). No reviewer approval is
required, and an administrator can still change the protection itself.
Suitable for "changes are gated," not for "changes are impossible to force."

**Verified:** 2026-08-11, exercised 2026-09-28 · **Sprint:** 1, 7 · **Version:** 1.6.0
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

**Claim** (reworded 2026-09-28 to its exact evidence): "Every HTTP request this
appliance sends to a language model provider is written to a ledger *before* it
is sent: one row per request, a schema re-ask included, and if the row cannot be
written the request is not made. No code outside the single gateway can reach a
provider; that is enforced structurally, not by review. The application cannot
rewrite the ledger: its database role may read and add rows, and nothing else,
which is proven against the running appliance."

**Evidence:** `test_egress_choke_point.py`, five tests carrying the structure:

| Property | Test |
| :-- | :-- |
| No module outside the gateway imports a provider SDK | `test_no_module_outside_the_gateway_imports_a_provider_sdk` |
| The scan is not vacuous — the gateway does import one | `test_the_gateway_itself_does_import_one` |
| Exactly one function reaches the provider client | `test_only_one_function_reaches_the_provider_client` |
| The ledger write precedes every statement that reaches it | `test_the_attempt_write_precedes_every_client_statement` |
| A ledger that cannot write stops the request | `test_a_ledger_that_cannot_write_stops_the_request` |

Added in Sprint 7:

| Property | Test |
| :-- | :-- |
| One ledger row per HTTP request: invalid JSON twice then valid is three rows, through the real Instructor client | `test_gateway_instructor.py::test_invalid_json_twice_then_valid_is_three_attempt_rows`; negative control `test_negative_control_instructor_retries_hide_requests_from_the_ledger` |
| A failure is recorded by class and structured fields, never the model's output | `test_model_output_redaction.py::test_model_output_reaches_no_ledger_error_or_log`; `test_provider_failure_fields.py::test_a_rate_limit_records_status_type_code_and_retry_after` |
| The application's role cannot update, delete or truncate either ledger (Postgres, raw SQL) | `test_ledger_roles_postgres.py::test_the_app_role_appends_but_cannot_rewrite_either_ledger`; negative control `test_negative_control_an_extra_ledger_grant_fails_the_check` |
| The same, against the running appliance | black-box `test_config_b.py::test_b8_the_application_role_cannot_update_the_egress_ledger`, CI run 36501535008 |

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
* **"Cannot rewrite" is about the application.** The database owner can change
  a ledger by a deliberate schema change, shipped as a migration; root on the
  host is out of scope (`SECURITY_FAQ.md` §6).

**Verified:** 2026-08-12, reworded and extended 2026-09-28 · **Sprint:** 5, 7 · **Version:** unreleased
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

**Against the running appliance** (black-box configuration C, added
2026-09-28, CI run 36501535008): the appliance with `AIRGAPPED=true`, a
sentinel value in every provider key, and every service but the web UI on a
Docker network with no gateway.

| Property | Test (`tests/blackbox/test_config_c.py`) |
| :-- | :-- |
| Precondition: the backend cannot open an outbound connection | `test_c0_the_backend_cannot_reach_outside` |
| The appliance starts and reports itself air-gapped | `test_c1_the_backend_starts_airgapped` |
| A synthesis that names a cloud provider is refused at route resolution | `test_c2_a_cloud_route_is_refused_at_resolution` |
| No ledger row and no routing line: zero outbound attempts | `test_c3_zero_outbound_attempts` |

The precondition is what makes the rest mean something: a box that merely had
no route out would pass C2 and C3 without any control existing.

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

**Verified:** 2026-08-29, against the running appliance 2026-09-28 · **Sprint:** 5, 7 · **Version:** unreleased
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

## PL-015 — An installed appliance refuses the credentials this repository publishes, and publishes one port

**Claim:** "Installed as documented, the appliance will not start until its
four secrets are set, and it names the one that is missing. It has no default
account and no open registration: the first owner is created on the command
line. It refuses a token signed with the development secret published in this
repository. And it publishes one port, the web UI's: the API, the database,
the cache and the local model runtime cannot be reached from the host."

**Evidence against the running appliance** (`tests/blackbox`, CI run
36501535008), with the in-process tests that carry each rule:

| Property | Black-box test | In-process |
| :-- | :-- | :-- |
| Only `.env.example`: compose refuses and names a missing secret, no container is created | `test_config_a.py::test_a_compose_refuses_with_only_the_example_env` | `test_appliance_configuration.py::test_negative_control_a_defaulted_secret_fails_the_check` |
| The development account cannot sign in | `test_config_b.py::test_b1_the_dev_account_cannot_sign_in` | `test_dev_seed.py::test_the_seed_is_refused_outside_development_even_when_asked` |
| A token signed with the shipped secret is refused | `test_config_b.py::test_b2_a_token_signed_with_the_shipped_secret_is_rejected` | `test_config_secrets.py::test_a_shipped_or_short_secret_refuses_to_start` |
| Ports 4000, 8000, 11434, 5432 and 6379 are unreachable from the host | `test_config_b.py::test_b3_only_the_ui_port_is_reachable` | `test_port_surface.py::test_only_the_ui_publishes_a_port` |
| Self-registration is refused | `test_config_b.py::test_b4_self_registration_is_refused` | `test_registration_and_bootstrap.py::test_production_refuses_self_registration` |
| The first owner comes from `create-owner` | the B fixture runs it | `test_registration_and_bootstrap.py::test_create_owner_refuses_a_second_owner` |

**Why it is stronger than it looks — every one of these checks has been seen to
fail.** CI also runs the suite against a committed, test-only insecure profile
that puts the weaknesses back by configuration (development mode, the dev seed,
the shipped JWT secret, open registration, the backend and Ollama ports
published). Against it, B1, B2, B4 and the 8000 and 11434 port checks must
fail, and fail on their own check; a check that passed there would turn the
build red. So none of them is a check that cannot see what it looks for.

**Honest limits:**

* **The web UI's port is plain HTTP.** Terminate TLS in front of it.
* **Root on the host is out of scope.** Someone with root can read `.env`.
* **The shipped database password is refused by settings, not observed from
  outside**: the database publishes no port to probe
  (`test_config_secrets.py`, `test_appliance_configuration.py`).

**Verified:** 2026-09-28 · **Sprint:** 7 · **Version:** unreleased
**Expires:** if any black-box B-check above fails, if the insecure profile stops
making its checks fail, or if the appliance compose file publishes a second port.
**Usable in:** security FAQ, install guide, regulated-buyer review.

---

## PL-016 — Roles and API keys are enforced by the API, and proven from outside

**Claim:** "Every API route declares the minimum role it needs, from VIEWER
through MEMBER, APPROVER and ADMIN to OWNER, and the server enforces it. An API
key acts only in the workspace it was minted in, at no more than the role its
creator gave it and still holds."

**Evidence:**

| Property | Test |
| :-- | :-- |
| Every route, through every included router, declares and enforces a role | `test_route_policy.py::test_every_route_enforces_its_declared_role`; negative control `test_negative_control_an_unguarded_route_in_a_nested_router_fails` |
| Per-role refusals on mutating routes | `test_role_authorization.py::test_editing_the_graph_requires_member`, `test_approving_requires_approver`, `test_deleting_requires_admin` |
| A key is refused outside its workspace, and capped | `test_api_key_scope.py::test_a_key_is_refused_in_another_workspace`, `test_a_viewer_capped_key_cannot_write`; negative control `test_negative_control_without_the_workspace_scope_a_key_reaches_b` |
| A VIEWER's `transform-paradigm` is 403 on the running appliance | black-box `test_config_b.py::test_b5_a_viewer_cannot_transform_a_model` |
| A key minted in workspace A is 403 in workspace B, whose model its creator can read | black-box `test_config_b.py::test_b6_a_key_minted_in_a_is_refused_in_b` |

The authorisation tests sign in with real credentials and never override the
code that decides who the caller is.

**Honest limits:**

* ~~**There is no API or UI to add workspace members or set their roles yet**
  (scheduled for Sprint 8). SCIM provisions people without a role; the
  black-box suite writes its VIEWER membership directly in the database.~~
  **Lifted 2026-09-29 — see PL-024.** Struck rather than deleted: members and
  roles are now managed through the API and the members page, and the
  black-box suite adds its VIEWER through that API.
* **One organisation per appliance.** Workspaces are teams within it; separate
  organisations need separate appliances (`SECURITY_FAQ.md` §5).

**Verified:** 2026-09-28 · **Sprint:** 7 · **Version:** unreleased
**Expires:** if a route lacks a declared role, if B5 or B6 fails, or if a key
acts outside its workspace.
**Usable in:** security FAQ, regulated-buyer review. That roles can be
managed in the product is PL-024's claim.

---

## PL-017 — Sign-ins reach an owner's audit export, and a failed audit write is visible

**Claim:** "Sign-ins and failed sign-ins, SCIM provisioning and the designation
of the appliance owner are recorded, and the appliance owner can export them as
JSONL for a SIEM. If an audit write fails, it is logged as an error and
`/health` reports the appliance as degraded."

**Evidence:**

| Property | Test |
| :-- | :-- |
| The audit sink writes a row with nothing in its path patched | `test_audit_sink_unpatched.py::test_the_unpatched_sink_writes_a_row`; negative control `test_negative_control_without_get_sessionmaker_nothing_is_stored` |
| A failed write is an ERROR and `/health` reads `degraded` | `test_audit_sink_unpatched.py::test_a_failed_write_logs_error_and_degrades_health`; negative control `test_negative_control_without_the_counter_health_stays_ok` |
| Every declared audit action, SCIM provisioning included, is emitted by its code path | `test_audit_actions.py::test_every_declared_action_is_emitted_by_its_path`; negative control `test_negative_control_an_unemitted_action_fails_the_check` |
| The appliance owner reads sign-ins; a plain workspace owner cannot | `test_audit_actions.py::test_the_appliance_owner_reads_logins_and_failed_logins`, `test_a_plain_workspace_owner_is_refused` |
| On the running appliance: `AUTH_LOGIN` and `AUTH_LOGIN_FAILED` in the owner's export, `/health` ok | black-box `test_config_b.py::test_b7_sign_ins_reach_the_owners_export_and_health_is_ok` |
| On a database upgraded from before v1.11.0: `designate-appliance-owner`, then `APPLIANCE_OWNER_DESIGNATED` and `AUTH_LOGIN` in that owner's export | black-box `test_upgrade.py::test_designate_on_an_upgraded_database_reaches_the_owners_export` |

**Honest limits:**

* **The failure count is per process.** The API and the worker each report
  their own; `/health` is the API's.
* **The owner can change the ledgers by a deliberate schema change**, and root
  on the host is out of scope (`SECURITY_FAQ.md` §6).

**Verified:** 2026-09-28 · **Sprint:** 7 · **Version:** unreleased
**Expires:** if the unpatched sink test or B7 fails, or if `/health` stops
reporting audit write failures.
**Usable in:** security FAQ, regulated-buyer review, SIEM integration notes.

---

## PL-018 — DDL import is tested per dialect on genuine exports, and Snowflake is labelled

**Claim:** "ModelBox imports an exported DDL file offline. Oracle and SQL Server
import is certified on genuine exports from those databases' own tools, and
PostgreSQL import on a genuine `pg_dump`. Snowflake import is tested only
against a fixture written from Snowflake's documentation, and is not certified."

**Evidence** (CI run 36644605175 on `main` at `4ea57f7`; the fixtures are
regenerated in fresh containers by the DDL Fixtures workflow, run 36623075855 on
`main`):

| Property | Test |
| :-- | :-- |
| Oracle HR and CO (`DBMS_METADATA`), SQL Server AdventureWorks (SMO) and PostgreSQL Pagila (`pg_dump`) import with no failures and no gaps | `test_ddl_import_fixtures.py::test_the_import_reconciles_with_no_failures_and_no_gaps` |
| What was imported matches each database's own catalog, counted from its catalog views | `test_ddl_import_fixtures.py::test_what_was_imported_agrees_with_the_catalog` |
| AdventureWorks imports identically in UTF-8 and UTF-16, with and without a BOM | `test_ddl_import_fixtures.py::test_adventureworks_imports_identically_in_every_encoding` |
| Every one of AdventureWorks' 1,943 batches is imported or listed; each SQL Server normalizer rule is what makes its case import | `test_ddl_import_sqlserver.py::test_adventureworks_is_1943_batches_each_imported_or_listed`; negative control `test_negative_control_each_rule_disabled_makes_its_case_fail` |
| Only the Snowflake fixture is documentation-derived, and it says so | `test_ddl_fixtures.py::test_only_snowflake_is_documentation_derived`; negative control `test_negative_control_removing_the_documentation_derived_label_fails` |
| Every surface leaves Snowflake import uncertified while its fixture is documentation-derived | `test_ddl_fixtures.py::test_nothing_calls_snowflake_import_certified_while_its_fixture_is_documentation_derived`; negative control `test_negative_control_a_certification_claim_is_found` |
| The Snowflake fixture fails by name on its HYBRID TABLE and is saved unreconciled | `test_ddl_import_fixtures.py::test_the_documentation_derived_snowflake_fixture_fails_by_name_and_is_unreconciled` |

**Honest limits:**

* **The genuine exports are of public sample schemas** (HR, CO, AdventureWorks,
  Pagila), each from the database version its provenance header names. A
  client's schema can use syntax none of them do; the import then names the
  statement it could not read rather than dropping it (PL-019).
* **Tables, columns, keys, constraints, defaults and descriptions are
  imported.** Indexes, sequences, views, procedures and similar objects are
  listed in the report, not imported.
* **Snowflake is not certified**, and cannot be until a genuine `GET_DDL`
  export replaces the documentation-derived fixture.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if any fixture stops reconciling, if the DDL Fixtures workflow stops
reproducing the committed exports, or if the Snowflake fixture is replaced (the
claim is then re-scoped, not extended).
**Usable in:** import page, engagement proposal, technical review. **Not**
usable as a claim about Snowflake certification.

---

## PL-019 — Every import is reconciled against the file, by a counter that shares no code with the parser

**Claim:** "Every DDL import is checked against counts taken from the file
itself by an independent counter. A model is saved *reconciled* only when every
count matches; otherwise it is saved *unreconciled*, and the report names each
gap by statement and line. The report downloads as Markdown or JSON."

**Evidence** (CI run 36644605175 on `main` at `4ea57f7`):

| Property | Test |
| :-- | :-- |
| The independent counter agrees with each database's catalog | `test_ddl_import_fixtures.py::test_the_independent_counter_agrees_with_the_catalog` |
| A statement the importer drops is a gap, named by its statement | `test_ddl_import_core.py::test_negative_control_a_statement_the_importer_drops_is_a_gap_by_statement` |
| An import with a gap is saved unreconciled; a clean one reconciled | `test_ddl_import_api.py::test_an_import_with_gaps_is_saved_unreconciled`, `test_a_member_imports_oracle_hr_and_it_is_stored_reconciled` |
| The report downloads as Markdown and JSON | `test_ddl_import_api.py::test_the_report_downloads_as_markdown_and_json_for_a_viewer` |
| On the running appliance, over HTTP: HR and AdventureWorks show zero gaps in the response, the stored report and the database row read with SQL | black-box `test_config_b.py::test_b10_a_genuine_export_imports_with_zero_gaps` |
| Air-gapped, with no route out: HR reconciles, and nothing is recorded in the egress ledger | black-box `test_config_c.py::test_c4_a_ddl_import_needs_no_route_out` |

**Honest limits:**

* **Reconciliation compares counts**: tables, columns, primary keys, foreign
  keys, UNIQUE and CHECK constraints, and descriptions. Matching counts do not
  prove that every imported value is right; the fixture tests above compare
  values against the catalog, a client's import is compared by count.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if a dropped statement stops being a gap, or if B10 or C4 fails.
**Usable in:** import page, engagement proposal, regulated-buyer review.

---

## PL-020 — Exported PostgreSQL DDL is applied to a real PostgreSQL, and what it cannot state is named

**Claim:** "The PostgreSQL DDL ModelBox exports for an imported schema is run
on a real PostgreSQL 16 in CI, and the resulting catalog is compared with the
source's. Anything the export cannot state is listed as a named gap at the top
of the file, and the shortfall in the catalog equals those gaps."

**Evidence** (Backend Pytest (Postgres) job, CI run 36644605175 on `main` at
`4ea57f7`):

| Property | Test |
| :-- | :-- |
| The job has its PostgreSQL server; the check cannot skip there | `test_ddl_on_postgres.py::test_the_postgres_job_has_its_server` |
| HR, CO, Pagila and AdventureWorks: PostgreSQL accepts the export, and its catalog matches the manifest less the named gaps | `test_ddl_on_postgres.py::test_postgresql_accepts_the_export_and_its_catalog_matches_the_manifest` |
| An invalid export makes the check fail | `test_ddl_on_postgres.py::test_negative_control_an_invalid_export_makes_the_check_fail` |

**Honest limits:**

* **Execution is PostgreSQL only.** Other certified dialects are checked by
  grammar (PL-001), not run.
* **Named gaps are real losses**, for example AdventureWorks' computed
  columns, and sequence defaults and user-defined types the model does not
  hold. They are stated in the file; they are not supplied.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if PostgreSQL refuses an exported file, if the shortfall differs
from the named gaps, or if the PostgreSQL image pin changes without a re-run.
**Usable in:** export UI, technical review.

---

## PL-021 — "Verified" in a data dictionary means three stated conditions, checked by the server

**Claim:** "A dictionary field is marked verified only when an approver asks,
the model is a reconciled import, the field's definition passes the
machine-checkable rules of ISO/IEC 11179-4, and its provenance is recorded and
is not an AI draft. A verified value that changes returns to pending review.
No one can set 'verified' directly."

**Evidence** (CI run 36644605175 on `main` at `4ea57f7`):

| Property | Test |
| :-- | :-- |
| All three conditions verify a field | `test_dictionary_verification.py::test_a_reconciled_import_with_a_sound_definition_and_provenance_verifies` |
| Each condition alone refuses, and each refusal is its own condition | `test_an_unreconciled_import_keeps_a_field_unverified`, `test_a_definition_failing_the_11179_rules_keeps_a_field_unverified`, `test_a_value_without_provenance_keeps_a_field_unverified`, `test_an_ai_draft_is_never_verified`; negative control `test_negative_control_each_refusal_is_its_condition` |
| An edited verified value returns to pending | `test_dictionary_verification.py::test_editing_a_verified_value_makes_it_pending` |
| A request that states a status is refused | `test_dictionary_verification.py::test_setting_verified_directly_is_refused` |
| The database refuses a verified row without a reviewer, time and provenance | `test_the_database_refuses_a_verified_row_without_a_reviewer`; negative control `test_negative_control_without_the_provenance_condition_the_database_refuses` |
| The dictionary says verified only where the attestation does | `test_dictionary_verification.py::test_the_dictionary_shows_verified_only_where_the_attestation_says_so` |
| In a browser, on the running appliance: verify a field, see the counts change, edit it back to pending; an unreconciled import's fields are refused | Engagement Journey (PL-025) |

**Honest limits:**

* **Only the machine-checkable rules of ISO/IEC 11179-4 are applied.** The rest
  of the standard is judgement; passing these rules does not claim it, and
  "verified" does not claim a definition is correct for the business.
* **Values saved before this release are "recorded"**, with no provenance, and
  cannot be verified until someone supplies them again.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if any condition can be bypassed, or if an edited value stays
verified.
**Usable in:** dictionary export, engagement proposal, regulated-buyer review,
in the words "definitions, owners, sources and validation rules of the kind
BCBS 239 expects". **Not** usable as a compliance claim.

---

## PL-022 — The drift report finds exactly the drift a real database was given, classified by written rules

**Claim:** "The drift report compares a saved model with a DDL export of the
deployed schema. On real Oracle, SQL Server and PostgreSQL databases altered by
committed scripts, it reports exactly the drifts each script makes, and
classifies each as breaking, non-breaking or informational by nineteen rules
published in the user guide. A drift touching a verified dictionary field is
flagged, and an unreconciled import is warned about first."

**Evidence** (CI run 36644605175 on `main` at `4ea57f7`; the drifted exports are
produced by the DDL Fixtures workflow, run 36623075855 on `main`):

| Property | Test |
| :-- | :-- |
| HR (Oracle), AdventureWorks (SQL Server), Pagila (PostgreSQL): exactly the expected drifts, each classified as its hand-written manifest says | `test_drift_fixtures.py::test_the_report_finds_exactly_the_expected_drifts`; negative controls `test_negative_control_a_suppressed_drift_category_fails`, `test_negative_control_a_broken_classification_rule_fails` |
| A baseline against itself has no drift | `test_drift_fixtures.py::test_a_baseline_against_itself_has_no_drift` |
| The drifted exports are genuine tool output | `test_drift_fixtures.py::test_the_drift_fixtures_are_genuine_tool_output` |
| Every rule has a case and every drift kind a rule; the user guide lists each rule with its text and class | `test_drift_rules.py::test_each_rule_classifies_its_case`, `test_every_rule_has_a_case_and_every_kind_a_rule`, `test_the_user_guide_lists_every_rule_with_its_text_and_class`; negative control `test_negative_control_a_broken_rule_changes_its_class` |
| Columns pair by name, never by internal identity | `test_drift_report.py::test_column_identity_is_never_used_to_pair` |
| The verified-field flag, and the unreconciled warning first in every format | `test_drift_report.py::test_a_drift_on_a_verified_field_is_flagged`, `test_an_unreconciled_import_says_so_at_the_top_of_every_format`; negative control `test_negative_control_an_unverified_field_is_not_flagged` |
| In a browser: the drifted HR export's rows match the manifest by kind, place and class, and only the drift on a verified field is flagged | Engagement Journey (PL-025) |

**Honest limits:**

* **Renames are not detected.** A renamed column is a removal and an addition;
  a "possible rename" hint is only a hint.
* **It compares what DDL states**: tables, columns, types, nullability,
  defaults, keys, constraints and descriptions. Data, indexes and grants are
  not compared.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if a fixture's report differs from its manifest, or if a rule
changes class without its manifest and the user guide changing with it.
**Usable in:** engagement proposal, drift report page, technical review.

---

## PL-023 — A migration says, in the DDL and on screen, which statements drop data

**Claim:** "Every statement in a generated migration that drops data says so in
the SQL and in the diff panel. A column is renamed only between versions of the
same model; between separately saved models, columns pair by name, so an
uncertain rename is shown as a removal and an addition, with the removal's data
loss stated."

**Evidence** (CI run 36644605175 on `main` at `4ea57f7`):

| Property | Test |
| :-- | :-- |
| Separately saved models pair by name, so an added column is an addition | `test_diff_engine.py::test_separately_saved_models_pair_by_name_so_an_added_column_is_an_addition`; negative control `test_negative_control_id_pairing_across_models_brings_the_false_rename_back` |
| The endpoint never renames across separately saved models | `test_diff_engine.py::test_the_diff_endpoint_never_renames_across_separately_saved_models` |
| An uncertain rename is a drop and an add, and the migration says so | `test_diff_engine.py::test_an_uncertain_rename_is_a_drop_and_an_add_and_the_migration_says_so` |
| A dropped table says its data goes too | `test_diff_engine.py::test_a_dropped_table_says_its_data_goes_too` |
| The diff panel names each column whose data is dropped | `DiffPanel.test.tsx` "says the migration drops data, naming each column"; negative control "no alert when nothing is dropped" |

**Honest limits:**

* **The migration is generated, not run.** Whether to apply a statement that
  drops data is the reader's decision; the product states the loss, it does not
  prevent it.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if a dropping statement lacks its data-loss line, or if the diff
renames across separately saved models.
**Usable in:** migration page, technical review.

---

## PL-024 — Workspace members and roles are managed in the product, within guards the server enforces

**Claim:** "A workspace OWNER or ADMIN adds existing users, changes their roles
and removes them, through the API and the members page. No one grants a role
above their own, an ADMIN cannot make an OWNER, a workspace always keeps an
OWNER, and a removed member's API keys stop at once."

**Evidence** (CI run 36644605175 on `main` at `4ea57f7`; authorisation tests sign
in with real credentials):

| Property | Test |
| :-- | :-- |
| An owner adds an existing user; an email with no user is refused by name | `test_members.py::test_an_owner_adds_an_existing_user`, `test_an_email_with_no_user_is_refused_by_name` |
| An admin changes a role and removes a member; a member cannot manage members | `test_members.py::test_an_admin_changes_a_role_and_removes_a_member`, `test_a_member_cannot_manage_members` |
| An admin cannot make an owner | `test_members.py::test_an_admin_cannot_make_an_owner`; negative control `test_negative_control_without_the_rule_an_admin_makes_an_owner` |
| The last owner can never be demoted or removed | `test_members.py::test_the_last_owner_can_never_be_demoted_or_removed`; negative control `test_negative_control_without_the_guard_the_last_owner_goes` |
| A removed member's keys stop at once | `test_members.py::test_a_removed_members_keys_stop_at_once`; negative control `test_negative_control_a_membership_read_once_would_keep_the_key` |
| The members page: its controls follow the viewer's role | `src/app/settings/members/page.test.tsx` (7 tests) |
| On the running appliance, the black-box suite adds its VIEWER through the members API | black-box `conftest.py` `world`, used by B5 and B6 (PL-016) |

**Honest limits:**

* **The members API adds existing users only.** Users come from OIDC, SCIM or
  `create-owner`.
* **One organisation per appliance**, as in PL-016.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if any guard above can be bypassed, or if a removed member's key
still acts.
**Usable in:** security FAQ, regulated-buyer review, admin guide.

---

## PL-025 — One consultant engagement runs end to end in a real browser on every change

**Claim:** "On every change, CI starts the appliance as installed, and a
browser walks one engagement: sign in, import the genuine Oracle HR export
(zero gaps), edit and save dictionary fields that survive a reload, verify a
field and see it lapse on edit, compare a drifted export, and export
PostgreSQL DDL. The same run shows a documentation-derived Snowflake import
warned about first and refused verification."

**Evidence:** `e2e/tests/journey.spec.ts`, run by the required **Engagement
Journey** check against the appliance in configuration B, with the owner made
by `create-owner`; on `main` at `4ea57f7`, CI run 36644605175: `2 passed`, no
retries.

**Honest limits:**

* **One browser (Chromium), one engagement.** It exercises the path a
  consultant takes, not every screen.
* **It runs in CI**, against images built from the commit; published images are
  checked by the Verify Release workflow.

**Verified:** 2026-09-29 · **Sprint:** 8 · **Version:** unreleased
**Expires:** if the Engagement Journey check fails or stops being required.
**Usable in:** engagement proposal, technical review.

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
