# Sprint 5 progress — governance that holds

**Started mid-sprint, and that is the point.** Sprints 2–4 each wrote their
progress doc at close. Sprint 5 lost a session to a machine restart with Task 1
uncommitted, and the reconstruction that followed recovered the code but not the
reasoning: of three mutants that had proven Task 1's structural tests failable,
**one survived and two did not.** The one that survived was written into the
docstring of the test it validated. The two that were lost existed only in chat.

That is a general rule, not an anecdote about a restart:

> A mutant recorded in the test it validates survives context loss. One recorded
> in a message does not.

So mutation results go in this file as they happen, and the load-bearing ones
also go in the docstring of the test they justify. This file is written to at
every commit boundary, not at sprint end.

---

## Current state — last verified 2026-08-12, at `Task 5 harness`

A recorded baseline, so a restart can tell whether a number *moved* rather than
only what it is. A count that differs from this table is a finding, and the
commit that moved it is where to look.

| Measure | Value | How |
| :-- | :-- | :-- |
| App suite | **549 passed, 36 skipped, 18 xfailed** | `cd backend && .venv/Scripts/python -m pytest -q` |
| Fidelity, non-preview xfails | **0** | `MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m "not preview" -q` |
| Fidelity, preview xfails | **18** | same, with `-m "preview"` |
| Ruff over `app` + `tests` | **69**, all pre-existing | `.venv/Scripts/python -m ruff check app tests` |
| Verification standards | **14** | `docs/ModelBox_AI_Acceptance_Criteria.md` |

The app suite spins up a disposable PostgreSQL via Docker (migrations 0013 and
0015) and takes ~2 minutes. The 36 skips are the fidelity tests, which need
`.venv-tools`.

---

## Task 0 — Verify the scorer, before anything depends on it

**Done.** Commit `a42fbd4`. `backend/tests/test_linter_discrimination.py`.

Thirteen linter codes, each with a graph that must trigger it and a
near-identical graph that must not. **All thirteen discriminate.** No finding
outranks the sprint.

Proven failable, since the discrimination file is itself a guard (standard 13):

| Mutant | Caught by |
| :-- | :-- |
| `PII_EXPOSURE` fires unconditionally | the silence half |
| `MISSING_DESCRIPTION` never fires | the trigger half |
| a fourteenth code with no case | the coverage test |

The third has the longest life: the coverage test reads emit sites out of
`graph_engine.py` by regex rather than restating a count, so a new code added
without a discrimination case fails immediately. Standard 11 applied to the
instrument — it cannot grow a blind spot while three claims lean on it.

**Correction recorded at the time:** a grep was read as suggesting
`MISSING_DESCRIPTION` and `PII_EXPOSURE` had never fired. That was true of the
test suite and false of the linter. The grep measured coverage, not capability.
The codes were untested, not broken.

---

## Standard 12 gains a third form

**Done.** Commit `9cf422b`, deliberately committed alone and ahead of Task 1.

`allow_provider_calls` was declared with a bare `validation_alias`, which
*replaces* the field name — so `Settings(allow_provider_calls=True)` bound
nothing and returned the default. Not absent, not empty: **unsettable**, while
every line of calling code read as correct. The failure direction was
permissive: the fail-closed egress gate would have been open on a deployment
that had explicitly closed it.

Absence, emptiness and unreachability all produce the same vacuous
satisfaction. Assert the expected value exists *and* that setting it changes the
outcome.

---

## Task 1 — Egress ledger (B3, D3)

**Done.** Files:

| File | Role |
| :-- | :-- |
| `alembic/versions/0015_add_egress_audit.py` | the table |
| `app/models/metadata_store.py` | `EgressAudit` |
| `app/services/egress_ledger.py` | the sink, and the three rulings |
| `app/services/llm_gateway.py` | `_call_provider` — the choke point |
| `tests/test_egress_choke_point.py` | structure and behaviour |
| `tests/test_migration_0015_egress_audit.py` | schema, against a real populated DB |
| `tests/_egress_doubles.py` | recording and failing sinks |

### How D3 was earned

The register asked for "a test proves no path bypasses the ledger" — a negative
over the whole call graph, unearnable by sampling. Converted to three structural
claims that compose into the universal:

1. no module outside `llm_gateway.py` imports a provider SDK (AST scan, so a
   deferred import inside a function body is caught too);
2. exactly one function inside it reaches `self.client`;
3. the ledger write is a statement of that function's own body, preceding every
   statement that reaches the client — so no branch, early return or handler can
   skip it.

Plus the discriminating half of (1): the gateway *does* import one, or the scan
would pass equally on a codebase with no LLM support at all.

### Rulings

**The attempt is written before the call, and a failed attempt-write blocks the
call.** No record, no request — the same fail-closed shape as
`allow_provider_calls`. Writing after the call would lose every request that
left and then crashed; writing best-effort would make the ledger a success log
with an unknown number of gaps and no way to detect them.

**A failed *outcome* write does not block anything.** The request has already
left; raising would neither un-send it nor improve the record, and would turn a
logging fault into a visible failure of work that succeeded. The lone ATTEMPT
row is left standing and means exactly "we tried, and we cannot say what
happened".

**One row per event, never an UPDATE.** An update lets a later write revise the
record of something that already left the network — the one thing an audit trail
must not permit. The outcome is a second row correlated by `attempt_id`.

**One attempt per provider, not per call.** A failover to a cloud fallback is a
second request that left the network, and the ledger shows two. The plausible
wrong implementation records one row per `structured_completion` call, which
understates egress in exactly the direction that flatters the product.

