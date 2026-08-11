# ModelBox AI — working agreements

Conventions that are easy to get wrong and expensive to get wrong. Each earned
its place by being violated at least once.

## Verification

**Never chain a verification command into a pipe whose exit status can mask an
earlier failure.** `cmd && cd x && test | tail -2 && git commit` reports
`tail`'s status, so a failed `cd` sails straight through and the commit lands on
a verification that never ran. Use `set -o pipefail`, or run the check as its
own command and read the result before committing.

The failure mode this guards against is not a broken build — it is **claiming
verification you did not perform.** Two instances so far, both caught after the
fact: the audit's dbt projects parsed only because the harness supplied a
`_sources.yml` the auditor had written (finding H9), and a piped test run that
never executed. Every register criterion and every Proof Log entry rests on the
claim that stated evidence was actually produced.

**A test must verify its own preconditions.** An exit code says a command
ran, not that it achieved its purpose. `alembic upgrade` returning 0 does not
mean the database reached that revision — read back `alembic current` and
assert it. Three harness bugs in Sprint 2 were all this same shape: a fixed
port that bound to a previous run's container, an exit code taken for arrival,
and a SQL `GROUP BY` on a non-unique name. Each produced a confident wrong
answer rather than an error.

**A skipped gate must be loud, not absent.** Anything a test depends on from
outside the working tree — a toolchain, a container, a git tag — can make it
degrade to a no-op that reports green. Guard it with a strict flag that turns
absence into failure, and remove the cause where you can.

**Verify from outside the layer under test.** Checking a persistence backfill
by reading it through the ORM lets a mapping bug satisfy the assertion; check
it with raw SQL. Checking an emitter rule against data where two rules produce
the same output proves nothing; supply a case where they differ. Register
verification standard.

## Environments

- `backend/.venv` — the application and `pytest`.
- `backend/.venv-tools` — the artifact fidelity toolchain (`requirements-dev.txt`).

**Never install one into the other.** dbt downgrades `protobuf` 7.x → 6.x and
`pathspec` 1.x → 0.x and removes `mypy`. Every fidelity verdict is a statement
about a specific resolved version set; mixing them silently changes what the
gate means.

`requirements.lock` is generated inside `python:3.11-slim`, never on a
developer machine — a Windows-generated lock pins Windows packages and omits
environment markers.

## The fidelity harness

`backend/tests/test_artifact_fidelity.py` asserts artifacts against the tools
that consume them, never against substrings. It carries the burn-down for the
audit's open findings.

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m "not preview" -q
```

- Defect `xfail`s are `strict=True` **from creation**, so a fix turns the run
  red until the marker is removed. The inventory can never overstate remaining
  work.
- `MODELBOX_FIDELITY_STRICT=1` turns a missing toolchain into a hard failure. A
  gate that silently skips is worse than no gate: it reports green having
  verified nothing.
- `@pytest.mark.preview` marks failures that are *labelled* rather than
  scheduled (the three Preview dialects, LookML). Excluded from the burn-down.
- **Check the inventory at every commit boundary**, not just at sprint end. If
  it moves, the commit that moved it is the bug.

## Tests must be able to fail for the right reason

A test that cannot distinguish the correct implementation from the current one
is worthless, and it will go green the moment an unrelated change makes two
different rules produce identical output — closing a finding that was never
fixed. Register stop condition 4.

Before relying on a test that depends on a new field, check the fixtures
contain a case where the old and new behaviour actually differ. `ColumnSchema`
defaults made `not is_nullable` and `is_primary_key` identical on all five gold
graphs; the assertion needed a mutated copy to mean anything (correction C7).

## Claims

- No public surface states a capability without a `PL-` id in
  `docs/marketing/PROOF_LOG.md` behind it.
- **A Proof Log entry requires a passing test.** Not a plausible argument, not
  a finding that is merely interesting — a named test that passes. An entry
  without one is the exact failure the document exists to prevent.
- Documentation is updated in the same PR as the behaviour it describes. If the
  code does not do it, the doc does not say it.

## Gold graphs

The five reference models are **extracted** from `frontend/src/lib/templates.ts`
into `backend/tests/fixtures/gold/`, never transcribed, with a drift guard that
re-extracts and diffs. They are a curriculum and marketing asset: do not seed
them with defects, and do not edit them to satisfy an emitter. Defect
reproductions belong in `backend/tests/fixtures/synthetic/`.
