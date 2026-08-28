# ModelBox AI

An enterprise-grade, **LLM-agnostic** business data modeling workspace. ModelBox AI
turns raw business requirements (PRDs, Jira stories, natural language) into
production-ready data warehouse architecture (Snowflake, Databricks, BigQuery,
Postgres) — with a visual ERD canvas, multi-paradigm transformation, and
zero-data-egress options for regulated industries.

> Shipped as a single-node Docker appliance ("The Box").

---

## Architecture

| Layer | Stack |
| :---- | :---- |
| **Frontend** | Next.js 14 (App Router), React 18, TypeScript, `@xyflow/react`, Zustand, Monaco, Tailwind |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, SQLGlot, NetworkX, Instructor, LiteLLM |
| **Verified against** | `dbt parse`, `protoc`, `fastavro`, `sqlfluff`, DuckDB execution — see `backend/tests/test_artifact_fidelity.py` |
| **Data** | PostgreSQL 16 (SQLAlchemy 2.0 async + asyncpg), Redis 7 |
| **LLM** | OpenAI · Anthropic · Gemini · Mistral (EU) · Ollama · vLLM — via a LiteLLM routing gateway |

```
Next.js UI  ──REST──►  FastAPI Engine  ──►  PostgreSQL 16 / Redis 7
                            │
                            └──►  LiteLLM Gateway ──►  Cloud APIs | Local (Ollama/vLLM)
```

## Project layout

```
modelbox-ai/
├── backend/          FastAPI engine (app/), Alembic migrations, requirements.txt
│   └── app/
│       ├── core/     config + async database
│       ├── models/   SQLAlchemy metadata-store ORM
│       ├── schemas/  Pydantic v2 API + LLM schemas
│       ├── services/ graph_engine, llm_gateway, synthesis_engine, paradigm_translator
│       └── api/v1/   routers + endpoints
├── frontend/         Next.js app (src/app, src/components, src/store, src/types)
├── config/           model_router.yaml (task→provider routing)
└── docker/           Dockerfiles + docker-compose.appliance.yml
```

## Quick start (Docker appliance)

```bash
cp .env.example .env          # then fill in provider API keys
docker compose --env-file .env -f docker/docker-compose.appliance.yml up --build
```

`.env` belongs here, beside this README, and **`--env-file .env` is not
optional.** Two different mechanisms read that file and only one of them finds
it on its own:

- **Provider credentials** reach the containers through `env_file:` entries in
  the compose file, whose paths resolve relative to the compose file itself. These
  work from any directory, with or without the flag.
- **Everything written as `${VAR}` in the compose file** — `UI_PORT`,
  `POSTGRES_PASSWORD`, `ENCRYPTION_KEY`, `AIRGAPPED` — is substituted by Compose
  *before* any service is created, and that substitution reads Compose's project
  directory, which is `docker/`. Without the flag those silently fall back to
  their defaults: the UI binds port 3000 rather than your `UI_PORT`, and the
  database comes up with the default password.

If synthesis fails with *"All providers exhausted"*, check that the file exists
and that the keys in it are current — a retired model identifier surfaces as a
404 and reads like a bad credential. If the UI fails to start with *"ports are
not available"*, the `--env-file` flag is missing and `UI_PORT` never applied.

- Web UI → http://localhost:3000
- API docs → http://localhost:8000/docs
- Health → http://localhost:8000/health

Enable the optional local inference engine (offline / air-gapped):

```bash
docker compose --env-file .env -f docker/docker-compose.appliance.yml --profile airgap up --build
```

## Local development

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic revision --autogenerate -m "initial schema"   # first run only
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

## Key API endpoints

| Method | Path | Description |
| :----- | :--- | :---------- |
| `POST` | `/api/v1/model/synthesize` | Synthesize a data model from natural language / documents |
| `GET`  | `/api/v1/model/{model_id}` | Retrieve a persisted model |
| `POST` | `/api/v1/model/{model_id}/transform-paradigm` | Transform between 3NF / Kimball / Data Vault 2.0 / OBT |
| `GET`  | `/health` | Liveness / readiness probe |

## LLM providers & regional routing

`config/model_router.yaml` spans all major regions: **US** (OpenAI, Anthropic,
Gemini), **EU-sovereign** (Mistral), **APAC** (DeepSeek, Kimi/Moonshot — cloud;
Qwen & DeepSeek open-weights locally), and **local/air-gapped** (Ollama, vLLM).
New providers are pure config — any OpenAI-compatible endpoint uses
`type: openai_compatible` with a `base_url` + `api_key_env` (no code changes).

> **Data-residency note:** the APAC *cloud* providers (DeepSeek, Kimi) are wired
> as **opt-in fallbacks**, never primaries for sensitive tasks. Sending schema
> metadata to any third-party cloud has residency/compliance implications —
> for zero-egress guarantees use `AIRGAPPED=true` with local open-weights.

## SQL dialects

**Certified** — verified on every push by two independent dialect grammars, and
for DuckDB by executing the emitted DDL against the engine itself:
`postgres`, `snowflake`, `redshift`, `duckdb`.

**Preview — not deployment-verified:** `bigquery`, `databricks`, `clickhouse`.
These transpile and re-parse, but the emitted DDL is not accepted by those
engines as written: BigQuery requires `NOT ENFORCED` on key constraints,
Databricks requires `NOT NULL` on primary keys, ClickHouse requires an `ENGINE`
clause and forbids `Nullable` in a key. LookML is Preview for a different
reason — no offline parser exists, so we cannot verify it at all.

The distinction is shown **in the export picker, before you generate**, not in
a note afterwards: certified and preview dialects are grouped separately and
choosing a preview dialect raises a standing warning. Promotion out of Preview
is gated on the fidelity harness proving deployability, not on a decision.

## Governance & air-gap

Prompt masking (`MASK_METADATA_IN_PROMPTS`) was **retired in v1.6.0**. It was
documented but never implemented, and is not being built: obfuscating column
names while the same request carries the source requirements document verbatim
leaks the same semantics. Setting the flag now fails startup. Use air-gapped
mode, which is a real control.

Set `AIRGAPPED=true` to enforce **zero data egress** (FR-6.2): the LLM gateway
strips every cloud provider from each task's routing chain and pins execution to
local runtimes (Ollama / vLLM). Routing is keyed off the explicit `egress:`
classification in `config/model_router.yaml` (any non-`local` egress — including
`cloud_apac` — is stripped in air-gapped mode), so the policy is deterministic.

## Releases (container images)

Tagging a commit with a semver tag publishes versioned images to GHCR via the
`Release Images` workflow (`.github/workflows/release.yml`). Cut tags from a
green `main`.

CI (`.github/workflows/ci.yml`) runs on every branch and pull request, and six
checks are required before merging to `main`: backend `pytest`, the artifact
fidelity harness, `tsc --noEmit`, `next build`, `next lint`, and an Alembic
single-head check — plus a version-consistency gate.

```bash
git tag v1.2.0
git push origin v1.2.0
```

Produces (per tag): `ghcr.io/emkwambe/modelbox-backend:{1.2.0,1.2,latest}` and
`ghcr.io/emkwambe/modelbox-frontend:{1.2.0,1.2,latest}`.

## License

Proprietary — ModelBox AI. All rights reserved.
