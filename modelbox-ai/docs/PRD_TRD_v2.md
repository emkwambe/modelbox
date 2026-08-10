# ModelBox AI v2.0 — Master PRD & TRD (Unified)

*Supersedes the v1 spec (`../../ModelBox AI PRD & TRD Specification.md`) for forward planning.*
*Unifies the three-pillar v2.0 expansion with the **shipped** v1 codebase on `main`.*
*Every place this doc corrects the original v2.0 draft to match real code is tagged `⟳ reconciled` and listed in Appendix A.*

---

## Part 0 — v1 Baseline: what is already shipped (do NOT rebuild)

| Capability | Where it lives | Reuse for v2 as |
| :---- | :---- | :---- |
| NL → validated model | `services/synthesis_engine.py` (`SynthesisEngine.synthesize`) | wrap in async job (FR-1.1) |
| Graph model type | `schemas/data_model.py::SynthesizedModel` (entities/relationships/metrics) | **this IS the "DataModelGraph"** used everywhere below ⟳ |
| Graph lints + ordering | `services/graph_engine.py::GraphEngine` — `validate()`, `detect_cycles()`, **`topological_order()`**, `dependency_layers()` | grading invariants (FR-3.3), seed ordering (FR-2.4) ⟳ |
| Persistence | `SynthesisEngine._persist_graph()` (entities→columns→relationships) | back `PUT /graph` (FR-1.2) |
| Exporters | `services/exporter_service.py::ExporterService` (**instance methods** over `SynthesizedModel`): `generate_ddl/dbt/cube`, `export()`, zip | extend with contract/semantic/synthetic methods (FR-2.3/2.4) ⟳ |
| Reconstruction | `SynthesisEngine.get_model()`, `.validate_model()` | diff inputs (FR-2.2) |
| Auth / tenancy / RBAC | `core/security.py`, `api/v1/dependencies.py` (`get_current_user`, `require_membership`, `require_model_role`, `get_authorized_model`) | gate every new route |
| Multi-region LLM gateway | `services/llm_gateway.py` (routing, failover, `drop_params`, air-gap egress) | Socratic tutor (FR-3.1), introspection enrichment |
| Metadata store | `models/metadata_store.py` — PKs are **`Uuid`** named `workspace_id`/`user_id`/`model_id`/… (NOT `id`) ⟳ | migrations `0001`–`0004` applied; v2 adds `0005` |
| Migrations | Alembic `0001`–`0004` (schema, auth, N:1, FK indexes) | v2 = `0005` |
| CI / release | `.github/workflows/ci.yml` (pytest+tsc gate), `release.yml` (GHCR on `v*`) | extend suites, publish v2 images |

**Consequence:** most of v2 is new *inputs* (introspection), new *outputs* (contracts/semantic/synthetic), and *scale* (async), bolted onto an existing, tested spine — not a rewrite.

---

## Part 1 — Product Requirement Document (PRD)

### 1. Thesis

ModelBox is a **deterministic NL/DDL → typed-graph → multi-dialect codegen pipeline** with zero-egress, multi-region LLM routing. v2.0 grows it from an ERD tool into a **three-pillar platform**:

- **Pillar 1 — Enterprise Designer:** async synthesis, canvas-edit persistence, live graph state.
- **Pillar 2 — Migration & Governance Mesh:** DB introspection, schema diff → `ALTER`, synthetic seed data, and data contracts (OpenDataContract/Avro/Protobuf/LookML/MetricFlow).
- **Pillar 3 — ModelBox Trainer:** the interactive teaching & learning engine for **RealityDB Academy** data-modeling courses — Socratic tutor, "Spot the Flaw" challenge mode, auto-graded rubrics.

### 2. Personas & buyers

| Persona | Goal | Key features |
| :---- | :---- | :---- |
| Principal Data Architect | Modernize legacy warehouses without breaking BI | Introspection, 3NF→Kimball, schema diff + `ALTER` |
| Governance / Platform Lead | Prevent breaking changes; enforce PII/quality | Data contracts, CI schema checks, synthetic seed |
| Professor / Corp Instructor | Teach modeling objectively with feedback | Socratic tutor, Spot-the-Flaw, auto-graded rubrics |
| Analytics Engineer / Student | Build validated dbt/Cube models | Async synthesis, canvas persistence, N:1 linter |

### 3. Functional Requirements

**Module 1 — Designer**
- **FR-1.1 Async job execution:** synthesis (60–90s) MUST run on a worker queue with status polling/WebSocket — no HTTP timeouts.
- **FR-1.2 Canvas persistence:** node positions, column add/edit/delete, and relationship cardinality edits MUST persist via a stateful graph endpoint, re-validated on save.