**A ledger error is never failed over.** An unrecordable request is
unrecordable on every provider, so `EgressLedgerError` is re-raised ahead of the
generic failover handler. Otherwise a broken ledger produces a chain of
unrecorded requests and then reports "all providers exhausted" — the loudest
possible symptom of the quietest possible failure, described as the wrong thing.

**The write commits in its own transaction, and the table carries no foreign
keys.** Egress is not undone by a rollback, and deleting a workspace must not
erase the record of what that workspace sent. Both are deliberate deviations
from the conventions used everywhere else in this schema, which is precisely why
each has a test defending it.

**The prompt is hashed, not stored.** The ledger answers what left, when and to
whom, and lets an operator prove a specific text was or was not sent, without
becoming a second copy of the data the governance story exists to protect.

### Mutation results

Every structural claim above was mutated and observed failing before being
relied on. Migration mutants ran against a real populated PostgreSQL 16.

| # | Mutant | Killed by | Note |
| :-- | :-- | :-- | :-- |
| 1 | Gate moved one line below `self.client` | `test_the_refusal_precedes_any_network_attempt` | **1.3s → 55s.** Constructing the client genuinely imports litellm and instructor, so the 40× gap is the measured evidence the ordering does work. Recorded in the test's own docstring. |
| 2 | `record_attempt` moved after the provider call | 5 tests, incl. `test_the_attempt_write_precedes_every_client_statement` and `test_a_ledger_that_cannot_write_stops_the_request` | The AST test catches the shape; the fail-closed test catches the consequence. |
| 3 | `except EgressLedgerError: raise` removed from the failover loop | `test_a_ledger_failure_is_not_failed_over`, `test_a_ledger_that_cannot_write_stops_the_request` | Symptom observed: a ledger fault reported as `LLMRouterError` "all providers exhausted", after both providers were tried. |
| 4 | Deferred `import openai` in a new module under `app/services/` | `test_no_module_outside_the_gateway_imports_a_provider_sdk` | Confirms the AST walk catches function-body imports, not just the import block. |
| 5 | Cascading FK `egress_audit.workspace_id → workspaces` added to 0015 | `test_the_ledger_carries_no_foreign_keys`, `test_deleting_a_workspace_does_not_erase_what_it_sent` | The behavioural test caught the actual harm — the row was erased — not merely the constraint metadata. |

Mutants 2–5 were run this session. Mutant 1 is recovered from the docstring it
was written into.

**Two mutants are lost.** The pre-restart session ran three against Task 1's
structural tests. Only the ordering mutant was preserved, in a docstring. The
other two were run and not recorded, and are not reconstructed here — a
plausible guess written down as history would be worse than the gap, because it
would read as evidence. What is honestly claimable: **Task 1's structural tests
carry one mutant recovered from the previous session and four run and recorded
in this one.** That is sufficient for D3 on its own; the two lost ones are a
process finding, not an evidence gap.

### Migration 0015 verified against a populated database

`MODELBOX_MIGRATION_STRICT=1`, PostgreSQL 16 in Docker, 5 tests passing.
Populated *before* the upgrade — 0014, seed the gold models, then 0015 — because
applying it to an empty schema exercises the DDL and nothing else.

`alembic current` is read back rather than inferred from an exit code, via the
imported `_upgrade_to` helper. **Imported, not copied:** that helper carries the
M1 fix (it resolves what `head` actually is instead of comparing against `""`),
and a second hand-written copy of a read-back guard is exactly how that defect
would return in a new disguise.

The revision id is 21 characters and `alembic_version.version_num` is
`VARCHAR(32)`. Only a real database can establish that it fits; it does.

Shape is asserted from `information_schema` rather than through the ORM — the
model and the migration are two independent statements of the same schema, and
reading the table back through the model that declares it would let them agree
with each other while both differed from the database.

### Honest limits, carried into PL-008

* **No operator-facing view.** The ledger is queryable SQL. D4 is not built, so
  "we can *show* you what left your network" is still listed as not provable.
* **Attribution is not populated.** `model_id` / `user_id` / `workspace_id`
  exist, are nullable, and the three call sites do not yet pass them. Today the
  ledger answers what, when and where to — not who.
* **Token counts are best-effort**, read off the provider response when its
  shape is recognised and null otherwise. Not a billing record.
* **Append-only is a code property, not a database constraint.** Nothing at the
  DDL level prevents an UPDATE; what exists is a schema with no update path and
  a sink that only inserts. Worth stating plainly rather than implying the
  database enforces it.

### Suite effect

Two existing tests in `test_egress_logging_and_masking.py` now inject a
recording sink, because a gateway with the default database ledger refuses in a
suite that has no database — which is the fail-closed rule working, observed
live. Both were strengthened while being adapted: they previously asserted
against the Sprint 1 log line, and now also assert against the ledger itself.
`test_airgapped_routing_never_records_a_cloud_provider` was written in Sprint 1
saying "whatever the Sprint 5 ledger records, it must not name a cloud
provider"; it now does exactly that.

---

## Task 2 — Per-task residency (D5) and typed failover (D8)

**Done.** `config/model_router.yaml`, `app/services/llm_gateway.py`,
`tests/test_egress_residency_and_failover.py`.

D5 and D8 look independent and share a failure mode: **something absent read as
something permitted.** D5's version is a task with no residency pin routing
wherever it likes; D8's is an unclassified exception retried as though it were
transient. Both are standard 12, and both are now asserted explicitly rather
than inferred from a happy path.

### The finding: `max_egress_class` cannot be a scalar

