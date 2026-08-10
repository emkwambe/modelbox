# ModelBox AI — v1.2.0 Release Notes

**Tag:** `v1.2.0`  ·  **Cut from:** `main` @ `83f31e5`  ·  **CI:** green (Backend Pytest + Frontend `tsc`/build)

ModelBox AI is an enterprise, LLM-agnostic data-modeling platform. This is the
first tagged release and consolidates the v2.0 platform expansion across three
pillars — **Designer & Canvas**, **Migration & Governance Mesh**, and the
**ModelBox Trainer** — on top of the core synthesis engine.

---

## Highlights

- **Migration & Governance Mesh** — reverse-engineer live databases, diff models
  into migration DDL, generate referentially-intact seed data, and emit
  governance data contracts + BI semantic layers.
- **ModelBox Trainer** — Socratic tutoring, "Spot the Flaw" challenges, and
  auto-graded ERD rubrics (the teaching engine for RealityDB Academy).
- **Async synthesis at scale** — Celery/Redis worker queue with a per-task
  event-loop fix, plus frontend job polling.
- **80 backend tests**, multi-dialect exporters, JWT auth + workspace RBAC.

---

## Pillar 1 — Designer & Canvas Engine

- **FR-1.1 Async synthesis** — `POST /api/v1/jobs/synthesize` enqueues a Celery
  job (Redis broker); the web UI polls to completion.
- **FR-1.2 Canvas persistence** — `PUT /api/v1/model/{id}/graph` replaces a
  model's graph from the canvas, re-validates, and bumps the version.
- **Graph linter** — topological/structural validation surfaces `CYCLIC_FK`,
  `MISSING_PK`, and `DANGLING_REF` (with precise entity/column source markers).

## Pillar 2 — Migration & Governance Mesh

- **FR-2.1 Brownfield introspection** — `POST /api/v1/connectors/introspect`
  reverse-engineers a live PostgreSQL schema via `INFORMATION_SCHEMA` (asyncpg),
  inferring PKs, FKs, and FACT/DIMENSION/TABLE types. Connection URIs are stored
  **AES-256-GCM encrypted** and never returned in the clear (masked as
  `postgresql://***`).
- **FR-2.2 Schema diffing** — `POST /api/v1/model/diff` compares two models into
  dialect-specific `ALTER`/`CREATE`/`DROP` DDL (via SQLGlot) and flags breaking
  changes (dropped tables/columns, type alterations).
- **FR-2.4 Synthetic seed data** — `POST /api/v1/model/{id}/export/synthetic-data`
  generates FK-consistent mock datasets in topological order (parents before
  children), as SQL `INSERT` scripts or a per-entity CSV bundle. Dependency-free
  and deterministic.
- **FR-2.3 Data contracts** — `GET /api/v1/model/{id}/export/contract?format=…`
  - `opendatacontract` — Open Data Contract Standard v0.9.x YAML
  - `avro` — Apache Avro record schemas (nullable `["null", T]` unions;
    decimal/date/timestamp logical types)
  - `protobuf` — proto3 messages with sequential field tags
- **FR-2.3 Semantic layers** — `GET /api/v1/model/{id}/export/semantic?engine=…`
  - `cube` — Cube.js schema files
  - `lookml` — Looker views (`dimension` / `dimension_group` / `measure`)
  - `metricflow` — dbt MetricFlow YAML (`semantic_models` + `metrics`)

## Pillar 3 — ModelBox Trainer

- **Socratic Tutor** — `POST /api/v1/trainer/socratic/step` guides learners with
  questions, never full solutions.
- **Spot the Flaw** — defective seed graphs for learners to diagnose.
- **Auto-grading** — `POST /api/v1/trainer/grade` scores ERDs against invariants
  (`NO_CYCLIC_FK`, `PK_PRESENT`, `NO_DANGLING_REF`).
- **`/trainer` UI** — assignment + tutoring experience.

## Core & Platform

- **Synthesis engine** — NL/PRD/DDL → validated model; paradigms 3NF, Kimball,
  Data Vault, OBT; multi-provider LLM gateway (Anthropic, OpenAI, Gemini,
  Mistral, DeepSeek, Kimi, local Ollama / air-gapped vLLM).
- **Exporters (v1)** — multi-dialect SQL DDL, dbt project, Cube.js.
- **AuthN/Z** — JWT bearer; workspace multi-tenancy; `OWNER > ADMIN > MEMBER`
  RBAC.
- **Appliance** — single-node Docker Compose (`docker-compose.appliance.yml`):
  UI, backend, Celery worker, LiteLLM proxy, PostgreSQL 16, Redis 7, optional
  Ollama.

---

## Fixes in this release

- **Celery worker event-loop crash** — `run_synthesis_job` now creates and
  disposes a dedicated `AsyncEngine` per task, so consecutive async jobs each
  run on their own `asyncio.run()` loop (previously job #2 raised
  *"Task … attached to a different loop"*). Verified live: two back-to-back jobs
  both reached `COMPLETED`.
- **Identifier sanitization** — model titles with spaces (e.g.
  `"Untitled Model"`) no longer leak into Protobuf package names or Avro
  namespaces; `_safe_identifier` coerces them to valid snake_case identifiers
  (`untitled_model`).

## Notes / known items

- Async-job-created models default their `title` to `"Untitled Model"` (the job
  path does not yet propagate the request `title`). Cosmetic.
- The appliance compose builds **local** image names
  (`modelbox/core-engine`, `modelbox/web-ui`), while `release.yml` publishes
  **GHCR** images (`ghcr.io/<owner>/modelbox-backend`, `…-frontend`). Intentional
  — different consumption paths.

---

## Publishing

`release.yml` builds and pushes the backend + frontend images to GHCR on any
`v*` tag, tagged `1.2.0`, `1.2`, and `latest`. Cut the tag from green `main`:

```bash
git tag v1.2.0
git push origin v1.2.0
```

Then watch the **Release Images** workflow publish to
`ghcr.io/<owner>/modelbox-backend` and `ghcr.io/<owner>/modelbox-frontend`.
