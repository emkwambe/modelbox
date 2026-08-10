# Data Quality Engineering — Strategic Review

**Input:** `Data_Quality_Engineering_Breakdown.md`
**Reviewer question:** genuine appliance addition vs. already-shipped vs. creep;
course impact (Module 4).
**Date:** 2026-08-10

---

## TL;DR

ModelBox already ships the design-time half of data quality (dbt tests,
contracts, synthetic seed, the linter, CI gates via `X-API-Key`). The **one
genuine addition is declarable Range & Regex quality rules** — the same
declare → persist → export pattern as the shipped Visual Metric Builder. The
doc's runtime observability / anomaly detection / paging is **out of scope**: a
design-and-governance appliance is not a runtime monitoring engine.

## Part 1 — Already shipped (do NOT rebuild)

| Doc capability | Status |
|---|---|
| dbt tests: `unique`, `not_null`, `relationships`, `accepted_values` | ✅ `generate_dbt_project` |
| Quality rules embedded in contracts (ODCS/Avro/Protobuf) | ✅ `export_data_contract` |
| Synthetic seed to exercise constraints | ✅ `generate_synthetic_seed` (referentially intact) |
| Constraint/governance linter (naming, grain, docs, PII, orphan, fan-out) | ✅ `GraphEngine.validate` |
| CI/CD quality gates | ✅ `X-API-Key` + `POST /model/validate-graph` |

## Part 2 — Genuine addition vs. creep

### Addition — Range & Regex quality-rule declaration  ★
**Gap:** `ColumnSchema` has no `min_value` / `max_value` / `regex`, and the dbt
exporter emits no `dbt-expectations` or ODCS quality block for value bounds.
**What:** declare numeric bounds and text patterns on a column → propagate into
- dbt `schema.yml`: `dbt_expectations.expect_column_values_to_be_between`,
  `…_to_match_regex`;
- ODCS YAML: a `quality` block on the property.
**Pattern:** identical to Semantic Sprint 2 (declare → persist → export). Low creep.

### Rejected — Runtime observability & anomaly detection
The doc's runtime data observability, z-score anomaly detection, and PagerDuty
integration are **rejected**. Tracking live pipeline runs and querying warehouse
data for anomalies belongs in dedicated tools (Monte Carlo, Metaplane) — it is a
runtime execution/monitoring concern, not a modeling-appliance one. This is the
same "design-time, not runtime" line held in the semantic and governance reviews
(no consumer/dashboard tracking, no runtime RLS/CLS).

## Part 3 — Course impact (Module 4)

Module 4 (Quality Test Automation & Capstone) maps to shipped features + the
Range/Regex addition:
- **Week 7** — dbt tests / `dbt-expectations` / ODCS quality + synthetic seed
  (all runnable once Range/Regex lands).
- **Week 8** — CI/CD gates (`X-API-Key`, `validate-graph`) + **"Spot the Flaw —
  Quality Edition."** Note: the lab grader is lint-based, so quality labs use
  **lint-detectable** flaws — missing PK (no uniqueness), dangling FK (broken FK
  assertion), unclassified PII, missing docs — not "weak coverage" abstractions.

## The unifying insight

All three research reviews (semantic, governance, quality) converge on **one
pattern**: declare metadata on the model → persist → propagate to exports and
lints. Semantic (measures) is shipped; governance (tier/SLA) and quality
(range/regex) are the remaining picks and share the same machinery. See
`Unified_Sprint_Plan.md`.