The prompt specifies `max_egress_class`, which reads as a position on a scale.
**Residency is not a scale.** Over `{local, cloud_eu, cloud_apac, cloud}` any
total order asserts either `cloud_eu ≤ cloud_apac` or the reverse, and both are
false as residency controls: an EU-pinned task must not fail over to APAC, and
an APAC-pinned task must not fail over to the EU. A scalar comparison gets
exactly one of those wrong, silently, in the permissive direction.

So the permitted set comes from a **declared containment map** in
`egress_policy`, never from an inferred ordering. `local` appears in every set
because a local provider is at least as restrictive as any cloud one; `cloud` is
the top. `test_an_eu_pin_does_not_admit_apac_and_an_apac_pin_does_not_admit_eu`
is the assertion a scalar implementation cannot pass.

The name `max_egress_class` is kept — it is what the register and the prompt
say, and the semantics are documented where it is declared.

### Enforced twice, deliberately

`resolve_route` filters the chain; `_call_provider` re-checks the individual
request. Not redundant: the first proves the *chain* is compliant, the second
proves the *request* is, in the same function that reaches the provider and
after every other decision. A check living only upstream is defeated by anything
mutating the chain in between, and nothing at the call site can distinguish
"validated" from "never validated".
`test_the_residency_check_lives_in_the_calling_function` pins it there by AST —
the instrument built for D3, applied to a different claim.

### Rulings

**A task with no pin fails loudly.** There is no permissive default. An absent
residency constraint read as "no constraint" is indistinguishable at the call
site from a constraint that was checked and passed.

**A pin naming an undeclared class fails loudly**, rather than admitting
everything or nothing. Both silent readings of a typo are wrong.

**Governance refusals never fail over.** `EgressLedgerError`,
`EgressResidencyError` and `EgressPolicyError` propagate past the failover
handler. A residency refusal that failed over would walk the chain looking for
someone to take the request — the breach the pin exists to prevent, performed by
the enforcement mechanism.

**An unclassified provider failure abandons the chain.** The reflex is to treat
an unrecognised failure as transient and try the next provider. We do not know
that continuing is safe, so we do not continue. The remedy is a one-line entry
in `_FAILURE_SIGNATURES`, which leaves a record of the decision.

**Failover decisions are looked up by subscript, not `.get()`.** A
classification added without deciding its failover behaviour raises at the
decision point instead of inheriting "retry".

**The reported error is the one that most needs acting on, not the last one.**
A chain ending on a 429 whose first provider had an invalid key is reported as
`ProviderAuthError` — otherwise an operator goes to a quota dashboard for a
problem in their environment file. That is the concrete harm D8 names.

**Classification is by exception class name, walking the MRO**, so the gateway
stays importable without the provider SDKs. The cost is that a renamed provider
exception drops to unclassified — which aborts rather than fails over, so the
failure direction of the shortcut is safe.

### Production config

Every task now declares a pin, and `test_the_production_router_pins_every_task`
asserts it against the shipped file rather than a fixture (standard 11). All
five are declared `cloud`, which is the truthful statement about where those
chains route today — the pin strips nothing yet.

### Decision deferred: tightening the pins waits for Task 5

**Ruled, so it does not become permanent through inaction.**
`unstructured_doc_parsing` carries customer PRD text and lists `kimi_cloud`
(APAC) among its fallbacks. It is the right first candidate for a tighter pin
and it is **not** being tightened yet.

The reason is that narrowing a chain has a cost nobody has measured: removing
fallbacks may degrade that task's output quality, and there is no data on how
much until Task 5's conformance harness scores providers against the gold
graphs. Tightening now would be guessing; tightening after conformance data
would be informed. So the decision is deferred to **post-Task-5**, with the
mechanism already built and proven.

D5's mechanism being proven but unexercised in production is an honest state to
be in for one more task. It is recorded here rather than left implicit, because
a deferred decision that nobody wrote down is indistinguishable from a decision
nobody made.

### `EGRESS_EVENTS` wired

The vocabulary had three homes — the constant, string literals in the sink, and
the migration's CHECK — with nothing enforcing agreement. Same shape as the
three `_is_temporal_type` predicates whose disagreement was the Cube bug.

Now: the model generates its `CheckConstraint` from the tuple, the sink and the
test doubles import the names, the sink rejects an unknown event before it
reaches the database, and the recording double asserts the vocabulary too — a
double that accepted anything would let a typo pass every test here and fail
only against the real constraint, in production.

The migration keeps its frozen literal, because a migration must not import
application code that can change under it.
`test_the_migration_check_matches_the_declared_vocabulary` holds the two
together instead.

### Mutation results

| # | Mutant | Killed by |
| :-- | :-- | :-- |
| 6 | Residency checked on `chain[0]` only | 3 tests, incl. the prompt-named `test_a_pin_strips_non_compliant_failover_targets` |
| 7 | Residency check removed from `_call_provider` | the AST test *and* both behavioural refusal tests |
| 8 | `UnclassifiedProviderError: True` in `_MAY_FAIL_OVER` | `test_an_unmapped_failure_abandons_the_chain` |
| 9 | Missing pin defaults to `"cloud"` | `test_a_task_without_a_pin_is_a_configuration_error` |
| 10 | A fourth event added to `EGRESS_EVENTS` | `test_the_migration_check_matches_the_declared_vocabulary` |

Both mutated files were restored and diffed byte-identical against a
pre-mutation copy before the suite was re-run.

### Suite effect

Two router fixtures gained an `egress_policy` block and per-task pins, because
the fail-loud policy refuses an unpinned task — the rule working, observed in
the suite before any production config saw it. One failover test was switched
from a bare `RuntimeError` to a name-classified `RateLimitError`: since Task 2
an unrecognised exception abandons the chain, so the old fixture would have
tested the abort path while claiming to test failover (standard 8 — a test
whose fixture stops exercising the feature it names).

