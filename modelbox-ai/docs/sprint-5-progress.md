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

## Remaining

| Task | State |
| :-- | :-- |
| 2 — Per-task residency (D5, D8) | next |
| 3 — Air-gapped mode that proves itself (D6, D7, Q1) | not started |
| 4 — Cross-artifact consistency gate (standard 10) | not started |
| 5 — Provider conformance harness (D10) | not started; threshold must be written before the first call |
| 6 — Security FAQ (G2) | not started |
| 7 — Unassisted install (G1) | pending an evaluator; Eddy arranges |
| 8 — One Trainer lab (H4) | not started |

Carried forward for D4: wiring `model_id` / `user_id` / `workspace_id` from the
three call sites, without which the ledger cannot answer "who".
