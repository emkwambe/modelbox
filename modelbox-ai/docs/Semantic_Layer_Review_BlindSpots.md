# Semantic Layer Breakdown — Appliance Blind-Spot Review

**Input:** `Semantic_Layer_Design_Development_Breakdown.md`
**Reviewer question:** What does the semantic-layer research imply is missing on the
appliance (blind spots) vs. already-shipped vs. feature creep — and what feeds course content?
**Date:** 2026-08-10

---

## TL;DR

ModelBox **already generates semantic layers** — the doc's flagship "Feature 1"
(auto-generate from the physical model) and most of "Feature 4" (multi-format
export) are shipped. The genuine appliance blind spots are small and fit engines
we already own:

1. **Fan-out / cardinality-risk lint** — the #1 semantic anti-pattern, and the
   linter never checks it. Highest value-to-effort.
2. **Richer semantic export** — current output is structural (measures + a count
   metric); add time granularities + a measure→metric scaffold.
3. **GraphQL schema export** — the one genuinely-missing format.

The big "semantic-layer management platform" items (impact analysis with
dashboard/consumer tracking, metric registry, RLS/CLS) are a **different product**
— don't drift there. The 8-week course module is strong material for Step 3.

---

## 1. Already shipped (do NOT rebuild)

| Doc "opportunity" | Status |
|---|---|
| **Feature 1 — auto-generate semantic layer from model** | ✅ `export_semantic_layer` → Cube.js / LookML / MetricFlow |
| **Feature 4 — multi-format export** | ✅ Cube/LookML/MetricFlow **+** ODCS/Avro/Protobuf contracts; "AI Context JSON" ≈ the data-dictionary JSON. Only GraphQL is missing. |
| **Feature 3 — business glossary** | ⚠️ Partial — the data dictionary (MD/HTML/JSON) already emits a glossary + FK lineage; missing synonyms + plain-English calc logic + consumer lineage. |
| Several design **principles** (business naming, grain-on-fact, documentation, PII) | ✅ enforced by the governance lint pack (`NAMING_CONVENTION`, `MISSING_GRAIN`, `MISSING_DESCRIPTION`, `PII_EXPOSURE`). |

**Implication:** the marketing line "ModelBox generates not just schemas but
semantic definitions" (the doc's bottom line) is *already true today*. Lead with it.

## 2. Genuine blind spots (fit existing engines, low creep) — the picks

### Pick 1 — Fan-out / cardinality-risk lint  ★ highest value-to-effort
**Why:** "Fan-out" is the doc's #1 anti-pattern and appears in its assessment
rubric ("no fan-outs"). The linter stores each relationship's cardinality but
**never validates it** — so a `N:M` edge or a fact→fact join that silently
inflates a `SUM` sails through clean.
**What:** add a governance rule (`FAN_OUT_RISK`, warning) that flags
many-to-many relationships and joins between two FACT entities — the exact
duplicate-row trap semantic layers fail on. Pure addition to `GraphEngine.validate`,
same `ValidationReport` + canvas overlay.
**Cost:** Low — one rule, unit-tested, no new subsystem.

### Pick 2 — Richer semantic export
**Why:** the current MetricFlow/LookML/Cube output is structurally correct but
thin: measures + a single count metric per model. The doc's rubric expects time
intelligence and usable metrics.
**What:** emit `time_granularities` on time dimensions and scaffold a simple
metric per numeric measure (so the file is closer to usable). **Do not** fabricate
business filters (e.g. `status='completed'`) — that needs business context; leave
it to the user/LLM.
**Cost:** Low-Med — extends the existing exporter.

### Pick 3 (optional) — GraphQL schema export
The one genuinely-missing format from Feature 4. A thin new exporter over the
model (types + relationships). Low effort; do only if a consumer wants it.

## 3. Feature creep / wrong layer (defer or reject)

| Doc item | Verdict | Reason |
|---|---|---|
| **Feature 2 — Semantic diff + impact analysis (which metrics/dashboards break)** | ⟶ Defer | Requires ModelBox to become a semantic-layer **registry** tracking metrics, dashboards, and consumers. The *physical* schema diff already ships; semantic-impact needs a consumer graph the product doesn't own — a platform pivot, not an increment. |
| **Feature 5 — "Spot the Flaw", semantic edition** | ⟶ Course/Trainer | Not core-appliance — it's **course content + a Trainer mode** (needs a gradable semantic-layer representation). Great for Step 3, scoped there. |
| Metric registry / owners / tiers / SSOT lifecycle, RLS/CLS access control | ✗ Reject | ModelBox models + exports; it is not a metric store or a runtime access-control engine. RLS/CLS belong to the warehouse/BI tool. |

## 4. Course content (feeds Step 3)

- The **8-week "Semantic Layer Mastery"** outline + assessment rubric is
  ready-to-adapt curriculum. It's a natural **Module 2** after a dimensional-
  modeling opener (Module 1).
- The **"Spot the Flaw — Semantic Layer Edition"** is the runnable-lab hook for
  that module: author flawed semantic definitions (missing filter, wrong grain
  placement, fan-out, missing owner/description) as Trainer challenges. This
  needs a new Trainer content type (a semantic-layer graph the grader
  understands) — a deliberate build to schedule with the course, not before it.
- Pick 1 (fan-out lint) doubles as the **auto-grader primitive** for the
  fan-out lab — the same rule that warns designers can score students.

## 5. Throughline

ModelBox already *generates* semantic layers; the disciplined additions **catch
semantic mistakes at design time** (fan-out lint) and **make the generated output
more usable** (richer export) — both extend engines we own. The
"semantic-layer-management-platform" features are a separate product; the course
module is where the rest of this research pays off.

**Recommended order:** Pick 1 (fan-out lint) → Pick 2 (richer export) → fold the
semantic-layer course module + Spot-the-Flaw into Step 3.
