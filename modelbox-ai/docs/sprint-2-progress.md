# Sprint 2 — progress and handoff state

**Branch:** `sprint/2-ir-foundation`, cut from `main` at `a707719` (v1.6.0 + the
two A9 documentation commits).
**Spec:** `docs/SPRINT_2_PROMPT.md`. **Register:** §C. **Rulings:** Blueprint §3.

This file exists so the sprint can be resumed from the branch alone. Nothing
below needs re-deriving — every decision here has already been ruled.

---

## Status

| Task | State | Commit |
| :-- | :-- | :-- |
| 1 — consolidate persistence (Q8, C6) | **done** | `a273dc3` |
| — amend `test_odcs_required_reflects_nullability` (C7) | **done** | this commit |
| 2 — `stable_id` (Q6, C3) | **schema+ORM+repo done**, tests pending | this commit |
| 3 — constraint fields (H4, C2 capability half) | **schema+ORM+repo done**, introspection pending | this commit |
| 4 — `agg_time_column` (B1's fourth defect) | **schema+ORM+repo done**, gold graphs pending | this commit |
| 5 — migration written; populated-DB verification (C8) | **migration `0013` written**, verification pending | this commit |
| 6 — `references` populate/persist (M6, C7 partial) | not started | |
| 7 — canvas controls | not started | |
| 8 — synthesis prompt | not started | |
| 9 — round-trip tests (C1) | not started | |

**Invariant checked at every commit boundary** — if it moves, the commit that
moved it is the bug:

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m "not preview" -q   # 76 xfail
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m preview -q         # 18 xfail
.venv/Scripts/python -m pytest -q                                                                                     # 246 passed
```

---

## Decisions already ruled — do not re-litigate

### `stable_id` allocation (Task 2)

Per-entity monotonic integer. `entity_columns.stable_id INTEGER NOT NULL` with
`UniqueConstraint(entity_id, stable_id)`; high-water mark on
`model_entities.next_stable_id INTEGER NOT NULL DEFAULT 1`.

**`replace_graph` must upsert entities by `(model_id, entity_name)` instead of
delete-and-recreate.** The natural key already exists as `uq_model_entity_name`.
Without this the watermark is destroyed on the first save after allocation and
ids are re-derived from scratch — reproducing exactly the reuse H6 is about.
This is a behavioural change and belongs in Task 2, which is why Task 1 was kept
to pure consolidation.

Allocation order, per incoming column:

1. `stable_id` supplied **and** currently held on this entity → reuse *(rename)*.
2. `stable_id` supplied, `< next_stable_id`, not currently in use → honour it
   *(undo / re-add recovers its original tag)*.
3. `column_name` matches an existing column → reuse that id.
4. Otherwise allocate `next_stable_id`; if `19000 ≤ id ≤ 19999` jump to `20000`
   (Protobuf reserved range); then `next_stable_id = id + 1`.

Reject `stable_id >= next_stable_id` (a client cannot invent a future id) and
duplicates within an entity.

**Never reused after delete** because the watermark only increases and is
stored, never derived as `max(existing) + 1`.

**Known edge, accepted:** dropping an entire entity discards its watermark, so a
re-created entity of the same name restarts at 1. A dropped and recreated table
is a new Protobuf message; pretending otherwise would be the wrong kind of
stability.

**Backfill preserves today's Protobuf tags.** `_protobuf_schema` uses
`enumerate(entity.columns, start=1)` over columns the ORM orders by
`ordinal_position`, so the current tag *is* the ordinal rank (verified on the
gold graphs). Backfill:

```sql
stable_id      = row_number() OVER (PARTITION BY entity_id ORDER BY ordinal_position, column_id)
next_stable_id = COALESCE(MAX(stable_id), 0) + 1
```

`column_id` breaks ties — `ordinal_position` carries no uniqueness constraint.
Add nullable → backfill → `SET NOT NULL`.

### Constraint fields (Task 3)

`is_nullable` (default `True`, primary keys forced `False`), `is_unique`,
`default_value`, `check_expression`.

Introspection scope, ruled: `is_nullable` and `default_value` from
`information_schema.columns` on **all four** engines (one extra column in the
existing query). `is_unique` from `table_constraints`/`key_column_usage` where
the catalog supports it (Postgres, MySQL, Snowflake; BigQuery has no such
concept). `check_expression` from `check_constraints` (Postgres, MySQL only).
Everything else stays **null, not false** — an unknown recorded as `false` is a
fabricated constraint in an exported contract.

### `agg_time_column` (Task 4) — entity-level

`EntitySchema.agg_time_column: str | None`, naming a temporal column on that
entity. Not a column-level boolean:

- MetricFlow's construct is one-per-semantic-model, so entity-level makes the
  invalid state (two flagged columns) unrepresentable.
- MetricFlow's per-measure override also *names a dimension*, so a boolean is
  the wrong shape even for the case that would justify column-level.
- It matches `grain`/`tier`/`freshness_sla`, which are already entity-level.

Validation: the named column must exist on the entity and be temporal.

**Only 9 of the 15 gold-graph entities can be populated.** These 6 have no
temporal column at all:

```
ecommerce-orders   dim_customer, dim_product, fact_order_line   (whole graph)
healthcare-ehr     provider, diagnosis
saas-subscription  dim_plan
```

Leave those `null`. **Ruled for Sprint 3:** entities with no `agg_time_column`
emit **no measures** and become dimension-only semantic models. Not new date
columns in `templates.ts` — that would mutate a curriculum and marketing asset
to satisfy an emitter. A `dim_product_count` with no time axis is not a useful
metric anyway. Sprint 3 must add a harness assertion that a semantic model with
no `agg_time_column` declares no measures, so the rule is verifiable rather
than incidental.

### `references` (Task 6) — populate only

Wire it, don't delete it: ODCS v3.1.0 has native property-level `foreignKey`
(correction C3), which gives the field the downstream consumer it lacked. Scope
here is populate/persist/round-trip only. The ODCS emitter consumes it in
Sprint 3 with the rest of H2, so **C7 in the register is partial after this
sprint**, not closed.

### Register criteria

Closed by this sprint: **C1, C2 (capability half), C3, C6, C8.** C7 partial.
The sprint prompt listed C7 as closing and omitted C8; C8 is exactly Task 5.

---

## What landed in the schema+ORM+migration commit

`ColumnSchema`: `stable_id` (server-assigned, `ge=1`), `is_nullable` (default
`True`, a validator forces `False` on primary keys), `is_unique`,
`default_value`, `check_expression`. `EntitySchema`: `agg_time_column`, with a
model validator requiring the named column to exist on the entity and be
temporal. A shared `_is_temporal_type` helper now lives in `data_model.py` —
three exporters carry their own copy of that predicate today, and Sprint 3
should collapse them onto it.

ORM: `model_entities.agg_time_column`, `model_entities.next_stable_id`;
`entity_columns.stable_id` with `uq_entity_column_stable_id (entity_id,
stable_id)`, plus the four constraint columns and `reference_target`. The FK
target column is **not** called `references` — that is a reserved SQL word — but
the IR field keeps the name.

`GraphRepository.replace_graph` now upserts entities by name instead of
delete-and-recreate, so the watermark survives a save. Relationships are still
rebuilt wholesale and are deleted *first*, because they reference the column
rows a column deletion would otherwise orphan. Allocation lives in
`_match_existing` / `_next_free_id`.

Migration `0013` is additive: add nullable → backfill → tighten. `stable_id` is
backfilled as `row_number() OVER (PARTITION BY entity_id ORDER BY
ordinal_position, column_id)`, which reproduces today's Protobuf tags exactly.

## Execution order — RULED, supersedes `SPRINT_2_PROMPT.md`

**5 → 9 → 3 → 4 → 6–8.** The prompt's numbering is not the execution order.

Round-trip tests (9) come before introspection (3), gold graphs (4) and the
canvas (6–8). `stable_id` allocation is the piece most likely to be subtly
wrong and is currently exercised only incidentally by the existing suite.

The sharper reason is correction C7. A test that cannot distinguish the correct
implementation from the current one is worthless, and *untested allocation
logic* is the same hazard one step earlier: everything built on top of it would
appear to work while resting on an unverified invariant. Verify the invariant,
then build on it.

### Still to do on these tasks

- Introspection does not yet populate `is_nullable`/`default_value` (all four
  engines) or `is_unique`/`check_expression` (where the catalog supports it).
- The five gold graphs do not yet set `agg_time_column`; 9 of 15 entities can.
- Round-trip tests (Task 9) are not written. The properties to assert are listed
  in `SPRINT_2_PROMPT.md`.
- The populated-database migration verification (Task 5) is not run; the plan is
  at the end of this file.
- Canvas (Task 7) and synthesis prompt (Task 8) untouched.

## Hard constraints

- **No exporter changes.** If a fix is one line and obvious, note it for
  Sprint 3 and leave it.
- **Do not flip any xfail.** The H4/H3 and H2/H4 cases depend on these fields
  but belong to Sprint 3.
- The only sanctioned harness edit is the mutated-copy assertion in
  `test_odcs_required_reflects_nullability`, already landed.
- `backend/.venv` for app and pytest; `backend/.venv-tools` for the fidelity
  toolchain. Never install one into the other.
- No provider API keys.

## Migration verification plan (Task 5)

Against a disposable Postgres container, never the appliance volume.

1. `postgres:16-alpine`, `alembic upgrade 0012`.
2. Seed all five gold graphs through the **v1.6.0** persistence code, run from a
   `git worktree` at the tag — the "before" must be produced by the old code.
3. Capture pre-migration artifacts from every emitter and SHA-256 each.
4. `alembic upgrade head`.
5. Re-export with the new code from the migrated database; **byte-identical is
   the assertion.**
6. Assert the backfill: `stable_id` 1..N per entity in ordinal order,
   `next_stable_id` = N+1, `is_nullable` true except PKs, nothing in the
   reserved range.
7. `alembic downgrade -1` → schema back at 0012, models still load and export
   identically.
8. `alembic upgrade head` again → re-application is clean.

Ruled: **add a `postgres` service to the existing backend CI job** so this runs
on every push. It does not add a seventh required check.

### If step 5 fails, it is a discovery, not a migration bug

The byte-identical export assertion is this sprint's real gate, and it has not
run yet. Sprint 2 changes no emitter, so **the same model must produce the same
bytes before and after the migration.** If it does not, the first hypothesis is
*not* that the migration is wrong.

It means something in the emitters is already non-deterministic — dictionary or
set iteration order, an unsorted `glob`, a timestamp, a hash seed — and that
would be a **new finding outranking most of what is on the board**, because
every fidelity verdict, every Proof Log entry and the whole byte-comparison
method rest on emitters being pure functions of the IR. Two of the three
Sprint 1 Proof Log entries assume it.

Treat a failure as something to characterise and report, not to debug into
submission until the diff goes away. Establish first *which* artifact differs
and *how*, then decide whether it is the migration or the emitter.

## For the PR body and the Proof Log

**H6 reproduced by the fix for H6.** The watermark had to move off
delete-and-recreate persistence, and the reason is the most instructive thing
in this sprint: a watermark stored on a row that `replace_graph` deleted on
every save would have been destroyed on first save, ids re-derived from
scratch, and a tag reissued that a deployed Protobuf consumer still associates
with an older field. That is precisely the defect `stable_id` exists to
prevent — latent inside its own remedy, and invisible until you ask what
happens on the *second* save.

**Sprint 8 lab candidate: "the fix that recreates the bug."** A real defect, a
real mechanism, and a fix whose first draft reintroduces the thing it was
written to eliminate. Better teaching material than an artificial flaw, and it
comes with a verifiable end state — `stable_id` unchanged across two saves.
