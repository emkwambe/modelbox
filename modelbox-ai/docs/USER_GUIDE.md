# ModelBox AI — User Guide

ModelBox AI is an LLM-agnostic **data modeling & governance mesh**: synthesize
validated models from plain language, reverse-engineer live warehouses, lint for
governance, diff & migrate schemas, and export production artifacts — dbt, data
contracts, semantic layers, dictionaries, and seed data.

This guide walks data teams through the seven core workflows. All actions are
available in the web UI; every one is also scriptable via the API (see
[API_REFERENCE.md](API_REFERENCE.md)).

**Getting in:** open the appliance (e.g. `http://localhost:13000`), sign in, and
you land on the home studio. The top nav links to Canvas, Trainer, Connectors,
and API keys.

---

## Workflow 1 — Greenfield AI synthesis & interactive canvas

1. On the home page, describe your domain in plain language (or paste a PRD /
   raw DDL). Example: *"Track customers, subscriptions, and monthly recurring
   revenue with tier changes over time."*
2. Choose a **paradigm** (3NF, Kimball, Data Vault, OBT) and a **dialect**.
3. Click **Synthesize model**. Synthesis runs as an async job and streams to
   completion, then opens the **Canvas**.
4. On the canvas: drag entities, edit columns, add relationships, and use
   **Auto-layout**. **Save** persists the graph and re-validates; **Rename** and
   **Delete** manage the model.

> New to the tool? Click **📚 Explore Requirements Library** for 6 gold-standard
> starter scenarios — load one onto the canvas instantly (no LLM call) or use it
> as a prompt.

**API:** `POST /api/v1/jobs/synthesize` → poll `GET /api/v1/jobs/{id}` →
`GET /api/v1/model/{id}`.

## Workflow 2 — Brownfield database introspection

Reverse-engineer an existing schema onto the canvas.

1. Go to **Connectors** (`/settings/connectors`).
2. **Add connection**: name, engine, and a connection URI. Supported engines:
   **PostgreSQL, Snowflake, BigQuery, MySQL**. URIs are stored **AES-256-GCM
   encrypted** and never shown again.
   - PostgreSQL / MySQL: `postgresql://user:pass@host:5432/db`, `mysql://user:pass@host:3306/db`
   - Snowflake: `snowflake://user:pass@account/DB/SCHEMA?warehouse=WH`
   - BigQuery: paste the service-account JSON key as the URI.
3. Click **Introspect →**, enter the schema/dataset, and ModelBox builds a model:
   entities, columns, PK/FK, and inferred FACT/DIMENSION/TABLE types — then opens
   it on the canvas.

**API:** `POST /api/v1/connectors` then `POST /api/v1/connectors/introspect`.

## Workflow 3 — Governance linting & PII classification

Every validation run includes the **governance lint pack** (advisory warnings —
they never block a model). On the canvas, affected nodes show an amber badge +
tooltip, and unclassified-PII columns get a `🔓` highlight.

Rules: `NAMING_CONVENTION`, `MISSING_GRAIN`, `MISSING_DESCRIPTION`,
`PII_EXPOSURE` (columns that look like PII but aren't classified), and
`ORPHAN_ENTITY`. Structural errors (`CYCLIC_FK`, `MISSING_PK`, `DANGLING_REF`)
still invalidate a model.

Fix findings by adding descriptions, declaring FACT grains, renaming to
conventions (`dim_`/`fact_`/… prefixes, `_id`/`_sk` key suffixes), and tagging
PII columns. Re-validate to confirm.

**API:** `POST /api/v1/model/{id}/validate`.

## Workflow 4 — Schema diffing & breaking-change migration

Compare two model versions into migration DDL.

1. On the canvas, open **Diff & migrate**.
2. Pick a **target model** (V2) from the dropdown and a **dialect**.
3. **Compute diff** renders the `ALTER`/`CREATE`/`DROP` DDL and a color-coded
   list of **breaking changes** (dropped tables/columns, type alterations).
4. **Copy** the DDL into your migration tool.

**API:** `POST /api/v1/model/diff` with `{source_model_id, target_model_id, dialect}`.

## Workflow 5 — Exporting data contracts & dbt

Open **Export artifacts** on the canvas. Tabs:

- **Artifacts** — multi-dialect SQL DDL, a **dbt** project (staging models +
  `schema.yml` with `unique`/`not_null`/`relationships` and `accepted_values`
  tests), and Cube.js. Download individual files or the dbt/Cube project `.zip`.
- **Contracts** — **OpenDataContract** YAML, **Apache Avro**, **Protobuf**.
- **Semantic** — Cube.js, **LookML**, **dbt MetricFlow**.

**API:** `GET /api/v1/model/{id}/export?format=…`,
`…/export/contract?format=…`, `…/export/semantic?engine=…`.

## Workflow 6 — Generating data dictionaries

Open **Export artifacts → Dictionary**. Choose a format:

- **Markdown** — per-entity column tables (type/key/PII/description), resolved FK
  targets, a relationships table, and a business glossary.
- **HTML** — a self-contained, styled documentation page.
- **JSON** — machine-readable metadata; feed it to AI agents or a catalog.

**API:** `GET /api/v1/model/{id}/export/dictionary?format=markdown|html|json`.

## Workflow 7 — CI/CD integration via API keys

Automate ModelBox from pipelines and agents.

1. Go to **API keys** (`/settings/api-keys`).
2. **Generate key** with a name. Copy the `mb_live_...` secret shown **once**.
3. Store it as a CI secret. Send it as an `X-API-Key` header — no interactive
   login. The key authenticates as its creating user and inherits that user's
   RBAC. Revoke anytime from the same page.

```bash
# Example: export a data contract in CI
curl -H "X-API-Key: $MODELBOX_KEY" \
  "http://modelbox.internal:8000/api/v1/model/$MODEL_ID/export/contract?format=avro"
```

**API:** `POST /api/v1/auth/api-keys`, `GET /api/v1/auth/api-keys`,
`DELETE /api/v1/auth/api-keys/{id}`.

---

## Roles & access

Workspaces are multi-tenant with `OWNER > ADMIN > MEMBER`. Members synthesize and
edit models; ADMIN+ manage connectors and API keys and delete models. See the
[API Reference](API_REFERENCE.md) for per-endpoint requirements.

## Learn by doing — ModelBox Trainer

The **Trainer** (`/trainer`) teaches modeling with a Socratic tutor,
"Spot the Flaw" challenges, and auto-graded rubrics — and can load Requirements
Library scenarios straight into the sandbox.
