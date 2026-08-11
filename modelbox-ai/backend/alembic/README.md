# Migrations

## Revision ids must be 32 characters or fewer

`alembic_version.version_num` is `VARCHAR(32)`. A longer revision id raises
`StringDataRightTruncation` **after** the DDL has already succeeded, while
alembic stamps the new version.

This is nasty to diagnose because nothing local catches it:

- `alembic heads` reports a clean single head — the id is valid Python.
- An empty-database migration test passes, because the failure is in version
  stamping, not in the schema change.
- It only fails against a real database, at the very end of an upgrade that
  otherwise worked.

Found in Sprint 2: `0013_add_column_identity_and_constraints` is 40 characters.
Shortened to `0013_add_column_identity` (24). Check the length before you commit:

```bash
python -c "r='0014_your_revision_id'; print(len(r), 'OK' if len(r)<=32 else 'TOO LONG')"
```

This is the empirical argument for the Postgres service in CI. No amount of
local checking substitutes for running the upgrade against the real engine.

## Every migration is verified against a populated database

`backend/tests/test_migration_0013_populated.py` is the pattern. An
empty-database migration proves only that the DDL parses. What matters is that
models persisted by the *previous release* survive.

The shape:

1. A disposable Postgres container on an **ephemeral free port** — never a fixed
   port, which silently binds to whatever a previous run left behind, and never
   the appliance volume.
2. `alembic upgrade <previous revision>` run from a **git worktree at the last
   tag**, so the "before" state is produced by the code that shipped it rather
   than by the current tree with new fields unset.
3. Seed every gold graph, export every artifact, hash each one.
4. `alembic upgrade head`, re-export with the new code, and assert
   **byte-identity** for any migration that is not supposed to change output.
5. Assert the backfill **against SQL**, not through the ORM.
6. `alembic downgrade -1`, confirm the old code still reads the database, then
   re-upgrade.

Two rules that emerged from getting this wrong:

**Verify from outside the layer under test.** The backfill is checked with raw
SQL because reading it through the ORM would let a mapping bug satisfy the
assertion. Register verification standard.

**A zero exit code means a command ran, not that it arrived.** `_upgrade_to`
reads back `alembic current` and asserts the stamped revision. Without that, a
wrong working directory or DSN surfaces as a confusing `UndefinedColumnError`
several steps later instead of naming the actual problem.

## Conventions

- One head, always. CI enforces it (`Alembic Single Head`).
- Additive only where possible: add nullable → backfill → tighten. No
  destructive step in an upgrade path.
- Every migration has a tested `downgrade`.
- `server_default` on any column added `NOT NULL` to an existing table.
