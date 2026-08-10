# Module 2 — Semantic Layer Engineering

**Course:** Analytics Engineering & Modern Data Modeling
**Weeks:** 3–4  ·  **Prerequisites:** Module 1 (dimensional design & grain)
**Appliance:** all labs run in ModelBox AI (`/canvas`, `/trainer`).

---

## Why this module

A validated star schema (Module 1) is the *structure*; the **semantic layer** is
the *meaning* — the governed metrics and dimensions every BI tool, API, and AI
agent consumes. Get it right and "Revenue" means one thing everywhere. This
module teaches you to turn a dimensional model into declared measures and
export a consistent semantic layer to dbt MetricFlow, Cube.js, and LookML — the
tools mentioned in ~45% of 2026 analytics-engineering roles.

## Learning objectives

By the end of Module 2 you can:

1. Distinguish **measures** (aggregatable numbers), **dimensions** (context),
   and **entities/semantic models** (business concepts).
2. **Declare measures** with the right aggregation directly on the canvas.
3. Keep **grain integrity** — one grain per semantic model, measures true at
   that grain.
4. Recognize **fan-out** in semantic models and relate facts through conformed
   dimensions, never fact-to-fact or many-to-many.
5. Export the same model to **MetricFlow / Cube.js / LookML** and know which fits.
6. Read a **semantic breaking-change** diff before a physical change ships.

---

## Lessons

### 2.1 The semantic layer, in one sentence
It is the "business API" for your data: a governed set of **metrics** and
**dimensions** defined once and served to every consumer. It sits on top of your
dbt/dimensional models.

### 2.2 Measures, dimensions, entities
- **Measure** — an aggregatable number (`SUM(order_total)`, `COUNT(DISTINCT
  user_id)`). Lives on a fact.
- **Dimension** — the "by what" (date, region, plan). Groups measures.
- **Entity / semantic model** — a business concept (Orders, Customers) grouping
  measures + dimensions at one grain.

### 2.3 Declaring measures in ModelBox — the Visual Metric Builder
Click a column on the canvas → the **Semantic role** popover → mark it a
**Σ Measure** and choose an aggregation (`SUM`, `COUNT`, `COUNT_DISTINCT`, `AVG`,
`MIN`, `MAX`), or a **Dimension**. Declared measures persist and drive the
MetricFlow / Cube / LookML exports — no export-time guessing.

### 2.4 Metric composability & time
Build metrics from measures, not by duplicating SQL (`LTV = ARPU / Churn`). Treat
time as first-class: a time dimension carries granularities so consumers can roll
up by day / week / month.

### 2.5 Grain integrity in semantic models
Each semantic model has **one grain**. A monthly-recurring-revenue model is
"one row per subscription per month"; a usage model is "one row per event." Never
mix them — split into separate semantic models. The **`MISSING_GRAIN`** lint
flags a fact with no declared grain.

### 2.6 Fan-out & conformed dimensions
A fact joined **many-to-many** to a dimension, or **fact-to-fact**, duplicates
rows and inflates measures. Relate facts only through **conformed dimensions**
(shared, identical). The **`FAN_OUT_RISK`** lint flags both traps on the canvas.

### 2.7 Exporting the layer
One model → three engines (**Export artifacts → Semantic**):
- **MetricFlow** — dbt-native; measures + a metric per measure.
- **Cube.js** — API-first / embedded analytics.
- **LookML** — Looker-native.

### 2.8 Semantic breaking-change diff
Before dropping or retyping a column, **Diff & migrate** shows a **Σ Semantic
impact** section: which declared measures or metrics a physical change would
break — so you never silently break a dashboard.

---

## Lab — "Spot the Flaw: Semantic Edition"

**File:** `frontend/src/content/trainer/m2_lab1_semantic_grain_and_fanout.json`
**Runs in:** `/trainer` (Select Lab → fix → Submit).

A SaaS analytics model came back from review. It is structurally valid but has
three semantic-layer flaws:

| Flaw | Lint code | Fix |
|---|---|---|
| `fact_usage` has no declared grain | `MISSING_GRAIN` | declare "one row per usage event" |
| `fact_usage` joined many-to-many to `dim_feature` | `FAN_OUT_RISK` | resolve the M:N through a bridge/conformed dimension at the right grain |
| `dim_feature` is undocumented | `MISSING_DESCRIPTION` | describe the entity and its columns |

**Done when:** re-validation is clean of those codes.

---

## Assessment rubric

| Criteria | Weight | Excellent |
|---|---|---|
| Measure declaration | 25% | Correct measures + aggregations; no numeric column left ambiguous |
| Grain integrity | 25% | One grain per semantic model; no mixing |
| Fan-out avoidance | 25% | Facts conform through shared dimensions; no M:N / fact-to-fact |
| Export correctness | 15% | MetricFlow/Cube/LookML reflect the declared semantics |
| Documentation | 10% | Semantic models and measures are described |

## What's next

**Module 3 — Data Contracts, Governance & Quality:** turn this governed semantic
model into enforceable contracts (ODCS/Avro/Protobuf), asset tiers + SLAs, and
PII classification.