**Module 2 — Migration, Brownfield & Contracts**
- **FR-2.1 Introspection:** connect to PostgreSQL / Snowflake / BigQuery / DuckDB, pull `INFORMATION_SCHEMA` into a `SynthesizedModel` graph, save as a model.
- **FR-2.2 Schema diff → `ALTER`:** compare model A vs B → dialect-specific `ALTER TABLE` DDL + a `breaking_changes` list.
- **FR-2.3 Contract & semantic exporters:** OpenDataContract (YAML), Avro, Protobuf, LookML, dbt MetricFlow.
- **FR-2.4 Referential synthetic seed:** generate CSV/SQL seed honoring `topological_order()` (dimensions before facts) + column constraints; never touch production. ⟳
- **FR-2.5 (ecosystem, optional) Cross-product seams:** synthetic seed MAY delegate to **RealityDB** (`@realitydb/cli`) for compliance-graded data; generated SQL/dbt MAY be validated by **SafeSQL Pro** (safesqlpro.dev) detectors / GitHub Action. See §2.6.

**Module 3 — ModelBox Trainer** *(Teaching & Learning Engine)*
*The interactive data-modeling sandbox and tutoring engine for **RealityDB Academy** courses. ModelBox is the schema source-of-truth + canvas; RealityDB supplies the underlying data-generation engine (see §2.6).*
- **FR-3.1 Socratic tutor:** guide schema creation via interactive prompt chains (step-by-step), not one-shot generation.
- **FR-3.2 Spot-the-Flaw:** present intentionally defective schemas (cyclic FK, missing PK, fan-out risk) to diagnose/fix with linter feedback.
- **FR-3.3 Auto-graded rubrics:** submit student ERD JSON → scored rubric from **graph invariants** (reuse `GraphEngine`) + requirements coverage.

### 4. Non-functional (carried from v1)
Async NFR: job P95 enqueue < 200ms. Introspection creds encrypted at rest (AES-256-GCM, per v1 NFR-3.1) via a KMS/`hvac` provider — never plaintext. RBAC enforced on every v2 route. Air-gapped mode still strips cloud providers.

---

## Part 2 — Technical Requirement Document (TRD)

```
                          FastAPI + JWT + RBAC (OWNER/ADMIN/MEMBER)
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        ▼                                 ▼                                 ▼
  DESIGNER ENGINE                  MIGRATION ENGINE                  TRAINER ENGINE
  - async jobs (Celery)            - DB connectors                   - Socratic agent
  - graph canvas                   - schema diff → ALTER             - challenge mode
  - edit persistence               - contract/semantic/seed export   - auto-grader
        └─────────────────────────────────┼─────────────────────────────────┘
                                          ▼
   CORE SPINE:  GraphEngine (NetworkX) · LLM Gateway (LiteLLM) · ExporterService · Postgres metadata
```

### 1. v2 schema extensions — **delivered phased** (one migration per pillar)

> Implementation note: rather than one big `0005`, tables ship with the code that
> uses them: **`0005` = `synthesis_jobs`** (shipped) · **`0006` = trainer tables**
> (shipped) · `database_connections` (P2). The full target schema below is the
> reference; each phase migrates its slice.

#### Migration `0005` — schema extensions  ⟳ (rewritten to match real conventions)

> Corrections vs the v2.0 draft: UUID PKs (not `VARCHAR(36)`), real FK targets
> (`workspaces.workspace_id`, `users.user_id`, `data_models.model_id`),
> `gen_random_uuid()` defaults, and `JSONB`. ORM will use `sqlalchemy.Uuid` +
> `sqlalchemy.JSON` for SQLite-test portability (mirrors `metadata_store.py`).

