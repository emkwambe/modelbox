# Module 4 — Data Quality Engineering, CI/CD Gates & Capstone

**Course:** Analytics Engineering & Modern Data Modeling
**Weeks:** 7–8  ·  **Prerequisites:** Module 3 (data contracts & governance)
**Appliance:** all labs run in ModelBox AI (`/canvas`, `/trainer`).

---

## Why this module

Module 3 turned the model into a **contract** — a promise about tiers, freshness,
sensitivity, and documentation. This module makes the promise **testable**. A
contract that no build enforces is a wish; a contract backed by automated tests
that fail the pipeline is a guarantee. Here you declare per-column **quality
rules** (numeric ranges, format patterns), export them as **dbt tests** and
**ODCS quality assertions**, and wire them into a **CI/CD quality gate** so bad
data — or a broken rule — never reaches a consumer. The capstone ties Modules 1–4
together: structure → semantics → contract → tested quality.

## Learning objectives

By the end of Module 4 you can:

1. Distinguish **schema tests** (does the column exist / is it unique) from
   **data-quality tests** (are the *values* in range / correctly formatted).
2. Declare **range** (`min_value`/`max_value`) and **regex** rules on a column.
3. Export those rules as **`dbt_expectations`** tests and **ODCS `quality`**
   assertions — the same rule, two engines.
4. Recognize a **broken rule** before it ships: the `INVALID_RANGE` and
   `INVALID_REGEX` lints.
5. Explain how a **CI/CD quality gate** (dbt test in a pipeline step) turns a
   contract into an enforced guarantee.
6. **Capstone:** take a model from raw structure to a tested, contract-backed
   deliverable.

---

## Lessons

### 4.1 Schema tests vs. data-quality tests
- **Schema test** — structural: `unique`, `not_null`, `relationships` (FK
  integrity). Modules 1–3 already emit these.
- **Data-quality test** — value-level: is `age` between 0 and 120? does
  `email` match an email pattern? This is what Module 4 adds.

Both belong in the contract; the second is where silent corruption hides.

### 4.2 Range rules
A **range** asserts a numeric column's values fall within `[min_value,
max_value]`. Declare it in the column editor's **Quality rules** section. It
exports to dbt as `dbt_expectations.expect_column_values_to_be_between` and to
ODCS as a `range` quality assertion.

### 4.3 Regex / format rules
A **regex** asserts a text column matches a pattern (email, ISO code, SKU
format). Declare it as **Regex pattern**. It exports to dbt as
`dbt_expectations.expect_column_values_to_match_regex` and to ODCS as a `regex`
quality assertion.

### 4.4 The broken-rule lints
A quality rule is only as good as its correctness. Two lints catch rules that
would silently fail or crash the build:
- **`INVALID_RANGE`** — `min_value > max_value`; no row can ever pass, so the
  test always fails (or, worse, is quietly ignored).
- **`INVALID_REGEX`** — a pattern that does not compile; the generated dbt test
  errors at run time.

Both are advisory warnings (they never invalidate the model), and both are
**fixable in-app** — correct the bounds or the pattern in the column editor. A
well-formed rule produces **no** lint: good quality is rewarded with silence.

### 4.5 The CI/CD quality gate
Export the model's dbt project and run `dbt test` as a pipeline step. If a range
or regex assertion fails, the step fails, and the deploy is blocked. That is the
whole point of a contract: **the promise is enforced by the build, not by
trust.** The same rule you declared on the canvas is the rule the gate runs.

### 4.6 The quality loop
Declare (range / regex on the column) → **persist** → **export** (dbt
`dbt_expectations` / ODCS `quality`) → **lint** (`INVALID_RANGE`,
`INVALID_REGEX`) → **grade** (the Trainer lab is scored by the same linter). One
engine governs the model, the exported tests, and your practice.

### 4.7 Capstone — structure to guarantee
Model a small domain end to end: design a valid star schema (M1), declare its
measures (M2), assign tiers/SLAs/PII and document it (M3), then add range/regex
quality rules and export a dbt project whose `dbt test` gate is green (M4). The
deliverable is a model that is **structurally sound, semantically governed,
contract-backed, and test-enforced.**

---

## Lab — "Spot the Flaw: Quality & Testing Edition"

**File:** `frontend/src/content/trainer/m4_lab1_quality_and_testing.json`
**Runs in:** `/trainer` (Select Lab → fix → Submit).

A signup model already declares column quality rules destined for dbt/ODCS tests
— but two are broken. **Both fixes are made in the column editor's Quality
rules section:**

| Flaw | Lint code | Fix (in-app) |
|---|---|---|
| `fact_signups.age` range has min 150 > max 18 | `INVALID_RANGE` | set a satisfiable range (e.g. 13–120) |
| `fact_signups.promo_code` regex won't compile | `INVALID_REGEX` | repair the pattern, e.g. `^[A-Z]{4}$` |

`dim_country.iso_code`'s `^[A-Z]{2}$` is **already correct** — a well-formed rule
raises no lint. Leave it alone.

**Done when:** re-validation is clean of those codes.

---

## Assessment rubric

| Criteria | Weight | Excellent |
|---|---|---|
| Rule declaration | 25% | Ranges/patterns declared on the columns that need them |
| Rule correctness | 25% | No `INVALID_RANGE` / `INVALID_REGEX`; correct rules left untouched |
| Export literacy | 20% | Can read the `dbt_expectations` tests + ODCS `quality` blocks |
| CI/CD reasoning | 15% | Explains how `dbt test` gates a deploy on the contract |
| Capstone integration | 15% | End-to-end model is valid, governed, and test-enforced |

## What's next

**Module 5 — Capstone: Full-Stack Modeling Mastery:** one model broken in all
four disciplines at once — structural, semantic, governance, and quality. Prove
you can hold the whole stack in your head and drive it to a clean, contract-backed
deliverable. Across the four modules you moved a model from **structure**
(dimensional design & grain) → **meaning** (the semantic layer) → **promise**
(data contracts & governance) → **guarantee** (tested quality with a CI/CD gate);
the capstone is where you do all four together.
