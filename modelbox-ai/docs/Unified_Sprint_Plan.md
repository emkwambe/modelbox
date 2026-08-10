# Unified Sprint Plan — Declarative Metadata + Curriculum

Consolidates the three strategic reviews (Semantic Layer, Data Governance &
Contracts, Data Quality Engineering) into one dependency-ordered plan.

## The common vision

Every genuine pick across the three reviews is the **same pattern**:

> **Declare metadata on the model → persist it → propagate to exports, lints,
> and Trainer graders.**

- **Semantic** — declare *measures* (`is_metric` + aggregation) → MetricFlow/Cube/
  LookML + semantic diff. **✅ shipped (Sprints 1–3).**
- **Governance** — declare *asset tier + freshness SLA* on entities → ODCS
  `slaProperties`/`tier` + dbt meta + a `MISSING_SLA` lint. **Pending.**
- **Quality** — declare *range + regex* on columns → `dbt-expectations` + ODCS
  quality block. **Pending.**

Everything the reviews rejected is the *opposite* pattern — runtime/registry
platform features (consumer/dashboard tracking, runtime observability/anomaly
detection, metric registries, RLS/CLS). **Out of scope, permanently.**

---

## Done (context)

- **Semantic Sprints 1–3** — fan-out lint, Visual Metric Builder (declare →
  persist → export), semantic breaking-change diff.
- **Step 3 foundation** — lab JSON format + CI guard, Module 1 curriculum, the
  first runnable lab, and the in-app `/trainer` lab loader (load → validate →
  grade by the shipped linter).

## Remaining sprints (ordered)

### Sprint U1 — Module 2 (Semantic) curriculum + labs  *(no appliance build)*
Deps already shipped (Sprints 1–3 are the graders).
- `docs/curriculum/MODULE_2.md` (Semantic Layer Engineering).
- Semantic-edition labs: fan-out trap, missing-grain fact, an aggregate column
  that should be a declared measure. Graded by `FAN_OUT_RISK` / `MISSING_GRAIN`.
**Continues Step 3.**

### Sprint U2 — Asset Tiering & Freshness SLA  *(Governance Pick 1)*
Declare → persist → export, plus a lint for grading.
- `EntitySchema.tier` + `freshness_sla`; ORM + migration; persist through repo +
  reconstruction (as with `is_metric`).
- Canvas: entity-level settings (tier + SLA).
- Export: ODCS `slaProperties` / `tier` / real `owner`; dbt `schema.yml` meta.
- Lint: **`MISSING_SLA`** (a `TIER_1` asset with no SLA) — warning; grader for the
  governance lab.
- Then **Module 3** curriculum + governance-edition labs (PII, missing docs,
  naming, `MISSING_SLA`).

### Sprint U3 — Range & Regex quality rules  *(Quality Pick 1)*
Same pattern, column-level.
- `ColumnSchema.min_value` / `max_value` / `regex`; ORM + migration; persist.
- Canvas: extend the **column semantic popover** (Sprint 2) with a "Constraints"
  section.
- Export: dbt `dbt_expectations.expect_column_values_to_be_between` /
  `…_to_match_regex`; ODCS `quality` block on the property.
- Then **Module 4** curriculum + quality-edition labs (lint-detectable flaws:
  missing PK, dangling FK, unclassified PII, missing docs).

## Backlog (optional, unscheduled)
- GraphQL schema export (semantic review, Feature 4 gap).
- PII auto-*suggest* (governance review) — suggestion only, never auto-mutate.

## Out of scope (creep guard — do not build)
Consumer/dashboard impact tracking · metric registry / owners-tiers lifecycle ·
runtime observability, anomaly detection, paging · runtime RLS/CLS access control.

## Sequence

**U1 (Module 2 + semantic labs) → U2 (tiering/SLA + Module 3 + governance labs)
→ U3 (range/regex + Module 4 + quality labs).**

Each sprint: implement → pytest/tsc → commit → CI → deploy → live smoke-test.
Every new lab is gated by `test_trainer_labs.py` (its `expected_flaws` must match
the linter exactly), and every appliance pick is verified end-to-end
(declare → persist → export/lint) on the running appliance.
