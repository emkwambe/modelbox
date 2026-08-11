# Sprint 3 — Exporter Truth

**Hand this file to Claude Code.** Branch `sprint/3-exporter-truth` from `main` at `v1.7.0`.
**Reference:** `docs/PROJECT_STATE_REPORT.md` §4 and §9 (B1, B14/H9, H2, H3, H5, H6, M3, M7, M11),
`ModelBox_AI_Enhancement_Blueprint.md` §3, `ModelBox_AI_Acceptance_Criteria.md` §B.
**Duration:** 2 weeks.

**Sprint premise:** this is the sprint the xfail inventory turns green. Sprint 2 built the
capability; this sprint makes the emitters consume it. Success is measured entirely in the
harness — not in code review, not in demos.

**Target: 76 → 2.** The two survivors are H1's seed tests
(`test_seed_respects_declared_length[G4]`, `test_seed_respects_quality_rules`), which the
plan assigns to Sprint 4. Everything else closes here. My earlier "76 → 0" was arithmetic
carried forward from before H1 entered the count — corrected now rather than discovered
at the end.

Every fix removes its `xfail` marker. `strict=True` means a fix without marker removal
turns CI red on XPASS. That is intended.

---

## Task 1 — MetricFlow (B1, 24 xfails) — the largest piece

Seven defects, all in `_metricflow`. Take them together; the harness cannot show progress
until `dbt parse` succeeds, and that needs the first five simultaneously.

1. **Missing `label`** on metrics (`exporter_service.py:531-548`).
2. **`ref('{name}')` → `ref('stg_{name}')`** (`:552` vs the dbt emitter at `:147`).
3. **Aggregation vocabulary.** `agg: avg` crashes dbt with a traceback; MetricFlow's term
   is `average`. Map the full vocabulary, and fail loudly on an unmapped aggregation
   rather than passing it through.
4. **`defaults.agg_time_dimension`** from Sprint 2's entity-level `agg_time_column`.
5. **Foreign entity naming.** Name the entity after the *parent's primary entity*, with
   `expr` carrying the local column. Currently named after the local FK column, so joins
   resolve only when FK name coincidentally equals parent PK name — latent in all five
   gold graphs, which is why the synthetic role-playing fixture exists.
6. **Primary entity on G3's satellite** — `banking-datavault` has an entity with no
   primary declared.
7. **Reserved granularity on G1** — `month` collides with a MetricFlow reserved word.

**Ruled behaviour for entities with no `agg_time_column`:** they emit **no measures** and
become dimension-only semantic models. Six of fifteen reference entities have no temporal
column and cannot acquire one honestly. Add the harness assertion that makes this rule
verifiable rather than incidental: *a semantic model with no `agg_time_column` declares no
measures.*

While here: `data_model.py` now has a shared `_is_temporal_type` and three exporters carry
private copies. Collapse them onto the shared predicate — this is where a disagreement
between them would bite.

## Task 2 — dbt self-containment (B14/H9, 5 · M7, 1 · M11, 4)

- **B14:** emit a `_sources.yml` declaring the `raw` sources the staging models reference.
  A generated project must parse standalone. The harness currently supplies sources
  derived from the emitted SQL so B1 and M11 aren't masked behind this;
  `test_dbt_project_is_self_contained` asserts the property with no scaffolding.
- **M7:** emit `packages.yml` whenever a model uses `dbt_expectations`.
- **M11:** remove the deprecated generic-test argument nesting.

## Task 3 — ODCS (H2, 5 · H2-ext, 5 · H2/H4, 5)

Verify the current spec with context7 before writing; my knowledge cuts off in May 2026
and this is exactly where it has already been wrong once.

- `apiVersion` to the current v3.1.0 line.
- Emit required top-level `version` and `status`.
- **Remove the `info:` block** (`exporter_service.py:378-382`) — it belongs to the rival
  Data Contract Specification, not ODCS. The artifact is currently a hybrid of two
  standards.
- `required` derived from `is_nullable`, not `is_primary_key`. Note the harness assertion
  was amended in Sprint 2 to test against a mutated graph, so it only passes if the
  emitter genuinely reads the field.
- **Consume `ColumnSchema.references`** via property-level `foreignKey` — this closes
  C7, which Sprint 2 left partial.

## Task 4 — Protobuf (H6, 10)

- Field tags from `stable_id`, never `enumerate()`. Sprint 2 allocated ids skipping
  19000–19999, so no special case is needed here.
- `NUMERIC → double` is wrong; money as float is a correctness defect, not a style one.
- Sanitise filenames.

The tag-stability test inserts a column and asserts no existing tag moves. It is the
criterion the whole `stable_id` design exists for.

## Task 5 — DDL (H5, 4 · H4/H3, 5)

- **H5:** emission order from `GraphEngine.topological_order`, with the existing
  `NetworkXUnfeasible` fallback the seed generator already uses.
- **H4/H3:** emit `NOT NULL` from `is_nullable`.

## Task 6 — Dialect certification (Q4, 15 preview)

Certify `postgres`, `snowflake`, `redshift`, `duckdb`. Label `bigquery`, `databricks`,
`clickhouse` as **Preview — not deployment-verified** in the export UI and the docs.

These 15 xfails stay `@pytest.mark.preview` and are **not** part of the burn-down. Do not
attempt to fix them. The deliverable is honest labelling, visible to a user before they
export.

## Task 7 — Cube (M3, 6)

Exclude foreign keys from measures; add the missing `BOOLEAN` branch in `_cube_type`.
LookML is demoted to preview and is out of scope — do not fix its three tests.

## Task 8 — SafeSQL Pro as a harness gate

The slot LookML vacated. Run every emitted DDL statement and dbt model through SafeSQL Pro
as a fidelity-harness step.

Scope it honestly: if integration proves larger than a day, report back rather than
absorbing it — the sprint's primary obligation is the burn-down. If it lands, it is a
Proof Log claim no competitor in this category can make.

---

## Definition of Done

1. **Inventory reads 2 non-preview, 18 preview.** Both survivors are H1, owned by Sprint 4.
2. Every fixed test has its `xfail` marker removed; no XPASS anywhere.
3. 5/5 gold graphs parse in every certified emitter's native toolchain.
4. Protobuf tag stability proven by insertion test.
5. Preview dialects visibly labelled in the export UI — no silent downgrade.
6. A semantic model with no `agg_time_column` declares no measures, asserted.
7. Standing DoD (Blueprint §7): six CI jobs green including the populated-database
   migration gate, docs updated in-PR, Proof Log updated, appliance smoke, tag from green
   `main`.

Register criteria closed: B1, B2, B4, B5, B6, B7, B8, B9, B10, B11, B12, B14, C2 (consumption
half), C7.

## Constraints

- Windows PowerShell, absolute paths, BOM-free UTF-8, direct file edits over heredocs.
- `backend/.venv` for app and pytest; `backend/.venv-tools` for the fidelity toolchain.
- No provider API keys.
- Verification standards 1–6 apply. Standard 5 in particular: for any fix where a
  plausible wrong implementation exists, show the test fails against it. The ODCS
  `required` derivation and the Protobuf tag stability both qualify.
- Standard 6: several of these fixes are on paths a round-trip could repair in transit.
  Assert at construction, not only after a save.
- Report anything that contradicts this prompt. Every sprint so far has improved because
  you did.
