# Sprint 2 — IR Foundation

**Hand this file to Claude Code.** Branch `sprint/2-ir-foundation` from `main` at `v1.6.0`.
**Reference:** `docs/PROJECT_STATE_REPORT.md` §3 and §9 (H4, M6, Q6, Q8),
`ModelBox_AI_Enhancement_Blueprint.md` §3, `ModelBox_AI_Acceptance_Criteria.md` §C.
**Duration:** 1.5 weeks.

**Sprint premise:** the IR cannot express what four exporters need, so each one guesses
and they guess differently — Avro says every non-PK is nullable, Protobuf says nothing
is, ODCS says only PKs are required, DDL says nothing at all. This sprint adds the
missing capability and proves it round-trips. **It changes no exporter output.** Sprint 3
consumes what this sprint builds.

That constraint is load-bearing. If an exporter changes here, the fidelity harness will
flip xfails outside the sprint that owns them, and the burn-down stops meaning anything.

---

## Task 1 — Consolidate persistence (Q8) — do this first

`GraphRepository._persist` (`graph_repository.py:85-102`) and
`SynthesisEngine._persist_graph` (`synthesis_engine.py:278-295`) are duplicated
column-by-column, and `graph_repository.py:5-6` acknowledges it. Every subsequent task in
this sprint would otherwise be written twice.

Collapse to one path. `SynthesisEngine` calls `GraphRepository`. Verify no behavioural
change: the existing suite must pass untouched before any new field is added. Commit this
separately so the diff is reviewable on its own.

## Task 2 — `stable_id` on `ColumnSchema` (Q6)

**Design, ruled:** a per-entity monotonic integer, allocated at first persist, **never
reused**, persisted, and immutable thereafter. Not a UUID — a small positive int, because
the same value becomes the Protobuf field tag in Sprint 3 and tags are wire-size-sensitive.

Requirements:

- Allocation from a high-water mark stored **on the entity**, not computed as
  `max(existing) + 1`. Deleting the highest column must not free its id for reuse — that
  is precisely the wire-compatibility break H6 is about.
- Immutable across canvas reorder, rename, and type change. A reorder changes
  `ordinal_position`; it must not touch `stable_id`.
- Backfill in the migration for every existing persisted column, in current
  `ordinal_position` order so today's Protobuf tags are preserved rather than shuffled.
- Skip the Protobuf-reserved range 19000–19999 at allocation time so Sprint 3's emitter
  needs no special case.

This field is why the diff engine can distinguish a rename from a drop-plus-add in
Sprint 4. Test that property here even though the diff engine does not yet use it.

## Task 3 — Constraint fields on `ColumnSchema` (H4)

Add `is_nullable`, `is_unique`, `default_value`, `check_expression`.

**Default for `is_nullable` is `True`, with primary keys forced `False`.** That is the SQL
default and it matches what the current DDL already implies by emitting no `NOT NULL`, so
existing models keep their present meaning rather than acquiring a claim nobody made.
Introspection should populate all four truthfully from the source system — a brownfield
model must not be silently marked nullable when the warehouse says otherwise.

## Task 4 — Aggregation time dimension (B1's fourth defect)

Add an entity-level `agg_time_column` (or a column-level `is_agg_time_dimension` — your
call, argue it) so MetricFlow can emit `defaults.agg_time_dimension` in Sprint 3. dbt
requires it on any semantic model declaring measures; its absence is one of the four
parse blockers.

Populate it in the five gold graphs. Do not touch the MetricFlow emitter.

## Task 5 — Migration

One additive Alembic migration for Tasks 2–4. Nullable with defaults; no destructive
operations.

**Verify against a populated database, not an empty one.** Seed the appliance Postgres
with models from all five gold graphs, run `alembic upgrade head`, and confirm every model
loads and exports byte-identically to its pre-migration output. Byte-identical is the
assertion — this sprint changes no output.

Include a downgrade path and test it.

## Task 6 — `ColumnSchema.references` (M6) — populate only

M6 was "wire it or delete it." **Wire it.** ODCS v3.1.0 has native property-level
`foreignKey`, which gives the field the named downstream consumer it was missing —
recorded as correction C3.

Scope here is **populate and persist only**: introspection and synthesis fill it, the
canvas can set it, it survives round-trip. The ODCS emitter consuming it lands in Sprint 3
with the rest of H2, so this sprint still changes no output.

## Task 7 — Canvas controls

Extend `ColumnSemanticEditor.tsx` for every new field. Nullability and uniqueness are
checkboxes; default and check are text with validation; `references` is an entity/column
picker; `agg_time_column` is an entity-level select over that entity's time columns.

`stable_id` is displayed read-only, never editable. If it can be edited it is not stable.

## Task 8 — Synthesis prompt

Update the LLM prompt and structured-output schema to populate nullability, uniqueness,
and the aggregation time dimension.

**Keep the new fields optional in the response schema with server-side defaults.** A
weaker local model that omits them must still produce a valid model rather than failing
synthesis outright. "LLM-agnostic" is a claim this sprint can quietly break — a schema
that only the strongest cloud model satisfies makes air-gapped mode worse without anyone
noticing until Sprint 5's conformance harness runs.

## Task 9 — Round-trip tests

`test_column_semantics_roundtrip.py` is the template. A model with every new field
populated must survive `POST /model/{id}/graph` → reload → export with zero loss, across
the single consolidated persistence path.

Specific properties to assert: `stable_id` immutable across reorder; `stable_id` not
reused after delete; `is_nullable` default is `True` and forced `False` on PKs;
`references` survives; `agg_time_column` survives.

---

## Definition of Done

1. One persistence path; `_persist_graph` gone.
2. Migration verified against a populated database; every gold graph exports
   byte-identically pre- and post-migration; downgrade tested.
3. Round-trip lossless for all new fields, proven by test.
4. `stable_id` immutable across reorder and never reused after delete.
5. Canvas sets every new field; synthesis populates them; a model omitting them still
   synthesises.
6. **Fidelity harness inventory unchanged: 76 non-preview xfails, 18 preview.** Any
   movement means an exporter changed and is out of scope.
7. Standing DoD (Blueprint §7): six CI jobs green, docs updated in-PR, Proof Log updated,
   appliance smoke, tag from green `main`.

Register criteria closed by this sprint: C1, C2 (capability half), C3, C6, C7.

## Constraints

- Windows PowerShell, absolute paths, BOM-free UTF-8.
- `backend/.venv` for app and pytest; `backend/.venv-tools` for the fidelity toolchain.
- No provider API keys.
- **Do not change any exporter.** If a fix is one line and obvious, note it for Sprint 3
  and leave it.
- Do not flip any xfail. The H4/H3 and H2/H4 cases depend on these fields but belong to
  Sprint 3.
- Report anything that contradicts the audit, the blueprint, or this prompt. The last two
  sprints both improved because you did.
