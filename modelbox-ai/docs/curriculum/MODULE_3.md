# Module 3 — Data Contracts, Governance & Quality

**Course:** Analytics Engineering & Modern Data Modeling
**Weeks:** 5–6  ·  **Prerequisites:** Module 2 (semantic layer engineering)
**Appliance:** all labs run in ModelBox AI (`/canvas`, `/trainer`).

---

## Why this module

A validated star schema (Module 1) is the *structure*; the semantic layer
(Module 2) is the *meaning*. A **data contract** is the *promise* — the machine-
checkable agreement between a producer and its consumers about what a dataset
contains, how fresh it is, how sensitive it is, and what "correct" means. Without
it, every downstream dashboard, API, and AI agent is coupled to an implementation
that can change without warning. This module teaches you to turn a governed model
into an enforceable contract: **asset tiers + freshness SLAs**, **PII
classification**, **documentation**, and export to the **Open Data Contract
Standard (ODCS)** and **dbt** — the governance vocabulary now expected in senior
analytics-engineering and data-platform roles.

## Learning objectives

By the end of Module 3 you can:

1. Explain what a **data contract** is and why it decouples producers from
   consumers.
2. Assign an **asset tier** (`TIER_1_CRITICAL` → `TIER_4_EXPERIMENTAL`) and a
   **freshness SLA** to an entity, and justify the choice.
3. **Classify PII** columns so the contract governs personal data explicitly.
4. Document entities and columns to a contract-ready standard.
5. Export the contract to **ODCS** (`tier`, `slaProperties`) and **dbt**
   (`meta`) and read what each field promises.
6. Recognize the governance lints — **`MISSING_SLA`**, **`PII_EXPOSURE`**,
   **`MISSING_DESCRIPTION`** — and clear them in-app.

---

## Lessons

### 3.1 What a data contract is
A contract is an explicit, versioned agreement about a dataset's **schema**,
**semantics**, **freshness**, **sensitivity**, and **quality**. It turns "trust
me" into "here's the checkable promise." When the producer changes something the
contract forbids, the change is caught *before* it reaches a consumer.

### 3.2 Asset tiers — not all data is equal
A tier states how much the organization depends on an asset, and therefore how
much rigor it warrants:

| Tier | Meaning |
|---|---|
| `TIER_1_CRITICAL` | Business-critical; drives revenue/exec decisions/regulatory reporting. |
| `TIER_2_IMPORTANT` | Widely used; a break is felt across teams. |
| `TIER_3_STANDARD` | Normal production asset. |
| `TIER_4_EXPERIMENTAL` | Prototype/sandbox; no downstream promises. |

Set the tier in ModelBox from an entity's **settings** popover (click the entity
node → *Entity settings* → **Tier**). It persists on the model and propagates to
the exports.

### 3.3 Freshness SLAs
A tier without a freshness promise is a hollow contract. A **freshness SLA**
states how recent the data is guaranteed to be — e.g. `< 1h`, `< 4h`, `< 24h`.
Declare it alongside the tier. The **`MISSING_SLA`** lint flags any
`TIER_1_CRITICAL` or `TIER_2_IMPORTANT` asset that promises importance but
declares no freshness guarantee. (Lower tiers are exempt — they make no such
promise.)

### 3.4 PII classification
A contract must say which columns carry personal data. Classifying a column
(`is_pii` + a `pii_type` such as `EMAIL`, `SSN`, `PHONE`) is what lets downstream
tooling mask, restrict, or audit it. ModelBox's **`PII_EXPOSURE`** lint flags a
column that *looks* like PII (its name matches a sensitive pattern) but is **not**
classified — the exact governance gap contracts exist to close. Fix it in the
column editor: select the column → tick **Contains PII** → choose the type.

> The lint flags the *gap*, not correctly-tagged PII. A well-classified column
> stays quiet — good governance is rewarded with silence.

### 3.5 Documentation as a contract term
Consumers can't sign a contract against an asset they can't understand. Every
entity and column should carry a description. The **`MISSING_DESCRIPTION`** lint
flags undocumented entities and columns. Set an entity's description in its
**settings** popover.

### 3.6 Exporting the contract
One governed model → contract artifacts (**Export artifacts**):
- **ODCS (Open Data Contract Standard)** — the tier appears as `tier`, the
  freshness SLA as `slaProperties: [{ property: freshness, value: "< 1h" }]`.
- **dbt `schema.yml`** — governance metadata rides in the model's `meta` block
  (tier, freshness SLA), so it travels with your dbt project.

The **same** metadata you declare on the canvas is what the contract exports —
declare once, propagate everywhere.

### 3.7 The governance loop
Declare (tier / SLA / PII / description on the model) → **persist** → **export**
(ODCS/dbt) → **lint** (`MISSING_SLA`, `PII_EXPOSURE`, `MISSING_DESCRIPTION`) →
**grade** (the Trainer lab is scored by the very same linter). One engine governs
the model, the exports, and your practice — they can never drift.

---

## Lab — "Spot the Flaw: Governance & Contracts Edition"

**File:** `frontend/src/content/trainer/m3_lab1_governance_and_contracts.json`
**Runs in:** `/trainer` (Select Lab → fix → Submit).

A customer-360 model is heading to production behind a contract. It is
structurally sound and correctly named, but a governance review flagged three
gaps. **Every fix is made with the in-app editors** — no code, no re-modeling:

| Flaw | Lint code | Fix (in-app) |
|---|---|---|
| `fact_orders` is `TIER_1_CRITICAL` but has no freshness SLA | `MISSING_SLA` | Entity settings → **Freshness SLA** = `< 1h` |
| `dim_customer.email` looks like PII but isn't classified | `PII_EXPOSURE` | Column editor → tick **Contains PII** (EMAIL) |
| `dim_marketing` has no description | `MISSING_DESCRIPTION` | Entity settings → write a **description** |

**Done when:** re-validation is clean of those codes.

---

## Assessment rubric

| Criteria | Weight | Excellent |
|---|---|---|
| Tiering | 25% | Tier matches the asset's real business criticality; justified |
| Freshness SLA | 25% | Critical/important assets carry a realistic SLA; no `MISSING_SLA` |
| PII classification | 25% | Every sensitive column classified; no `PII_EXPOSURE` |
| Documentation | 15% | Entities and columns described; no `MISSING_DESCRIPTION` |
| Export literacy | 10% | Can read the tier/`slaProperties`/`meta` in the ODCS & dbt exports |

## What's next

**Module 4 — Data Quality Engineering:** move from *promising* quality to
*testing* it — range and regex/pattern rules, dbt tests, and the quality gate
that keeps a contract honest at build time.