---

## Task 3 — Air-gapped mode that proves itself (D6, D7, Q1)

**Done.** `config/model_router.yaml`, `tests/test_airgap_routing.py`. No
application code changed — the defects were in configuration and in what was
being asserted about it.

### D6 inverted

The criterion read "runs end to end with no cloud keys present", which passes on
a box that simply never had any keys configured. Green on a developer laptop for
a reason unconnected to air-gapped mode working — standard 12, an absent input
read as satisfaction.

Inverted: the test **sets every provider key to a distinct sentinel** and
asserts none was used, every route resolved local-only, and a route that would
have needed one was refused. Absence is loud, because the keys are present,
usable, and provably untouched. `test_the_sentinels_are_actually_present` guards
the inversion itself — without it the whole file could pass on an empty
environment, which would have rebuilt the original defect one level up.

The leak assertion reads **what was handed to the provider call**, not what the
router intended. Keys are attached in `_litellm_kwargs`, after resolution, so a
resolution-only assertion cannot see one.

### D7: the appliance's default pointed at a container it does not ship

`airgapped_vllm` was the air-gapped primary for two tasks, and its host
`vllm-server.internal` is not a service in
`docker/docker-compose.appliance.yml` — nothing in this repository creates it.
The out-of-the-box air-gap path depended on infrastructure the appliance neither
shipped nor documented, and failed at runtime with a DNS error.

Now: every primary is `local_ollama` (the shipped `ollama-engine`, compose
profile `airgap`), `airgapped_vllm` is marked `byo: true` and is a fallback
only, and `socratic_tutoring` gained an explicit override rather than falling
through. Two tests hold it: every air-gapped provider is either a compose
service or declared BYO, and **no primary may be BYO** — the discriminating
half, since marking everything BYO would satisfy the first while leaving the
appliance just as broken.

`test_the_shipped_local_runtime_is_reachable_from_the_backend` asserts
reachability rather than the service name, because a service can be present and
unreachable. The default-network case is asserted as a property rather than
skipped when trivially true: `if networks: assert ...` would verify nothing
today and keep verifying nothing the day someone adds a network to one service
only.

### Mutation results — and one that found a defect in these tests

| # | Mutant | Killed by |
| :-- | :-- | :-- |
| 11 | BYO provider restored as an air-gapped primary | `test_no_airgapped_primary_is_bring_your_own` |
| 12 | `byo: true` removed from `airgapped_vllm` | `test_every_airgapped_provider_exists_or_is_declared_byo` |
| 13 | Air-gap falls back to the cloud chain when nothing is local | `test_a_route_that_would_use_a_cloud_key_is_refused_at_resolution` |
| 14 | Air-gap stripping disabled entirely | **initially only 1 test — see below**; now 2 |

**Mutant 14 is the useful one.** Disabling air-gap stripping altogether left
seven of eight tests green, because every task in `airgapped_overrides` already
lists local providers only. The D6 assertions were passing for a reason that had
nothing to do with air-gap enforcement working — standard 8, in tests written to
close a standard 12 hole.

The production config cannot supply the discriminating case, precisely because
it is now correct. So `test_stripping_is_what_makes_a_fall_through_task_local`
supplies it: a task with **no** override, falling through to `task_routing`,
where stripping is the only thing between a cloud provider and a sentinel key.
With it, mutant 14 dies twice.

Worth stating as a general shape: **a config made correct stops being a test
fixture for the mechanism that corrects it.** Fixing Task 3's routing removed
the only case that exercised the stripping.

---

## Task 4 — Cross-artifact consistency gate (standard 10)

**Done, and it found a real defect on its first run.**
`tests/test_cross_artifact_consistency.py`, 39 tests.

### The defect: Avro read the wrong IR field

`_avro_schema` decided nullability from `col.is_primary_key`, not
`col.is_nullable` — the comment even said "non-key columns are nullable". So a
column declared `NOT NULL` in DDL and `required: true` in ODCS was emitted as a
nullable `["null", T]` union in Avro. Three artifacts, same IR field, two
answers.

**It was invisible to every test that existed**, because on all five gold graphs
every primary key is non-nullable and every non-key column is nullable —
`not is_nullable` and `is_primary_key` are the same partition. That is
correction C7, and this is the third time it has cost something. The mutated
fixture that exists precisely for it is what exposed the defect, on the first
run of the gate, before any mutation was attempted.

Fixed in the same commit, with the reasoning at the site.

### Shape, as designed

A projection reads one IR field out of one emitted artifact:
`(artifact, field) → {(entity, column): value}`. The gate groups **by IR field**
and asserts all projections agree. No pair is named anywhere. Currently:
`is_nullable` from four DDL dialects + ODCS + Avro; `is_primary_key` from four
DDL dialects + ODCS.

Everything parses — sqlglot for DDL, yaml for ODCS, json for Avro. Never
substrings.

**Venue changed from the design: the app suite, not `.venv-tools`.** The design
assumed Avro and Protobuf projections would need `fastavro` and `protoc`. They
do not: an `.avsc` *is* JSON, so `json.loads` is the correct parse for
structure, and Protobuf turned out to carry no nullability at all (below). Every
current projection parses with tools present in `.venv`, so the gate runs on
every commit rather than only under the fidelity harness — strictly better
coverage. Artifact *validity* is still asserted against each consumer's own
parser in `test_artifact_fidelity.py`; this gate assumes it.

### The second finding: Protobuf carries no field presence

