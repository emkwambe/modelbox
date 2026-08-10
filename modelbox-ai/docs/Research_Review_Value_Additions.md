# Research Review — Value Additions for ModelBox AI

**Input:** `Data_Modeling_Roles_Research_Report_2026.md` (43 job postings; role/responsibility taxonomy)
**Reviewer question:** Which recommendations are *genuine, high-value* additions vs. already-shipped vs. feature creep?
**Date:** 2026-08-10

---

## TL;DR

The report's central thesis is sound and matches where ModelBox AI already points: **modeling is a bundle**, and the highest-growth work is governance, semantic layers, data contracts, data quality, and reverse engineering. But **most of Section 18's product recommendations are already implemented** — so the disciplined move is *not* to build the long list. Three additions are genuinely missing, high-frequency in the research, and cheap because they reuse existing engines:

1. **Governance lint pack** — extend the existing graph linter with convention/governance rules.
2. **Data dictionary / business glossary export** — a new exporter (Markdown/HTML).
3. **Finish multi-engine introspection** — complete the "coming soon" Snowflake/BigQuery/MySQL seam.

Everything else in Section 18 is either already done or is Trainer *course content* / scope drift.

---

## 1. Already shipped (do NOT rebuild)

The report (understandably, as an outside market scan) under-credits the current appliance. These Section-18 asks are **done**:

| Report recommendation | Status in ModelBox AI |
|---|---|
| Data contract exports (ODCS/Avro/Protobuf) — §18.A.5 | ✅ `export_data_contract` |
| Semantic layer exports (Cube/LookML/MetricFlow) — §18.A.5 | ✅ `export_semantic_layer` |
| dbt-native export (SQL + `schema.yml`) — §18.A.3 | ✅ `generate_dbt_project` |
| Data-quality scaffolding (dbt `unique`/`not_null`/`relationships`) — §18.A.3 | ✅ auto-generated per PK/FK |
| Reverse engineering / introspection — §18.A.4 | ✅ PostgreSQL (`INFORMATION_SCHEMA`, AES-256-GCM) |
| Migration: schema diff → ALTER — §18.A.4 | ✅ `POST /model/diff` |
| Methodology coverage (Kimball/3NF/Data Vault/OBT) — §18.A.1 | ✅ all four + paradigm transform |
| PII classification — §18.A.2 | ✅ `is_pii` / `pii_type` tags + canvas badges |
| Version-control-friendly (SQL/YAML as code) — §18.A.3 | ✅ file-map exports |
| Spot-the-Flaw / Socratic tutor / grading — §18.B | ✅ ModelBox Trainer |
| Reference architectures / templates | ✅ Business Requirements Library (5 scenarios) |

**Implication:** the marketing story ("we already do contracts + semantic layers + reverse-engineering") is stronger than the report assumes. Amplify it before building more.

---

## 2. Recommended additions (genuine gaps, ranked)

All three reuse an existing subsystem — additive, testable, no new architecture.

### Pick 1 — Governance Lint Pack  ★ highest value-to-effort
**Why:** Governance is the report's *fastest-growing secondary responsibility* (58%, §4/§13.4) and documentation is a "primary deliverable" (65–75%, §16.14). The current linter only checks structural integrity (`CYCLIC_FK`, `MISSING_PK`, `DANGLING_REF`).
**What:** Add governance/convention rules to `GraphEngine.validate` (same `ValidationReport`, same canvas overlay):
- naming-convention violations (e.g. fact/dim/hub prefixes, snake_case)
- `FACT` entity missing a declared **grain**
- entity/column missing a **description** (documentation gap)
- **PII exposure** warnings (PII column with no masking hint; PII on a wide OBT)
- orphan entity (no relationships), surrogate-key convention checks
**Cost:** Low — pure additions to one existing pure function; each rule is a unit test. No new endpoints.

### Pick 2 — Data Dictionary / Business Glossary Export
**Why:** Documentation/metadata is the most universal secondary (65–75%, §12/§16.14) and directly serves the "stakeholder artifacts" (§18.A.2) and "AI context provision" (§18.A.7) asks — one exporter covers three recommendations.
**What:** A new `ExporterService` family emitting a human-readable **data dictionary** (Markdown + HTML): entities, columns, types, PK/FK, PII flags, grain, descriptions, relationships — plus a business glossary section. Machine-readable JSON variant doubles as AI-agent context.
**Cost:** Low — identical pattern to the existing contract/semantic exporters; operates on `SynthesizedModel`; drops into the export drawer as another tab.

### Pick 3 — Finish Multi-Engine Introspection
**Why:** Reverse engineering is a named growth area (§13.7, §16.10) driven by cloud migration/M&A. The connectors UI already lists Snowflake/BigQuery/MySQL as "coming soon"; the backend returns `501` for anything but PostgreSQL.
**What:** Implement `information_schema`/catalog introspection for **Snowflake, BigQuery, MySQL** behind the existing `IntrospectionService.build_graph` (which is already engine-agnostic — only the metadata query differs).
**Cost:** Medium — one adapter per engine, but it *completes a half-built feature* rather than opening new scope. Sequence by demand (Snowflake first per §7/§9 tech matrix).

### Optional (small) — Amplify dbt test scaffolding
Already emits `unique`/`not_null`/`relationships`. Add `accepted_values` for enum-like/low-cardinality columns and surface tests as a first-class "Data Quality" view. Low effort, incremental.

---

## 3. Explicitly NOT now (feature creep / wrong layer)

Rejecting these *is* the point of the review:

| Report item | Verdict | Reason |
|---|---|---|
| Airflow DAG scaffolding (§18.A.2) | ✗ Drift | ModelBox designs models; it is not an orchestrator. Generating DAGs invites a maintenance surface far from the core. |
| Role-based persona views (§18.A.6) | ⟶ Defer | Large UI surface for marginal capability — the same model already exports role-relevant artifacts (DDL for DBAs, dbt/MetricFlow for AEs, dictionary for stakeholders). Revisit only if users ask. |
| Industry tracks, certification alignment, persona tutors (§18.B) | ✗ Wrong layer | These are **Trainer course content**, not appliance features — the report itself files them under "Course Development." Handle as curriculum, not code. |
| AI embeddings / RAG context store (§18.A.7) | ⟶ Defer | Vague and heavy; largely subsumed by the data dictionary + contracts + column metadata (Pick 2). Wait for a concrete consumer. |
| Auto "methodology advisor" (§18.B.4) | ⟶ Trainer | Risks a gimmick as a product feature; far stronger as the Trainer's interactive decision-tree content. |

---

## 4. Throughline

Every recommended pick **extends an engine ModelBox already owns** — the linter, the exporter dispatch, the introspection service — so each is additive, unit-testable, and ships without a new subsystem. That is precisely "more complete, not more sprawling." Suggested order: **Pick 1 (governance lint) → Pick 2 (data dictionary) → Pick 3 (multi-engine introspection)**, with the dbt-test amplification folded in opportunistically.
