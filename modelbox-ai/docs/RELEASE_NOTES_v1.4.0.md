# ModelBox AI — v1.4.0 Release Notes

**Tag:** `v1.4.0`  ·  **Cut from:** `main`  ·  **CI:** green (Backend Pytest + Frontend `tsc`/build)

This release builds on the completed v2.0 platform ([v1.3.0](RELEASE_NOTES_v1.3.0.md))
with a **Business Requirements Library**, a **governance lint pack**, a
**data-dictionary exporter**, and **multi-engine brownfield introspection**
(PostgreSQL, Snowflake, BigQuery, MySQL) — the highest-value additions from the
2026 data-modeling-roles research review, each extending an engine ModelBox
already owns rather than adding a new subsystem.

---

## Highlights

- **Business Requirements Library** — 5 gold-standard starter scenarios, dual-mode launch.
- **Governance Lint Pack** — 5 convention/governance rules on the graph linter.
- **Data Dictionary & Glossary exporter** — Markdown / HTML / JSON.
- **Multi-engine introspection** — Postgres, Snowflake, BigQuery, MySQL.
- **Connection management** — `DELETE /connectors/{id}`.

---

## Business Requirements Library

Accessible from the home prompt bar ("📚 Explore Requirements Library") and the
Trainer header ("📚 Library"). Five gold-standard scenarios — Subscription
Analytics (Kimball/SCD2/MRR), E-Commerce (Kimball/order-line grain), Retail
Banking (Data Vault), Healthcare EHR (3NF/PII), Marketing Attribution (OBT) —
each with a raw prompt, a pre-built verified graph, and a modeling rationale.

- **Mode A — Synthesize Live**: populates the prompt + paradigm.
- **Mode B — Inspect Gold-Standard Graph**: hydrates the graph onto the canvas
  with **no LLM call** (zero latency/tokens); PK and PII badges included.

## Governance Lint Pack (FR-2.3)

Five additive, **warning-severity** rules on `GraphEngine.validate` (never
invalidate a model — `is_valid` still keys off errors only). They surface on the
canvas node cards (badge + tooltip + amber border), with a column-level `🔓`
highlight for unclassified PII.

| Rule | Flags |
|---|---|
| `NAMING_CONVENTION` | non-snake_case, missing type prefix (`dim_`/`fact_`/`hub_`/`lnk_`/`sat_`), PK without key suffix |
| `MISSING_GRAIN` | FACT entities with no declared business grain |
| `MISSING_DESCRIPTION` | undocumented entities and columns |
| `PII_EXPOSURE` | columns that look like PII (email/ssn/phone/dob/…) but aren't classified |
| `ORPHAN_ENTITY` | isolated nodes in a multi-entity model (single-table/OBT exempt) |

Live-verified: reintrospecting ModelBox's own DB surfaced **41 findings** across
all five rules (previously "0 issues"), with `is_valid` still True.

## Data Dictionary & Glossary Exporter (Pick 2)

`GET /api/v1/model/{id}/export/dictionary?format=markdown|html|json` and a
"Dictionary" tab in the export drawer:

- **Markdown** — per-entity column tables (name/type/key/PII/description) with
  resolved FK targets, a relationships table, and a business glossary.
- **HTML** — self-contained styled page (escaped, PII-highlighted).
- **JSON** — machine-readable metadata; structured context for AI agents.

## Multi-Engine Brownfield Introspection (FR-2.1, Pick 3)

`POST /api/v1/connectors/introspect` now dispatches on engine and reuses the
engine-agnostic `build_graph` with a per-engine type map:

| Engine | Driver | Notes |
|---|---|---|
| PostgreSQL | asyncpg | `INFORMATION_SCHEMA` (unchanged) |
| Snowflake | snowflake-connector-python | keys via `SHOW PRIMARY/IMPORTED KEYS` |
| BigQuery | google-cloud-bigquery | service-account JSON; `<project>.<dataset>.INFORMATION_SCHEMA` |
| MySQL | aiomysql | `key_column_usage` FKs; `tinyint(1)→BOOLEAN` |

Type maps normalize each dialect (e.g. Snowflake `NUMBER→DECIMAL`,
`TIMESTAMP_NTZ→TIMESTAMP`; BigQuery `INT64→BIGINT`, `GEOGRAPHY→JSON`; MySQL
`mediumtext→TEXT`). Drivers are lazy-imported — a missing driver returns a clear
`501`, not a crash. Connection URIs stay AES-256-GCM encrypted.

## Connection Management

`DELETE /api/v1/connectors/{id}` (ADMIN+) with a per-row Delete button in the
`/settings/connectors` UI. Migration `0008` adds `MYSQL` to the allowed engines.

## Other

- **dbt exporter** now scaffolds `accepted_values` tests for well-known
  categorical columns (`status`, `tier`, `priority`, `severity`) — real values,
  never fabricated — alongside the existing `unique`/`not_null`/`relationships`.
- Trainer integration for the Requirements Library.
- `canvasStore.loadGraph` gained an optional `paradigm` argument.
- Appliance compose image tags bumped to `v1.3.0`; `UI_PORT` documented.

## Known items / notes

- Async-job-created models still default their `title` to `"Untitled Model"`.
- Live Snowflake/BigQuery paths reach their real drivers (verified: graceful
  502 on bad account/credentials); MySQL is native once `aiomysql` is installed
  (now in requirements). BigQuery/MySQL end-to-end need real accounts to verify.

---

## Publishing

`release.yml` builds and pushes backend + frontend images to GHCR on any `v*`
tag, tagged `1.4.0`, `1.4`, and `latest`. Cut from green `main`:

```bash
git tag v1.4.0
git push origin v1.4.0
```
