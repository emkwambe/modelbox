# ModelBox AI — v1.7.0 Release Notes

**Tag:** `v1.7.0`  ·  **Cut from:** `main`  ·  **CI:** green, six required checks

Sprint 2 — *IR Foundation*. The intermediate representation could not express
what four exporters needed, so each guessed and they guessed differently: Avro
declared every non-key column nullable, Protobuf declared nothing nullable,
ODCS restated the primary-key flag, and DDL emitted no constraint at all. This
release adds the missing capability and proves it round-trips.

**It changes no exported artifact.** Sprint 3 consumes what this builds. The
artifact fidelity inventory is unchanged at **76 non-preview / 18 preview**,
which is the assertion that the sprint stayed in its lane.

---

## What the model can now express

| Field | |
| :-- | :-- |
| `stable_id` | Per-column identity, server-assigned, **never reused** |
| `is_nullable` | Defaults to `true` — the SQL default; forced `false` on primary keys |
| `is_unique` | A `UNIQUE` constraint independent of the key |
| `default_value` | Column `DEFAULT` |
| `check_expression` | Boolean `CHECK` |
| `references` | Column-level `entity.column` foreign-key target |
| `agg_time_column` | Entity-level default time axis for measures |

Introspection reads them from the source system rather than assuming them, and
the canvas can set every one. `stable_id` is displayed read-only: a field that
can be edited is not stable.

### Introspection, scoped honestly per engine

| Engine | nullable | default | unique | check |
| :-- | :-- | :-- | :-- | :-- |
| PostgreSQL | ✅ | ✅ | ✅ | ✅ |
| MySQL | ✅ | ✅ | ✅ | ✅ (8.0.16+) |
| Snowflake | ✅ | ✅ | ✅ *(declared, unenforced)* | — |
| BigQuery | ✅ | ✅ | — | — |

**An unknown is left absent, never asserted as false.** A brownfield model that
claimed a constraint the warehouse never made would export that claim into a
data contract as fact. So: single-column `UNIQUE` only, because a composite says
nothing about any one column; Postgres `CHECK` excludes the `IS NOT NULL`
clauses it materialises for every `NOT NULL`; and MySQL, which does not report
which column a `CHECK` belongs to, attributes a clause only when exactly one of
the table's columns is named in it.

---

## The theme: fixes that contained the problem they fixed

Two defects this release, both of which had the shape of a remedy concealing the
thing it was meant to remove. They are the most useful thing in it.

### H6 reproduced inside the fix for H6

`stable_id` exists because Protobuf field tags derived from list position break
wire compatibility when a column is inserted. The design puts the allocation
high-water mark on the entity row — but `replace_graph` **deleted every entity
row on save**. The watermark would have been destroyed on the first save, ids
re-derived from scratch, and a tag reissued that a deployed consumer still
associates with an older field.

That is precisely the defect the field exists to prevent, latent inside its own
remedy, and invisible until you ask what the *second* save does. Fixed by
upserting entities on the existing `(model_id, entity_name)` natural key.

Two consequences worth having: relationships are now torn down before columns,
since upserting deletes columns individually rather than cascading from a
dropped entity; and the canvas save path no longer churns
`from_column_id`/`to_column_id` on every write.

### A validator that never ran, and a test that repaired the evidence

`_primary_keys_are_never_nullable` was a Pydantic `field_validator`. **Pydantic
does not validate a field that was never supplied**, so the rule did nothing
whenever `is_nullable` was omitted — which is every LLM response and every
reference model.

The round-trip test passed regardless, because reloading constructs the column
with every field explicit and the rule fired on the way back. The model was
wrong at construction and correct after a save. `POST /model/synthesize`
returns the model **directly**, so a freshly synthesised primary key stayed
nullable and the next release would have emitted no `NOT NULL` for it —
silently defeating the entire purpose of this one.

Now a `model_validator`, which always runs. Recorded as verification standard 5:
*a round-trip test cannot see a defect the round-trip itself corrects.*

---

## Robustness

A weaker local model that omits the new fields still synthesises — they are
optional with server-side defaults. More usefully, a weaker model that gets one
*plausibly wrong* also still synthesises: an `agg_time_column` naming a column
that does not exist, or one that is not temporal, is discarded with a warning
and the entity becomes dimension-only.

Raising there looked stricter and was worse. Because the model is the structured
output schema for synthesis, a raise failed the **whole** result: one
hallucinated column name and you got no schema at all instead of a good schema
with one hint missing. "LLM-agnostic" is the claim that would have broken, and
it would have surfaced two releases later as a model-quality problem rather than
a schema decision taken here.

## Migration `0013`

Additive: add nullable, backfill, tighten. `stable_id` is backfilled as
`row_number()` over `(ordinal_position, column_id)`, which reproduces existing
Protobuf tags byte-for-byte.

Verified against a **populated** PostgreSQL, not an empty one: five models
seeded by v1.6.0's code at the previous revision, migrated, re-exported, and
compared hash for hash across ~150 artifacts per model. This now runs in CI on
every push. A downgrade path is included and tested.

## Known open defects

Unchanged from v1.6.0: **76** non-preview, enumerated with test ids in
[v1.6.0's notes](RELEASE_NOTES_v1.6.0.md#known-open-defects). No exporter
changed, so none moved. Sprint 3 burns them down.

## Limits

- Register **C7** is partial. `references` is populated and persisted, but the
  ODCS emitter consumes it in the next release.
- **C2** is the capability half only. The fields exist and round-trip; no
  emitter reads them yet.
- Six of fifteen reference-model entities declare no `agg_time_column` because
  they have no temporal column. They become dimension-only semantic models in
  the next release rather than acquiring an invented time axis.

## Upgrade notes

- One additive migration, `0013`. No destructive step.
- Container image tags move to `v1.7.0`.
- No configuration changes.