proto3 emits no `optional` keyword, so every scalar field has implicit presence
and the artifact says nothing about nullability. It therefore has no
`is_nullable` projection — and that is recorded as a finding rather than an
omission. `test_protobuf_carries_no_field_presence` **fails the day the emitter
starts emitting `optional`**, which is the day a projection should be added.

Whether the emitter *should* emit `optional` is a product decision, not a
mechanical one, and is left open.

### Breadth, closed from both ends

* IR side: every `ColumnSchema` field carries ≥2 projections or a written
  `EXEMPT` reason. Enumerated from `model_fields`, so a new field fails until
  someone decides.
* Artifact side: contract formats are discovered by asking the exporter what it
  accepts, not from a list, so a fifth format cannot arrive uncovered.
* **A field with exactly one projection is a failure**, not a pass.
* Exemptions carry reasons; `test_no_exemption_is_silent` also fails on a stale
  exemption for a field the IR no longer has.
* `test_each_field_actually_varies_across_the_fixtures` — a projection over a
  constant proves nothing, so the fixtures must make each field vary.
* `test_entity_names_canonicalise_injectively` — the join canonicalises
  `DimCustomer` to `dim_customer`, and must never merge two entities.

`data_type` is exempt with the stated reason: each artifact renders its own type
system, equality across them is not the property, and a comparison would have to
be loosened until it passed.

### Mutation results

| # | Mutant | Killed by |
| :-- | :-- | :-- |
| 15 | *(not a mutant — the real Avro defect)* | the gate itself, first run, 5 models |
| 16 | A field registered with a single projection | `test_no_field_has_a_single_projection` + 2 others |
| 17 | An `EXEMPT` entry removed | `test_every_ir_field_is_projected_or_exempt` |

Row 15 is the strongest evidence available that the gate discriminates: it
failed for a real reason, on real output, and went green on a real fix.

---

## Task 4 — original design (kept for the record)

Scoped and unblocked, not implemented. Written down so the next session starts
from a decision rather than a blank file.

### The constraint that shapes it

The gate must **derive** the pairs from the IR field, not enumerate them. A list
of two comparisons behind a pleasant interface is the pair-checking version
wearing the category's clothes, and standard 11 says the breadth itself has to
be asserted.

### Shape

A *projection* is `(artifact, ir_field) → {(entity, column): normalised value}`.
One registry of projections; the gate groups them **by IR field** and asserts
every projection of the same field agrees, on every gold model.

```
Projection(artifact="ddl:postgres", field="is_nullable", read=…)
Projection(artifact="odcs",         field="is_nullable", read=…)
Projection(artifact="avro",         field="is_nullable", read=…)
Projection(artifact="protobuf",     field="is_nullable", read=…)
```

Adding a fourth artifact that projects `is_nullable` is covered the moment its
projection is registered — no pair is named anywhere.

### The breadth assertions — closed from both ends

* **From the IR:** enumerate `ColumnSchema.model_fields` (derived, never hand
  listed). Every field must either carry ≥2 projections or appear in an
  `EXEMPT` map with a written reason. A new IR field then *forces a decision*
  rather than silently arriving uncovered.
* **From the artifacts:** every contract format `export_data_contract` accepts,
  and every DDL dialect `generate_ddl` accepts, must appear as an `artifact` in
  the registry. A fifth contract format added without projections fails here.
* **A field with exactly one projection is a failure**, not a pass — it asserts
  nothing while looking registered.

### Two traps already identified

**Standard 14 applies before a line is written.** The gold graphs will not
discriminate on their own: `ColumnSchema` defaults make `is_nullable` and
`is_primary_key` uniform across all five (this is correction C7, and it already
cost one sprint a meaningless assertion). The gate needs **mutated copies** —
a nullable PK, a non-nullable non-PK — or it measures the defaults.

**Type equality is not the property.** `data_type` renders legitimately
differently per dialect and per contract format, so it belongs in `EXEMPT` with
that reason rather than in a comparison that would have to be loosened until it
proved nothing.

### Venue: `.venv-tools`, not the app suite

Decided by what can parse the artifacts:

| Parser | app `.venv` | `.venv-tools` |
| :-- | :-- | :-- |
| `sqlglot` (DDL) | ✅ 30.16.0 | ✅ 30.16.0 |
| `yaml`/`json` (ODCS) | ✅ | ✅ |
| `fastavro` (Avro) | ❌ | ✅ |
| `protoc` (Protobuf) | ❌ | system binary, resolved by the harness |

Avro and Protobuf — the pair with a track record of disagreeing, since Sprint 3's
NUMERIC defect — are only parseable in the fidelity toolchain. So the gate lives
beside `test_artifact_fidelity.py`, runs under `.venv-tools`, and is guarded by
`MODELBOX_FIDELITY_STRICT` so a missing toolchain fails loudly instead of
skipping (standard 4).

**Projections must parse, never substring-match.** The whole programme exists
because 76 defects hid behind string assertions.

### Known first pairs

`is_nullable` → DDL `NOT NULL` / ODCS `required` / Avro union-with-null /
Protobuf optionality. `is_primary_key` → DDL `PRIMARY KEY` / ODCS `primaryKey`.
Both sides already exist; this is comparison, not generation.

---

## Proposed follow-on, for sprint close: the removal sweep

**Proposed, not decided.** Recorded here so it survives the sprint.

Standards 8, 11, 12 and 14 are four variations on one theme — *a test that
passes without the thing it names ever happening.* Each was found separately, in
unrelated code, by tripping over it. Four independent discoveries of one shape
is strong evidence there is a fifth, and that hunting it deliberately beats
waiting to find it.

All four share a single detector, and it is cheap to apply:

