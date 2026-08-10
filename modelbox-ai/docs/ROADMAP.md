# ModelBox AI — Next Steps, Adjacent Use Cases & Growth Roadmap

*Companion to the PRD/TRD. Grounded in what actually ships today (`main`), not aspiration.*

---

## 0. What exists today (baseline)

| Layer | Shipped |
| :---- | :------ |
| Synthesis | NL → validated ERD (3NF / Kimball / Data Vault / OBT) via LLM gateway with failover; deterministic `N:1` normalization |
| Graph engine | NetworkX cycle / missing-PK / dangling-ref lints; topological ordering |
| Canvas | React Flow, linter overlay, PII/grain badges, export panel, rename/delete |
| Exporters | Multi-dialect DDL (SQLGlot), dbt staging + schema.yml, Cube.js, ZIP |
| Platform | JWT auth, self-registration, workspace multi-tenancy, RBAC (OWNER/ADMIN/MEMBER) |
| Infra | Docker appliance, Alembic migrations, CI on every push, GHCR release on tags |
| Providers | US (OpenAI/Anthropic/Gemini) · EU (Mistral) · APAC (DeepSeek/Kimi) · local (Ollama/vLLM) |

**Honest gaps** (things the PRD implies but that are NOT built yet): reverse-engineering existing DBs, saving manual canvas edits back to the model, async (non-blocking) synthesis, schema diff/versioning, LookML/MetricFlow export, data contracts, audit trail, SSO/OIDC.

---

## 1. Adjacent use cases (same engine, new leverage)

These reuse the existing NL→graph→exporter pipeline + multi-tenant platform with **little to no new core code** — mostly new *inputs* or new *exporters*.

### A. Brownfield / reverse engineering  ⭐ highest market unlock
Today the tool is greenfield-only (NL in). The dependencies already bundle `snowflake-connector`, `databricks-sql-connector`, `google-cloud-bigquery`, `psycopg2`, `pymysql`, `duckdb`. Connect to an existing warehouse → introspect schema → load onto the canvas → lint → re-model / migrate. **Turns "design a new schema" into "understand and modernize the schema you have"** — a far bigger buyer.

### B. Data contracts & event schemas
New exporter targets from the same model: **JSON Schema / Avro / Protobuf**. Producer→consumer contracts for microservices; validate proposed schema changes in CI. The `ExporterService` dispatch pattern extends directly.

### C. Automated data catalog / glossary
Synthesis already generates descriptions + PII flags. Point that capability at an existing DB to **auto-document cryptic columns** (`usr_lgn_dt` → "User last login timestamp") and tag PII/PHI for access control. A governance product hiding inside the modeling product.

### D. Schema drift & migration diffing
`data_models.version_number` + the graph engine are the foundation. Diff two model versions (git-like) → generate **`ALTER` DDL** + a migration plan. Pairs naturally with (A).

### E. Synthetic / seed data
From model constraints (cardinality, nullability, FK integrity) emit **Faker / SQL `INSERT` scripts** that honor referential integrity — schema-valid mock data for QA/sandboxes without touching production data.

### F. Semantic-layer breadth
We export Cube.js today; add **LookML** and **MetricFlow** (already named in the PRD) from the same `suggested_metrics`. The semantic-layer export could stand alone as its own wedge.

### G. Beyond databases (same primitive)
The core primitive is "NL → typed entity graph → codegen". That also produces **OpenAPI / GraphQL** schemas, **Terraform** for warehouse provisioning, or **Kafka topic** schemas. Each is a new exporter, not a new engine.

---

## 2. Taking it to the next level (prioritized execution)

Ranked by **leverage ÷ effort**. Effort: S ≈ days, M ≈ 1–2 wks, L ≈ 3+ wks.

### Tier 1 — do these first (unblock scale + real usage)

| # | Item | Effort | Why it matters |
| - | ---- | :----: | -------------- |
| T1 | **Async synthesis jobs** (Celery/Redis — already in deps, unused) | M | Synthesis is a 60–90s **blocking HTTP call** (we hit the 2-min limit live). Move to a job + poll/WebSocket: no timeouts, progress UI, survives reloads. Biggest robustness/UX win. |
| T2 | **Persist canvas edits** | M | Manual node/column/edge edits aren't saved back. Wire canvas mutations → a `PUT /model/{id}/graph` (reuse `_persist_graph`). Without this the canvas is view-only after synth. |
| T3 | **Reverse-engineering connector** (start with Postgres) | M–L | The brownfield unlock (§1.A). One connector proves the pattern; others follow. |

### Tier 2 — product depth

| # | Item | Effort | Why |
| - | ---- | :----: | --- |
| T4 | **Schema diff + `ALTER` generation** | M | Versioning → migration story (§1.D). |
| T5 | **LookML + MetricFlow exporters** | S–M | Cheap breadth on an existing pattern (§1.F). |
| T6 | **Data-contract exporter** (JSON Schema/Avro/Protobuf) | M | New market, same dispatch (§1.B). |
| T7 | **Audit trail** (append-only: model id, prompt hash, user, ts) | S | PRD §9.4 requirement; also the base for cost/token logging the gateway already hooks. |

### Tier 3 — enterprise & scale

| # | Item | Effort | Why |
| - | ---- | :----: | --- |
| T8 | **SSO / OIDC hardening** (the audit's F1: RS256, `aud`/`iss`) | M | Real IdP integration; enterprise gate. |
| T9 | **Real-time collaboration** (multi-user canvas, presence) | L | Zustand → shared server state (Yjs/CRDT or WS). |
| T10 | **Rate limiting + per-workspace quotas / cost caps** | S–M | Multi-tenant safety; the LLM gateway is the choke point. |

---

## 3. Production hardening (parallel track)

- **Secrets**: move API keys to Vault / AWS Secrets Manager (`hvac` already in deps) — currently plain `.env`.
- **Observability**: structured JSON logs + request tracing + LLM token/cost metrics (gateway `_maybe_mask` / routing is the natural instrumentation point).
- **Deploy story**: turn the GHCR images into a **Helm chart** / one-click cloud template (the appliance is compose-only today).
- **Test depth**: add tests for the exporters against real dialect execution (Snowflake/Postgres containers) — TS-03 in the PRD QA matrix is currently unproven end-to-end.
- **Frontend session**: consider `httpOnly` cookies over `localStorage` for JWT (audit F4) if the threat model tightens.

---

## 4. Suggested 30 / 60 / 90

- **30 days** — T1 (async jobs) + T2 (persist canvas edits). These make the *current* product genuinely usable at scale; everything else is additive.
- **60 days** — T3 (Postgres reverse-engineering) + T4 (diff/ALTER). Opens the brownfield/migration market — the biggest TAM jump.
- **90 days** — T5/T6 (semantic + contract exporters) + T7 (audit) + T8 (OIDC). Enterprise-ready breadth.

---

## 5. The one-line thesis

> The core asset isn't "an AI that draws ERDs" — it's a **deterministic NL → typed-graph → codegen pipeline with governance and multi-region routing.** Every item above is a new *input* (reverse-engineering), a new *output* (contracts, LookML, Terraform), or *scale* (async, collaboration) on that same spine.