```sql
-- 1. Async job tracking
CREATE TABLE synthesis_jobs (
    job_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id           UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status            VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED')),
    prompt            TEXT NOT NULL,
    paradigm          VARCHAR(32) NOT NULL
                        CHECK (paradigm IN ('3NF','KIMBALL','DATA_VAULT','OBT')),
    dialect           VARCHAR(64) NOT NULL DEFAULT 'snowflake',
    result_model_id   UUID REFERENCES data_models(model_id) ON DELETE SET NULL,
    error_message     TEXT,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_synthesis_jobs_workspace_id ON synthesis_jobs(workspace_id);

-- 2. DB introspection connections (URI encrypted at rest)
CREATE TABLE database_connections (
    connection_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id              UUID NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    name                      VARCHAR(100) NOT NULL,
    engine                    VARCHAR(30) NOT NULL
                                CHECK (engine IN ('POSTGRESQL','SNOWFLAKE','BIGQUERY','DUCKDB')),
    connection_uri_encrypted  TEXT NOT NULL,   -- AES-256-GCM ciphertext, never plaintext
    created_at                TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workspace_id, name)
);

-- 3. Trainer assignments + submissions
CREATE TABLE trainer_assignments (
    assignment_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id               UUID NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    title                      VARCHAR(150) NOT NULL,
    description                TEXT NOT NULL,
    flawed_graph_json          JSONB,           -- Spot-the-Flaw seed graph
    expected_graph_invariants  JSONB NOT NULL,  -- e.g. {"NO_CYCLIC_FK":true,"PK_PRESENT":true}
    created_at                 TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trainer_submissions (
    submission_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id        UUID NOT NULL REFERENCES trainer_assignments(assignment_id) ON DELETE CASCADE,
    student_id           UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    submitted_graph_json JSONB NOT NULL,
    score                NUMERIC(5,2),
    feedback_json        JSONB,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_trainer_submissions_assignment_id ON trainer_submissions(assignment_id);
```

### 2. API endpoints (all under `/api/v1`, RBAC-gated)

**Designer**
- `POST /jobs/synthesize` → `202 { job_id, status:"PENDING", poll_url }`. Enqueues Celery task; body `{prompt, paradigm, dialect, workspace_id?}` (workspace resolved via `resolve_user_workspace`).
- `GET /jobs/{job_id}` → `200 { status, result_model_id, error }`. 404/403 via job's workspace membership.
- `PUT /model/{model_id}/graph` → replaces the persisted graph with user edits, runs `GraphEngine.validate()`, bumps `version_number`. Requires **MEMBER+** (`require_model_role`). Reuses `SynthesisEngine._persist_graph` (extract to a `GraphRepository`). ⟳

**Migration & Governance**
- `POST /connectors` (create, ADMIN+) / `POST /connectors/introspect` `{connection_id, schema_name}` → builds a `SynthesizedModel` from `INFORMATION_SCHEMA`, saves a model.
- `POST /model/diff` `{source_model_id, target_model_id, dialect}` → `{ alter_statements[], breaking_changes[] }` (both models authorized).
- `GET /model/{model_id}/export/contract?format=opendatacontract|avro|protobuf`
- `GET /model/{model_id}/export/semantic?engine=cube|lookml|metricflow` ⟳ (folds into existing export surface)
- `POST /model/{model_id}/export/synthetic-data` `{row_count_per_entity, format:"sql_insert|csv"}`

**Trainer**
- `POST /trainer/assignments` (instructor) · `GET /trainer/assignments/{id}`
- `POST /trainer/socratic/step` `{assignment_id, conversation_history, current_graph}` → `{ next_question, hints[] }`
- `POST /trainer/grade` `{assignment_id, submitted_graph}` → `{ score, passed_invariants[], violations[] }` (violations reuse `ValidationReport` codes: `CYCLIC_FK`, `MISSING_PK`, `DANGLING_REF`).

### 3. ExporterService extensions  ⟳ (align to the real instance-based service)

The shipped `ExporterService` is **instance-based** over `SynthesizedModel` with an `export()` dispatch. v2 adds three method families using the same shape (`self`, `SynthesizedModel`), reusing `GraphEngine.topological_order`:

```python
class ExporterService:
    # ...existing generate_ddl / generate_dbt_project / generate_cube_schema / export()...

    def export_data_contract(self, model: SynthesizedModel, fmt: str) -> str:
        # opendatacontract (YAML) | avro (JSON) | protobuf
        ...

    def export_semantic_layer(self, model: SynthesizedModel, engine: str) -> str:
        # cube (exists) | lookml | metricflow
        ...

    def generate_synthetic_seed(self, model: SynthesizedModel, rows_per_fact: int = 50,
                                fmt: str = "sql_insert") -> str:
        order = GraphEngine().dependency_layers(GraphEngine().build_graph(
            model.entities, model.relationships))  # dimensions (parents) first
        # surrogate keys + Faker attrs + FK-consistent rows in topo order
        ...
```

### 4. Async architecture
- **Celery + Redis** (both already in `requirements.txt`, currently unused). `redis-cache` service is the broker/result backend (add `CELERY_BROKER_URL`/`RESULT_BACKEND` = `redis://redis-cache:6379/1`).
- New `worker` service in `docker-compose.appliance.yml` (`celery -A app.worker worker`). The task calls the existing `SynthesisEngine.synthesize`, writes `synthesis_jobs.status/result_model_id`.
- Frontend: home page fires `POST /jobs/synthesize`, then polls `GET /jobs/{id}` (WebSocket optional later); the "Synthesizing…" state we already show becomes real progress.

