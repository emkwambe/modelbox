# Sprint 3 — progress and handoff state

**Branch:** `sprint/3-exporter-truth`, cut from `main` at `v1.7.0`.
**Spec:** `docs/SPRINT_3_PROMPT.md`. **Register:** §B. **Rulings:** Blueprint §3.

Resumable from the branch alone. Every decision below is already ruled.

---

## Target — revised

**77 → 3.** The prompt said 76 → 2; H10 was found during Task 3's spec check and
entered the inventory as an xfail before any fix, per the standing rule that
defects become tests before they become fixes.

| Survivor | Owner |
| :-- | :-- |
| `test_seed_respects_declared_length[healthcare-ehr]` (H1) | Sprint 4 |
| `test_seed_respects_quality_rules` (H1) | Sprint 4 |
| `test_odcs_quality_entries_use_v3_vocabulary` (H10) | Sprint 4 |

Preview stays at 18 and is not part of the burn-down.

## Status

| Task | State |
| :-- | :-- |
| — record C7-a, H10, open questions | **done** |
| 1 — MetricFlow (B1, 24) | in progress |
| 2 — dbt self-containment (B14 5 · M7 1 · M11 4) | not started |
| 3 — ODCS (H2 5 · H2-ext 5 · H2/H4 5) | not started |
| 4 — Protobuf (H6, 10) | not started |
| 5 — DDL (H5 4 · H4/H3 5) | not started |
| 6 — dialect certification (Q4, labelling only) | not started |
| 7 — Cube (M3, 6) | not started |
| 8 — SafeSQL | **dropped** — see below |

Invariant at every commit boundary — the burn-down should only ever fall:

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m "not preview" -q
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m preview -q   # 18, always
.venv/Scripts/python -m pytest -q
```

Every fix removes its `xfail` marker. `strict=True` turns a fix without marker
removal into a red XPASS.

---

## Ruled — do not re-litigate

### ODCS (Task 3), verified via context7 on 2026-08-11

- `apiVersion: v3.1.0`.
- Required top-level: **`apiVersion`, `kind`, `id`, `version`, `status`**.
  `name` optional; `dataProduct` deprecated since v3.1.0.
- **No `info:` block** — that is the Data Contract Specification, a different
  standard.
- **Property-level foreign key is `relationships: [{to: "<object>.<property>"}]`**,
  with `from` implicit. `type: foreignKey` is the *schema-level* construct and
  requires explicit `from` and `to`. Correction **C7-a**: C3 named this wrongly
  and Sprint 2's M6 ruling rested on the wrong name. The ruling holds; the
  construct did not. The shorthand happening to match `ColumnSchema.references`
  exactly is luck, not design.
- Quality entries are `{id, metric, mustBe*, arguments, unit, description}`,
  optional `type: library|sql|custom`. Our `{rule: …}` key does not exist —
  finding **H10**, Sprint 4.

### MetricFlow (Task 1)

- Primary entity keeps the **PK column name**; the foreign-entity fix must match
  something, and matching that name is what lets `expr` carry the local column.
- Entities with no `agg_time_column` emit **no measures** and become
  dimension-only. Six of fifteen reference entities. Asserted, not incidental.
- Reserved granularity names get a `_dim` suffix. **`defaults.agg_time_dimension`
  must reference the renamed dimension**, or fixing defect 7 silently undoes
  defect 4 — two fixes in one emitter, one quietly cancelling the other.
  Asserted specifically on `saas-subscription`, where the rename fires.
- An unmapped aggregation raises `ExporterError` rather than passing through. A
  crash inside `dbt parse` is a worse failure than a refused export.

### Task 8 — dropped, and it is not a scheduling problem

SafeSQL Pro is not on `PATH`, not on npm under plausible names, not on PyPI, and
unreferenced in the repo. Unobtainable dependency, so unknown work rather than a
day of work.

The larger point, which goes back to the product owner: **if SafeSQL Pro is a
hosted service, it cannot be a hermetic fidelity gate at all.** The harness is
offline by construction, and giving it network and credentials would break what
`MODELBOX_FIDELITY_STRICT` means — a gate that can fail for reasons unrelated to
the artifact is not a gate. That is an architectural constraint on the whole
dogfooding idea, not a sizing question. Re-scopeable in an hour given the
distribution model.

---

## Open questions raised, not resolved

**Role-playing dimensions in MetricFlow.** Under the ruled foreign-entity
naming, two FKs from one entity to the same parent produce two foreign entities
with the same name, distinguished only by `expr`. MetricFlow very likely rejects
duplicate entity names on a semantic model.

No gold graph has two FKs to one parent, so the burn-down is unaffected, and
`test_metricflow_foreign_entity_names_parent_primary` asserts *naming* rather
than that dbt parses the synthetic fixture. If the rejection is real, genuine
role-playing needs **separate semantic models per role** — a design question for
Sprint 4+, not something this fix resolves.

**Verification standard numbering.** The register has five standards. The
Sprint 3 prompt referred to "1–6"; its "standard 5" is the register's 1
(discriminating test) and its "standard 6" is the register's 5 (round-trip
masking). Use the register's numbering.
