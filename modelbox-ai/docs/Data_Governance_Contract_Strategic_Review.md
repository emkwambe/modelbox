# Data Governance & Contract Architecture — Strategic Review

**Input:** `Data_Governance_Contract_Architecture_Breakdown.md`
**Reviewer question:** genuine appliance gaps vs. already-shipped vs. feature creep,
and how it shapes the course (Module 3).
**Date:** 2026-08-10

---

## TL;DR

ModelBox already ships most of the doc's governance recommendations (contract
exports, the 5-rule linter incl. `ip_address`, PII overlays, schema diff,
`X-API-Key`). The **one genuinely high-value, low-creep gap is Asset Tiering &
Freshness SLA declaration** — it mirrors the just-shipped Visual Metric Builder
(declare metadata → persist → propagate to exports).

**Consistency flag:** the doc's gap #2 (Downstream Consumer Impact against
Tableau / Power BI / APIs / ML feature stores) is the **same external-consumer
tracking I rejected as creep in the semantic-layer review**. Tracking live
external systems is a platform pivot, not an increment. Reject as written; only a
strictly *in-model declared-consumer tag* is defensible, and even that is
optional.

---

## Part 1 — Already shipped (do NOT rebuild)

| Doc feature | Status |
|---|---|
| **Multi-format contracts** (ODCS YAML, Avro, Protobuf) — Feature 6 | ✅ `export_data_contract` |
| **Naming standard validator** — Feature 3 | ✅ `NAMING_CONVENTION` lint |
| **PII flagging on canvas + into ODCS** — part of Feature 4 | ✅ `PII_EXPOSURE` (+`ip_address`), `🔓` overlay, `classification: PII` in ODCS |
| **Governance linter (5 rules)** | ✅ naming / grain / description / PII / orphan |
| **Schema diff + breaking changes** — physical part of Feature 2 | ✅ `DiffEngine` (+ semantic breaks, Sprint 3) |
| **dbt tests** (`unique`/`not_null`/`relationships`/`accepted_values`) | ✅ `generate_dbt_project` |
| **CI/CD via API keys** | ✅ `X-API-Key` |
| **Business glossary / metadata JSON** — Feature 1 (partial) | ✅ data dictionary (MD/HTML/JSON) |

**Implication:** "ModelBox generates governed contracts + lints for governance"
is already true. The ODCS export currently hardcodes `owner: modelbox` and a
default version, and has no asset tier or SLA — that's the real gap below.

## Part 2 — Genuine gaps vs. creep

### Pick 1 — Asset Tiering & Freshness SLA declaration  ★ the real win
**Gap:** contracts use default metadata (hardcoded owner/version, no tier, no SLA).
**What:** add `tier` (e.g. `TIER_1`…`TIER_4`) and `freshness_sla` (free-text,
e.g. `< 1 hour`) — and optionally `owner` — as **entity-level** fields; declare
them on the canvas (entity settings, same pattern as the measure popover);
**persist** them (ORM + migration, like `is_metric`); and **propagate** into the
ODCS YAML (`slaProperties`, `tier`, `owner`) and dbt `schema.yml` meta.
**Cost:** Med. **Pattern:** identical to Semantic Sprint 2 (declare → persist →
export). Low creep, high enterprise signal.

### Pick 2 (optional) — PII auto-suggest
**Gap:** `PII_EXPOSURE` flags unclassified PII but doesn't help fix it.
**What:** when it fires, the finding suggests a `pii_type` + masking hint in the
message (a *suggestion*, never auto-mutating the user's model). Low effort.

### Rejected / rescoped

| Doc item | Verdict | Reason |
|---|---|---|
| **#2 Downstream Consumer Impact** (diff vs. Tableau / Power BI / APIs / ML feature stores) | ✗ Creep (as written) | Tracking live external consumers is a registry/platform pivot — the exact thing rejected in the semantic-layer review. If ever pursued, restrict to a **declared in-model consumer tag** (a string list the diff echoes); build **no** live BI/feature-store integration. |
| **Auto-mutate PII tags** (Feature 4 auto-tag + auto-add access policy) | ⟶ Suggest only | Silently rewriting a user's classifications/policies is unsafe; keep it advisory (Pick 2). |
| Governance operating models, approval workflows, audit-log runtime, lineage-to-consumers | ✗ Reject | These are org/runtime concerns, not a modeler's output. |

### Governance "Spot the Flaw" (Feature 5)
Course/Trainer content — **bundle with Step 3 / Sprint 4**. Graders reuse the
existing governance lint (PII, description, naming) plus the new tier/SLA checks
from Pick 1 (e.g., "Tier 1 asset with no SLA", "unclassified PII", "no owner").

## Part 3 — Course impact (Module 3)

The 8-week syllabus is sound and maps cleanly:
- **Module 3 (Contracts, Governance & Quality)** aligns with shipped features
  (ODCS/Avro/Protobuf, dbt tests, the 5-rule linter, PII) **plus Pick 1**
  (asset tiering + SLA) — so the "Enforcing … SLA Contract Declarations" lab is
  runnable once Pick 1 lands.
- The **"Spot the Flaw — Governance Edition"** lab is graded by the governance
  lint + tier/SLA checks — the same grader-reuse pattern as the semantic edition.

## Throughline

Lead with **Asset Tiering & SLA** (clean, mirrors Sprint 2, feeds Module 3).
Hold the line on **consumer-impact tracking** — it's creep here just as it was
for the semantic layer. Governance Spot-the-Flaw + the syllabus land in Step 3.

**Recommended order:** Pick 1 (tiering/SLA) → Module 1 & 2 curriculum → Trainer
"Spot the Flaw" labs (semantic + governance) with Step 3.
