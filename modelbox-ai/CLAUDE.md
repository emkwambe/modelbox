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

**After a multi-step edit, verify the resulting file state directly.** Do not
trust the edit's own report. Twice now a scripted edit reported success for
work it did not do: a pipe swallowed a failed `cd` so a commit landed on a test
run that never happened, and a batch whose last assertion failed silently
discarded the earlier substitutions, leaving a call site referencing queries
that were never written. Both times a tool caught it — `pytest`, then Ruff's
F821 — rather than the author. Read back what the file now contains, or run the
check that would fail if it did not. Same shape as `_upgrade_to` reading back
`alembic current`.

**A round-trip test cannot see a defect the round-trip itself corrects.** If
the path under test normalises its input in transit, the assertion measures the
repair. Assert at construction as well as after a save. A Pydantic
`field_validator` never fires on an unsupplied field, so a rule that looks
enforced can be doing nothing on every real payload while a save-reload test
passes — see register verification standard 5.

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

**Never edit source through a bash heredoc, and never with a regex spanning
multiple constructs.** A hard constraint, not a preference — the preference was
overridden for convenience twice and cost four incidents in one sprint:

- A newline escape inside a Python string literal is mangled in transit,
  producing an unterminated literal. Three times, including in the paragraph
  that previously stood here, which is why it read as a stray backtick.
- A regex anchored across constructs matched far more than intended and deleted
  161 lines, taking two whole test sections and a helper the rest of the file
  depended on.

What the four have in common is that **the reasoning was correct and the
transport corrupted it.** More care is therefore not the fix; removing the
transport is. Use direct `Edit` calls. Where a genuinely mechanical multi-site
change is unavoidable, use line-addressed replacement and validate **every**
block against the file before writing **anything**, so a late mismatch cannot
leave a file half-edited.

What made both serious incidents cheap was the file being committed, not the
guidance. Commit before a mechanical edit.

**Commit messages go through `git commit -F <file>`, never inline quoting.** A
PowerShell here-string passed to the Bash tool put a stray `@` on the subject
line of a Sprint 5 commit; the message was correct and the transport mangled it.
Fourth venue for the same class, and the same remedy: write the message with
`Write`, pass the path. Inline `-m` is fine only for a single line with no
quotes, backticks or `$`.

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

The six reference models are **extracted** from `frontend/src/lib/templates.ts`
into `backend/tests/fixtures/gold/`, never transcribed, with a drift guard that
re-extracts and diffs. They are a curriculum and marketing asset: do not seed
them with defects, and do not edit them to satisfy an emitter. Defect
reproductions belong in `backend/tests/fixtures/synthetic/`.