### 5. Security notes (carry v1 + audit)
- Connection URIs: AES-256-GCM at rest; key from env/KMS (`hvac` in deps). Decrypt only in the introspection worker.
- OIDC (audit F1): RS256 + `aud`/`iss` validation lands with SSO (Phase 3) — the `/auth/token` HS256 path stays for local/dev.

### 2.6 Ecosystem integration (RealityDB · SafeSQL) — the house thesis
The three Mpingo products form one loop — **design (ModelBox) → populate (RealityDB) → query-safely (SafeSQL)** — against the common enemy of *plausible-but-wrong*. ModelBox is the **schema source-of-truth**; its `SynthesizedModel` is the interchange the others consume.

| Seam | Direction | v2 hook |
| :---- | :---- | :---- |
| **Synthetic data** | ModelBox → RealityDB | FR-2.4 native emitter, OR emit a RealityDB manifest → SimLab live Postgres in 60s |
| **SQL/dbt correctness** | ModelBox → SafeSQL | validate generated dbt/DDL through SafeSQL's 33 detectors; surface a "passed N detectors" badge on the export panel + optional CI GitHub Action |
| **Schema connection** | shared | one Postgres introspection layer reused by ModelBox (FR-2.1), SafeSQL ("connect your DB"), RealityDB (SimLab) |
| **ModelBox Trainer** | ties all three | model on ModelBox canvas, grade design via `GraphEngine`, grade queries via SafeSQL, on RealityDB data → RealityDB Academy cert |

---

## Part 3 — Roadmap & milestones (mapped to real code)

| Phase | Days | Deliverables | New code | Tests |
| :---- | :--- | :---- | :---- | :---- |
| **P1 — Usability + Trainer foundation** | 1–30 | Async jobs (FR-1.1), canvas persistence (FR-1.2), Trainer alpha (FR-3.1/3.2) | `worker.py`, `endpoints/jobs.py`, `GraphRepository`, `endpoints/trainer.py`, migration `0005`, compose `worker` svc | job lifecycle, `PUT /graph` re-validate, grade invariants |
| **P2 — Brownfield + synthetic** | 31–60 | Introspection PG+Snowflake (FR-2.1), diff→`ALTER` (FR-2.2), synthetic seed (FR-2.4) | `services/introspection.py`, `services/diff_engine.py`, exporter `generate_synthetic_seed` | introspect→graph fidelity, diff `ALTER` correctness, FK-integrity of seed |
| **P3 — Governance + scale** | 61–90 | Contracts+semantic (FR-2.3), OIDC/SSO (F1), Trainer classroom dashboard (FR-3.3) | exporter contract/semantic methods, OIDC verify, grading dashboard | contract round-trip parse, RS256 verify, rubric scoring |

Each phase: green CI (pytest + tsc), then a tagged GHCR release (`v2.0.0-alpha.N`).

---

## Appendix A — Reconciliation deltas (draft → this doc)

| # | v2.0 draft said | Corrected to | Why |
| - | :---- | :---- | :---- |
| 1 | `id VARCHAR(36)` PKs; FK `workspaces(id)`, `users(id)`, `data_models(id)` | `UUID` PKs named `workspace_id`/`user_id`/`model_id`; FKs to those | matches shipped `metadata_store.py` + migrations `0001`–`0004` |
| 2 | `GraphEngine.topological_sort` | `GraphEngine.topological_order` / `dependency_layers` | actual method names |
| 3 | `ExporterService` static methods over `DataModelGraph` | instance methods over `SynthesizedModel` (the real graph type) | matches shipped exporter; avoids a parallel type |
| 4 | `PUT /graph` "updates stored model" | reuse/extract `SynthesisEngine._persist_graph` → `GraphRepository`; MEMBER+ RBAC | avoids duplicate persistence logic; enforces existing RBAC |
| 5 | migration numbered ambiguously | `0005` (chain from `0004`) | `0001`–`0004` already applied |
| 6 | `JSONB` only | `JSONB` on PG, `sqlalchemy.JSON` in ORM | SQLite test portability (tests run on aiosqlite) |
| 7 | contracts/synthetic built in-house only | native **or** delegate to RealityDB/SafeSQL (FR-2.5, §2.6) | leverage the sister products instead of re-solving compliance/validation |
