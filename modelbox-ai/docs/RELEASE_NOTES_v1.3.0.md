# ModelBox AI — v1.3.0 Release Notes

**Tag:** `v1.3.0`  ·  **Cut from:** `main`  ·  **CI:** green (Backend Pytest + Frontend `tsc`/build)

ModelBox AI is an enterprise, LLM-agnostic data-modeling platform. This release
completes the v2.0 platform expansion across three pillars — **Designer &
Canvas**, **Migration & Governance Mesh**, and the **ModelBox Trainer** — and
brings the **frontend UI fully in line with the backend capability matrix**:
every backend service now has canvas/settings controls.

> Supersedes the never-tagged `v1.2.0` draft (backend-only). The delta since
> then is the Migration & Governance UI (§ "Frontend — Migration & Governance UI").

---

## Highlights

- **Migration & Governance Mesh** — reverse-engineer live databases, diff models
  into migration DDL, generate referentially-intact seed data, and emit
  governance data contracts + BI semantic layers — now driveable from the UI.
- **ModelBox Trainer** — Socratic tutoring, "Spot the Flaw" challenges, and
  auto-graded ERD rubrics.
- **Async synthesis at scale** — Celery/Redis worker queue with a per-task
  event-loop fix, plus frontend job polling.
- **81 backend tests**, multi-dialect exporters, JWT auth + workspace RBAC.

---

## Pillar 1 — Designer & Canvas Engine

- **FR-1.1 Async synthesis** — `POST /api/v1/jobs/synthesize` enqueues a Celery
  job (Redis broker); the web UI polls to completion.
- **FR-1.2 Canvas persistence** — `PUT /api/v1/model/{id}/graph` replaces a
  model's graph from the canvas, re-validates, and bumps the version.
- **Graph linter** — surfaces `CYCLIC_FK`, `MISSING_PK`, and `DANGLING_REF`
  (with precise entity/column source markers).

## Pillar 2 — Migration & Governance Mesh

- **FR-2.1 Brownfield introspection** — `POST /api/v1/connectors/introspect`
  reverse-engineers a live PostgreSQL schema via `INFORMATION_SCHEMA` (asyncpg),
  inferring PKs, FKs, and FACT/DIMENSION/TABLE types. Connection URIs are stored
  **AES-256-GCM encrypted** and never returned in the clear.
- **FR-2.2 Schema diffing** — `POST /api/v1/model/diff` compares two models into
  dialect-specific `ALTER`/`CREATE`/`DROP` DDL (via SQLGlot) and flags breaking
  changes. `GET /api/v1/model` lists workspace models to pick from.
- **FR-2.4 Synthetic seed data** — `POST /api/v1/model/{id}/export/synthetic-data`
  generates FK-consistent mock datasets in topological order, as SQL `INSERT`
  scripts or a per-entity CSV bundle. Dependency-free and deterministic.
- **FR-2.3 Data contracts** — `GET /api/v1/model/{id}/export/contract?format=…`
  - `opendatacontract` — Open Data Contract Standard v0.9.x YAML
  - `avro` — Apache Avro record schemas (nullable unions; logical types)
  - `protobuf` — proto3 messages with sequential field tags
- **FR-2.3 Semantic layers** — `GET /api/v1/model/{id}/export/semantic?engine=…`
  - `cube` (Cube.js) · `lookml` (Looker views) · `metricflow` (dbt MetricFlow)

## Pillar 3 — ModelBox Trainer

- **Socratic Tutor** (`POST /api/v1/trainer/socratic/step`), **Spot the Flaw**,
  and invariant **auto-grading** (`POST /api/v1/trainer/grade`), with the
  `/trainer` UI.

## Frontend — Migration & Governance UI (new in v1.3.0)

- **Connectors & Introspection** (`/settings/connectors`) — register encrypted
  DB connections and one-click introspect a live schema onto the canvas.
- **Schema Diff & Migration** — canvas "Diff & migrate" panel: pick a target
  model (via `GET /api/v1/model`), view the `ALTER` DDL and color-coded breaking
  changes.
- **Expanded export drawer** — tabs for Artifacts (DDL/dbt/Cube), Synthetic Seed
  (row-count slider), Data Contracts (ODCS/Avro/Protobuf), and Semantic Layers
  (Cube/LookML/MetricFlow), each rendered in Monaco with per-file download.

## Core & Platform

- **Synthesis engine** — NL/PRD/DDL → validated model; paradigms 3NF, Kimball,
  Data Vault, OBT; multi-provider LLM gateway (Anthropic, OpenAI, Gemini,
  Mistral, DeepSeek, Kimi, local Ollama / air-gapped vLLM).
- **AuthN/Z** — JWT bearer; workspace multi-tenancy; `OWNER > ADMIN > MEMBER`.
- **Appliance** — single-node Docker Compose: UI, backend, Celery worker,
  LiteLLM proxy, PostgreSQL 16, Redis 7, optional Ollama.

---

## Fixes since v1.2.0 draft

- **Celery worker event-loop crash** — `run_synthesis_job` builds/disposes a
  dedicated `AsyncEngine` per task; consecutive async jobs verified `COMPLETED`
  live.
- **Identifier sanitization** — model titles with spaces no longer leak into
  Protobuf package names / Avro namespaces (`_safe_identifier`).

## Notes / known items

- Async-job-created models default their `title` to `"Untitled Model"` (the job
  path does not yet propagate the request `title`). Cosmetic.
- **UI host port** — the web UI defaults to `:3000`; set `UI_PORT=13000` in
  `.env` (documented in `.env.example`) to avoid collisions with other local
  services on `:3000`.
- The appliance compose builds **local** image names, while `release.yml`
  publishes **GHCR** images (`ghcr.io/<owner>/modelbox-{backend,frontend}`).

---

## Publishing

`release.yml` builds and pushes the backend + frontend images to GHCR on any
`v*` tag, tagged `1.3.0`, `1.3`, and `latest`. Cut the tag from green `main`:

```bash
git tag v1.3.0
git push origin v1.3.0
```

Then watch the **Release Images** workflow publish to
`ghcr.io/<owner>/modelbox-backend` and `ghcr.io/<owner>/modelbox-frontend`.
