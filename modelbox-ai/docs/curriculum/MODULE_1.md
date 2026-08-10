# Module 1 — Dimensional Schema Design & Grain Declaration

**Course:** Analytics Engineering & Modern Data Modeling
**Weeks:** 1–2  ·  **Prerequisites:** working SQL, basic relational concepts
**Appliance:** all labs run in ModelBox AI (`/` studio, `/canvas`, `/trainer`).

---

## Why this module

Everything downstream — semantic layers (Module 2), contracts and governance
(Module 3), production CI/CD (Module 4) — sits on top of a sound dimensional
model. Get the **grain** wrong and every metric built above it is wrong. This
module teaches you to translate business requirements into a star schema with an
explicit, defensible grain, and to recognize the traps (fan-out, mixed grain)
before they reach a dashboard.

## Learning objectives

By the end of Module 1 you can:

1. Translate a business requirement into conceptual → logical → physical models.
2. Distinguish **facts** (measurable events) from **dimensions** (descriptive
   context) and choose the right entity type.
3. Declare the **grain** of a fact table in one sentence and defend it.
4. Design **conformed dimensions** shared across facts.
5. Explain **SCD Type 2** and when to track dimension history.
6. Identify **fan-out** risk (fact-to-fact / many-to-many joins) and avoid it.
7. Judge when **One Big Table (OBT)** beats a star, and the trade-off.

---

## Lessons

### 1.1 From requirements to a conceptual model
Business language first: nouns become entities, verbs/events become facts.
"A customer places an order for products" → entities *Customer*, *Product*;
event *Order*. Draft the conceptual model before touching types or keys.

*In ModelBox:* describe the domain on the home studio and **Synthesize** — or
load a **Requirements Library** template to inspect a gold-standard star.

### 1.2 Facts vs. dimensions
- **Fact** — a measurable business event at a fixed grain (an order line, a
  payment, a session). Holds **measures** (additive numbers) + foreign keys to
  dimensions.
- **Dimension** — the "who / what / where / when" context (customer, product,
  date). Holds descriptive attributes and a surrogate key.

*In ModelBox:* set each entity's type on the canvas; FACT/DIMENSION drive the
exports and the linter.

### 1.3 Grain — the most important sentence you'll write
The **grain** is the meaning of one row: *"one row per order line"*,
*"one row per subscription per month"*. Rules:
- Declare it **before** adding measures.
- **One grain per fact.** Never mix order-level and line-item-level measures in
  one table (split them).
- Every measure must be true **at that grain**.

*In ModelBox:* declare the grain on each FACT entity. The **`MISSING_GRAIN`**
lint flags a fact with no declared grain.

### 1.4 Conformed dimensions
A dimension shared across facts (e.g. `dim_date` used by orders *and* sessions)
must be **identical** everywhere — same keys, same attributes. Conformity is
what lets you compare metrics across processes.

### 1.5 Slowly Changing Dimensions (SCD Type 2)
When a customer's tier or region changes, do you overwrite (Type 1) or keep
history (Type 2)? **Type 2** adds `valid_from` / `valid_to` / `is_current` and a
new surrogate key per version — so a historical order still maps to the tier the
customer had *then*. Use it when point-in-time accuracy matters.

*In ModelBox:* the SaaS Subscription Requirements-Library template is a worked
SCD2 dimension.

### 1.6 Fan-out — the silent measure-inflator
Joining a fact to another fact, or through a many-to-many relationship,
**duplicates rows** and inflates `SUM`s. A returns fact joined to a sales fact at
sale grain double-counts revenue. Keep facts joined only through **conformed
dimensions**; relate fact-to-fact through a shared dimension, not directly.

*In ModelBox:* the **`FAN_OUT_RISK`** lint flags many-to-many relationships and
fact-to-fact joins on the canvas.

### 1.7 Star vs. OBT
- **Star** — normalized dimensions; flexible, conformed, storage-efficient.
- **OBT (One Big Table)** — everything denormalized into one wide table; simplest
  for non-technical users and fastest for simple queries, at the cost of
  redundancy and storage. Choose OBT for a single, well-understood consumer;
  choose a star when dimensions are shared and reused.

---

## Lab — "Spot the Flaw: Dimensional Edition"

**File:** `frontend/src/content/trainer/m1_lab1_grain_and_fanout.json`
**Runs in:** `/trainer` (load the flawed graph → validate → fix → re-validate).

You are handed a flawed e-commerce star. Find and fix the seeded issues, graded
by the shipped linter:

| Flaw | Lint code | What you should do |
|---|---|---|
| A FACT named `sales` with no prefix | `NAMING_CONVENTION` | rename to `fact_sales` |
| `fact_sales` has no declared grain | `MISSING_GRAIN` | declare "one row per sale line" |
| `fact_returns` joined directly to `fact_sales` | `FAN_OUT_RISK` | relate through a conformed dimension instead |

**Done when:** re-validation is clean of those codes.

---

## Assessment rubric

| Criteria | Weight | Excellent |
|---|---|---|
| Grain declaration | 30% | Every fact has one explicit, correct grain; no mixed grain |
| Fact/dimension typing | 20% | Correct types; measures live only on facts |
| Conformed dimensions | 20% | Shared dimensions are identical across facts |
| Fan-out avoidance | 20% | No fact-to-fact / many-to-many measure inflation |
| Documentation | 10% | Entities and key columns are described |

## What's next

**Module 2 — Semantic Layer Engineering:** turn this validated star into
governed metrics (dbt MetricFlow, Cube.js, LookML) using the Visual Semantic
Metric Builder.
