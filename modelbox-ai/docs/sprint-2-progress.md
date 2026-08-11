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
| 2 — `stable_id` (Q6, C3) | not started | |
| 3 — constraint fields (H4, C2 capability half) | not started | |
| 4 — `agg_time_column` (B1's fourth defect) | not started | |
| 5 — migration + populated-DB verification (C8) | not started | |
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