> **Of every gate in the suite: what still fails if the mechanism is removed?**
>
> If the answer is "nothing", the gate is one of these four — the fixture never
> exercised the feature (8), the parameterisation never covered it (11), the
> expected value was absent, empty or unsettable (12), or a later fix removed
> the discriminating case (14).

It is the question that killed mutant 14, and it would have found the
`_upgrade_to` empty-string defect, the `field_validator` that never fired, and
the `stable_id` high-water mark on a row its own path deleted. Those were each
found by a different accident.

Scope when it runs: mechanical, one pass over the suite, no fixes in the same
commit as the finding. Anything it turns up is a register entry before it is a
repair.

### Venue five, and why the scope stays narrow anyway

A fifth instance appeared while this proposal was being written, and it was not
a gate and not in the suite. **This document** carried every ruling and all
fourteen mutation results and no test counts at all — so a restart could report
the current numbers and nothing recorded could say whether they were the right
ones. Present, plausible, unverifiable: the same shape, in the handoff artifact
instead of the code. Fixed by the baseline table above, which turns a divergent
count into a finding with a commit range attached.

That argues the eventual aperture is wider than "every gate in the suite" — the
general form is *of every artifact that carries a claim, what would have to be
different for it to be wrong, and would anything notice?* Register rows, Proof
Log entries and this file all qualify.

**The first pass stays narrow regardless**, and deliberately:

* The narrow sweep is bounded — fourteen-odd gates, one question each — and
  every instance it finds is of a shape already proven to recur four times.
* The wide version is an open-ended audit of everything the programme has
  written, proposed at the point where Sprint 5 still has four tasks left and
  its only genuine unknown ahead of it.
* **The first pass is the evidence for whether the second is needed.** Six
  findings in gates would clearly justify a document-level pass. One finding
  would suggest the pattern is more concentrated in tests than five venues
  make it look.

So: narrow pass first, at sprint close. Scope of any second pass decided after
the first reports, not before. This is a budget decision as much as a
methodological one — introspection competes with Tasks 4 through 8, and Task 5
is the one that cannot be rushed.

---

## Task 5 — threshold banked, harness and run outstanding

**Step one done:** `backend/scripts/conformance_threshold.py`, commit `b6a3e1a`,
committed alone into a tree that contained no code able to contact a provider.
"Threshold before output" is therefore a property of git history, not a claim in
a docstring — and the remaining work can happen in any session without weakening
it, which was the entire reason for the ordering.

**Step two done:** `scripts/conformance_scoring.py` (pure, offline-testable),
`scripts/run_provider_conformance.py` (the only script permitted to reach a
provider), `tests/test_conformance_isolation.py` (7 tests).

**Two opt-ins, not one.** `MODELBOX_ALLOW_PROVIDER_CALLS` is Task 1's
appliance-wide fail-closed gate; `MODELBOX_RUN_CONFORMANCE` is the script's own.
Either alone refuses, and all three insufficient combinations are asserted —
checking only the all-unset case would pass on a runner needing just one flag,
and one flag away from an accident is not far enough.

Two structural guarantees beyond that: the runner makes no provider call at
module scope (so importing or collecting it cannot cause egress), and **neither
the runner nor the scorer may define a threshold constant** — they must import
them. A harness carrying its own copy of a number would silently undo the
guarantee the ordering bought, while the report still claimed the threshold was
applied. The threshold module is also asserted unable to import the gateway, so
its commit stays readable as one where nothing could call out.

`test_neither_flag_is_set_in_this_environment` asserts the offline guarantee
where it is relied on — the suite's zero-egress property is worth nothing if
nobody checks the flags that would break it are unset while it runs.

### Run instruction

```bash
# 1. local runtime up, with the router's default_model pulled
docker compose -f docker/docker-compose.appliance.yml --profile airgap up -d ollama-engine
docker exec modelbox-ollama-engine ollama pull qwen2.5-coder:32b

# 2. at least one cloud key, so there is something to compare against
export ANTHROPIC_API_KEY=...

# 3. both opt-ins, deliberately, and never in CI
cd backend
MODELBOX_ALLOW_PROVIDER_CALLS=1 MODELBOX_RUN_CONFORMANCE=1     .venv/Scripts/python -m scripts.run_provider_conformance     --providers local_ollama,anthropic_cloud     --out ../docs/marketing/conformance-report.json
```

### Two acceptance events, deliberately separate

* **The harness is done** — built, isolated, provably unable to run by accident.
  All of that is verifiable offline and is verified.
* **Sprint 5 is done** when the run has happened and the report exists.

D10's register evidence must cite **the report**, not the script. A harness that
has never produced a number proves the method, not the claim.

### BLOCKING: the prompts are underspecified — do not run yet

Written before the first call, as a judgement rather than a glance, because
after numbers exist the ambiguity resolves in whichever direction is convenient:
a poor local score reads as "local models are worse", a poor cloud score reads as
"the prompt needs work". Both are available after the fact. That is the shape the
threshold ordering exists to prevent, arriving through a door the threshold does
not cover.

**Two defects, found by running the check.**

1. **No gold graph has a `description` field at all.** The keys are `id`,
   `title`, `paradigm`, `entities`, `relationships`. So the runner's fallback
   fires on all five and the prompt becomes the filename with hyphens replaced —
   "banking datavault", "ecommerce orders". `title` exists and is better
   ("Retail Banking & Ledger") but is still four words.
2. **The paradigm is never communicated**, and the five graphs span four of
   them. The product's own `SynthesizeRequest` carries `target_paradigm`
   precisely because it is not inferable. A model asked for a banking schema
   with no paradigm stated cannot produce `hub_` / `lnk_` / `sat_` naming — that
   is Data Vault convention, not a fact about banking.

