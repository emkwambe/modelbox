# Module 5 — Capstone: Full-Stack Modeling Mastery

**Course:** Analytics Engineering & Modern Data Modeling
**Week:** 9 (capstone)  ·  **Prerequisites:** Modules 1–4
**Appliance:** runs in ModelBox AI (`/trainer` → *Capstone: Full-Stack Modeling Mastery*).

---

## Why this capstone

Modules 1–4 each taught one discipline in isolation: **structure** (dimensional
design), **meaning** (the semantic layer), **promise** (data contracts &
governance), and **guarantee** (tested quality). Real models are never flawed in
just one dimension. This capstone puts a single model in front of you that is
broken in **all four at once** — and asks you to make it whole. It is the exam
that proves you can hold the whole stack in your head and ship a model that is
**structurally sound, semantically governed, contract-backed, and
test-enforced.**

## What it assesses

You will diagnose and repair **seven flaws spanning four disciplines**, every one
fixable with the in-app editors you have used all course:

| Discipline | Flaw (in this model) | Lint code | In-app fix |
|---|---|---|---|
| **Structural** | `dim_customer` has no primary key | `MISSING_PK` | column editor → tick **🔑 Primary key** on `customer_sk` |
| **Semantic** | `fact_sales` has no declared grain | `MISSING_GRAIN` | entity settings → **Grain** |
| **Governance** | the `product` dimension lacks its `dim_` prefix | `NAMING_CONVENTION` | entity settings → **Name** = `dim_product` |
| **Governance** | `dim_customer.email` is unclassified PII | `PII_EXPOSURE` | column editor → tick **Contains PII** (EMAIL) |
| **Governance** | Tier-1 `fact_sales` has no freshness SLA | `MISSING_SLA` | entity settings → **Freshness SLA** |
| **Quality** | `fact_sales.quantity` range has min > max | `INVALID_RANGE` | column editor → **Quality rules** (fix min/max) |
| **Quality** | `product.sku` regex will not compile | `INVALID_REGEX` | column editor → **Quality rules** (fix the pattern) |

> Renaming `product` → `dim_product` **cascades** to the `fact_sales.product_sk`
> foreign-key relationship automatically — you fix the name once and the edge
> follows.

## Learning objectives

By completing the capstone you demonstrate you can:

1. **Triage across disciplines** — recognize, in one model, which flaws are
   structural vs. semantic vs. governance vs. quality.
2. **Apply the right fix with the right tool** — primary-key / PII toggles,
   the Name / grain / SLA fields, and the quality-rule inputs.
3. **Reason about cascade** — understand that a rename rewrites dependent
   foreign-key references so the graph stays consistent.
4. **Drive a model to a clean contract** — end with zero lints and exports
   (dbt + ODCS) that carry grain, tier, SLA, PII classification, and quality
   assertions.

---

## Lab — "Capstone: Full-Stack Modeling Mastery"

**File:** `frontend/src/content/trainer/m5_capstone_mastery.json`
**Runs in:** `/trainer` (Select Lab → fix → Submit).

A sales model — `fact_sales`, `dim_customer`, and a mis-named `product`
dimension — arrives with all seven flaws above. Work through the four
disciplines in any order; each fix uses an editor you already know. **Done when:
re-validation is completely clean** (no warnings, no errors) — the same bar a
production contract must clear.

### Suggested approach
1. **Structure first** — a model with no key can't be trusted downstream. Give
   `dim_customer` its primary key.
2. **Meaning** — declare `fact_sales`' grain so every measure is true at one
   grain.
3. **Governance** — rename `product` → `dim_product`, classify the PII, set the
   Tier-1 SLA. Watch the FK relationship follow the rename.
4. **Quality** — repair the impossible range and the uncompilable regex so the
   exported `dbt test` gate is green.
5. **Re-validate** — confirm zero issues, then export the dbt project + ODCS
   contract and read your governance + quality metadata riding along.

---

## Assessment rubric

| Criteria | Weight | Excellent |
|---|---|---|
| Structural integrity | 20% | Every entity has a key; no `MISSING_PK` |
| Semantic correctness | 20% | Grain declared; measures true at grain; no `MISSING_GRAIN` |
| Governance completeness | 30% | Correct naming, PII classified, SLA on critical assets; no `NAMING_CONVENTION` / `PII_EXPOSURE` / `MISSING_SLA` |
| Quality enforcement | 20% | Range/regex rules valid; no `INVALID_RANGE` / `INVALID_REGEX` |
| Clean contract | 10% | Final model validates clean; exports carry all metadata |

## Course completion

Clearing this capstone means you can take a model from raw structure to a
tested, contract-backed deliverable across the full arc of modern analytics
engineering:

**Structure → Meaning → Promise → Guarantee** — diagnosed and repaired in the
same appliance that enforces it, graded by the very linter that governs
production models.