**Per-graph judgement.** Could a competent human data modeller, given only the
prompt text, plausibly produce the gold entity set?

| Graph | Paradigm | Verdict |
| :-- | :-- | :-- |
| `banking-datavault` | DATA_VAULT | **No.** hub/lnk/sat naming is unrecoverable from "Retail Banking & Ledger" |
| `marketing-attribution` | OBT | **No.** A single wide `obt_touchpoints` table is a deliberate modelling choice; the default answer is a star schema |
| `ecommerce-orders` | KIMBALL | **Only if the paradigm is stated.** `dim_`/`fact_` naming is a coin flip otherwise |
| `saas-subscription` | KIMBALL | **Only if the paradigm is stated.** Same as above |
| `healthcare-ehr` | 3NF | **Entities plausible** (patient/provider/encounter/diagnosis are canonical), naming still paradigm-dependent |

**Zero of five are well-posed as they stand. Two are not well-posed at all.**
Running now would produce five numbers measuring prompt poverty and report them
as model quality — against a threshold that cannot tell the difference.

**The fix, in two parts.**

* *Mechanical, and clearly correct:* pass the graph's `paradigm` into the
  prompt. The product's own API carries it, so withholding it tests something
  the product never asks a model to do.
* *A content decision, deliberately not made here:* author a domain description
  per graph. This needs calibration and is the reason it is not being guessed
  at — **too thin measures prompt poverty, too rich measures transcription.**
  The target is a description from which a competent modeller could plausibly
  arrive at the gold entity set without being handed it. Whoever writes them
  should record that judgement per graph, as above, before the run.

Until both are done, **any conformance number is uninterpretable** and D10 stays
open. This is a fixture defect, not a harness defect: the harness, its isolation
and its scoring are complete and verified.

### The calibration rule — write the descriptions to this, not to a feel

Fixed before authoring any description, for the same reason the threshold was
fixed before any call: a description written while looking at the gold entity
list will drift toward naming it.

> **State the business domain, each entity's purpose, and the grain of the
> central fact. Do not name entities, columns, or relationships.**
> Pass `target_paradigm` explicitly, since the product's own API carries it.

**Exclusion rule.** If `banking-datavault` or `marketing-attribution` cannot be
made well-posed without naming entities, **exclude them from conformance with
the reason recorded** rather than including them at a discount. A graph scored
against a prompt that had to give away the answer measures transcription, and
averaging it with the others hides that inside a mean.

**The paradigm fix** is mechanical and unblocked: pass each graph's `paradigm`
into the prompt. Withholding it tests something the product never asks a model
to do.

---

## Two product items surfaced by a user question

Neither is Sprint 5 scope. Recorded because both are derived from shipped code
rather than opinion, which is what makes them cheap and defensible.

**1. The thirteen-code table is an input specification.** "Here is precisely
what to provide, and here is which check fires if you don't" — grain, entity and
column descriptions, PII designation, freshness SLA, quality rules, keys and
references, naming convention, relationship structure. Derived from
`GraphEngine.validate`, the same instrument that grades Trainer labs and scores
provider conformance. It belongs in `docs/USER_GUIDE.md`, with a compressed
version in the synthesis UI. That is the honest answer to "what should a user
provide": not intuition and not a gate, but the product stating its own
requirements, sourced from the thing that will judge the result.

**2. "Omit rather than guess" is a stated product property and a Proof Log
candidate.** The synthesis system prompt already instructs it — an omission
costs nothing, a guess is exported into a data contract as fact — so
under-specification yields a *sparser* model rather than a wrong one. Safe
failure direction, and the reason iteration works.

**Checked, and it is partially proven only.** `test_unbounded_pattern_is_not_guessed_at`
covers one linter path; `test_a_response_omitting_every_new_field_still_validates`
covers IR-level omission. Neither proves the end-to-end claim — that a sparse
input yields a sparse-but-correct model rather than a wrong one. **No Proof Log
entry until a test does**, which is the rule the document exists to enforce.

**Not claimed anywhere yet**, and it should not be until then.

---

### Done: paradigm supplied, five descriptions written

`scripts/conformance_prompts.py` and `tests/test_conformance_prompts.py` (23
tests). The prompt now states the paradigm and a description written to the
calibration rule. A graph with no description is a **hard error**, never a
fallback to the filename — that fallback is what made every prompt two words,
and degrading to it again would be the same defect wearing the word "default".

Descriptions live in the harness, **not in the gold fixtures**: those are
extracted from `templates.ts` behind a drift guard that re-extracts and diffs, so
a `description` field added to the JSON would fail it, and the graphs are a
curriculum asset that must not be edited to suit a harness.

**No graph is excluded.** `banking-datavault` and `marketing-attribution` were
judged not well-posed *because the paradigm was missing*. Supplying it makes both
answerable without naming an entity — "two business concepts, an association
between them, descriptive attributes historised separately" maps onto
hub/link/satellite by Data Vault convention, and OBT plus a single interaction
row is the One Big Table answer. Recorded per graph in the module docstring.

The rule is **enforced, not stated**: no snake_case token, no entity name
verbatim, a grain in every description, a 40-word floor against regression to
the filename fallback, and the paradigm present in the built prompt.

### The rule caught its own author

The first draft failed on three graphs — `balance`, `status`, `campaign`,
`channel`, `device`, `month`. All single-word **column** names that are also
ordinary nouns of their domain. You cannot describe a bank account without
"balance", and banning the noun produces evasive prose ("the hardware the
prospect used") that tests whether a model can decode circumlocution. That is
prompt poverty wearing a rule's clothing.

**The principle, stated so it is not re-derived to suit whatever failed last:**
a prompt may use the domain's vocabulary; it may not disclose the schema's
structure. Entity names are structure. Multi-token identifiers are structure. A
single common noun any requirements document in that domain would contain is
vocabulary.

The allowance is an explicit per-graph list with its own guard —
`test_the_vocabulary_allowance_is_narrow_and_justified` rejects any entry that
is multi-token, an identifier, or an entity name — because "we allowed a few
words" is how a rule stops being one.

**The honest consequence, recorded rather than hidden:** column F1 is partly
credited for domain vocabulary and is a weaker signal than entity F1. The
threshold already rated it lower — 0.70 against 0.80 — and those numbers were
fixed in `b6a3e1a` before any of this was written, which is the one reassurance
that the refinement is a principle rather than a rationalisation.

### Mutation results

| # | Mutant | Killed by |
| :-- | :-- | :-- |
| 19 | A description names `fact_order_line` | `test_no_description_leaks_a_schema_identifier[ecommerce-orders]` |
| — | *(first attempt was a silent no-op)* | see below |

**Mutant 19's first attempt applied nothing** — the anchor phrase spanned a line
break in source, so `str.replace` matched nothing and the suite passed. Without
a precondition assert that reads as *a surviving mutant*, which would have been
recorded as evidence the leak test was weak. Standard 2, in the mutation
procedure rather than in the code under test: an operation that ran is not an
operation that did anything. **Every mutation script from here asserts its
anchor is present before writing.**

**Outstanding:** the run itself, on a box with `ollama-engine` up and a cloud key. **Mutant 18:** requiring only one opt-in instead
of both — killed by `test_the_runner_refuses_without_both_opt_ins`.

**Superseded note — the harness (synthesise the five gold graphs through each
configured provider, score, emit the report), and the isolation tests — opt-in,
outside the CI gate set, incapable of running as a side effect of any test
invocation. That last one is cheap now: Task 1's choke point refuses unless
`MODELBOX_ALLOW_PROVIDER_CALLS` is set deliberately, so isolation is inherited
rather than rebuilt.

**Blocking dependency, so the next session plans around it rather than
discovering it:** the run needs a working `ollama-engine` with the router's
`default_model` pulled, and at least one cloud key. Neither is available in the
agent environment. The harness can be built and its isolation proven without
them; **the numbers themselves need Eddy's box.** Expect the next session to
deliver a runnable harness and a run instruction, not a report.

---

## Scoped and ready: make the C7 fixture structural

**Not started. Small, well-defined, and third-time-lucky evidence behind it.**

`not is_nullable` and `is_primary_key` are the same partition across all five
gold graphs. That coincidence has now cost three things:

1. a non-discriminating ODCS test (correction C7, Sprint 3);
2. a silent DDL risk, noted at the time and never exercised;
3. a **live Avro defect** shipped for four sprints (Task 4).

The remedy has been the same every time — a mutated copy where the two fields
disagree — and it keeps having to be *rediscovered* by whoever writes the next
nullability-touching test. Three recurrences is enough to stop relying on memory.

**The change.** Promote `_discriminating()` from
`tests/test_cross_artifact_consistency.py` into a shared fixture module
(`tests/_gold_fixtures.py`), exposing gold models *and* their mutated
counterparts as one parameter set. Every test that touches nullability
parameterises over that set by default, so the discrimination is **inherited
rather than remembered**.

Add the standard-11 half: a test asserting that the shared set contains at least
one model where the two fields disagree. Otherwise the fixture can silently stop
discriminating — which is standard 14, and would be the fourth recurrence of the
same coincidence wearing a fourth disguise.

Deliberately **not** done in the Task 4 commit: it is a refactor across several
test files, and Task 5 has the next claim on the sprint's budget. Recorded here
so it is a decision rather than an intention.

---

## For the sprint-close retro — not a verification standard

**A correct generalisation is not automatically due now. The work it was meant
to serve has first claim.**

Not a verification standard: it is not about a test meaning nothing. It is about
scope, and this programme is structurally prone to it — every sprint has
produced a genuine generalisation, and each arrives with momentum attached.
Acting immediately *feels* like rigour and is the scope drift that the
burn-down invariants and the preview-count discipline exist to prevent.

Two instances, one from each direction:

* **Sprint 5, the removal sweep.** Venue five was real, the wider aperture was
  the right conclusion, and widening the scope there and then would have traded
  a bounded sweep for an open-ended audit with four tasks and the sprint's only
  unknown still ahead. The insight was right; the timing would have been wrong.
* **The LookML deferral** — the same call made correctly, under less pressure,
  which is why it did not feel like a decision at the time.

The tell is that the generalisation is *sound*. An unsound one gets argued
down. A sound one arrives with its own justification attached and has to be
timed rather than refuted.

---

## Remaining

| Task | State |
| :-- | :-- |
| 2 — Per-task residency (D5, D8) | **done** |
| 3 — Air-gapped mode that proves itself (D6, D7, Q1) | **done** |
| 4 — Cross-artifact consistency gate (standard 10) | **done** — found and fixed an Avro/DDL/ODCS disagreement |
| 5 — Provider conformance harness (D10) | **next** — own session; threshold in writing before the first call |
| 6 — Security FAQ (G2) | not started |
| 7 — Unassisted install (G1) | pending an evaluator; Eddy arranges |
| 8 — One Trainer lab (H4) | not started |

Carried forward for D4: wiring `model_id` / `user_id` / `workspace_id` from the
three call sites, without which the ledger cannot answer "who".
