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
docker compose -f docker/docker-compose.appliance.yml up --build
```

- Web UI → http://localhost:3000
- API docs → http://localhost:8000/docs
- Health → http://localhost:8000/health

Enable the optional local inference engine (offline / air-gapped):

```bash
docker compose -f docker/docker-compose.appliance.yml --profile airgap up --build
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

## Governance & air-gap

Set `AIRGAPPED=true` to enforce **zero data egress** (FR-6.2): the LLM gateway
strips every cloud provider from each task's routing chain and pins execution to
local runtimes (Ollama / vLLM). Routing is keyed off the explicit `egress:`
classification in `config/model_router.yaml`, so the policy is deterministic.

## Releases (container images)

Tagging a commit with a semver tag publishes versioned images to GHCR via the
`Release Images` workflow (`.github/workflows/release.yml`). Cut tags from a
green `main` — CI gates every push.

```bash
git tag v1.2.0
git push origin v1.2.0
```

Produces (per tag): `ghcr.io/emkwambe/modelbox-backend:{1.2.0,1.2,latest}` and
`ghcr.io/emkwambe/modelbox-frontend:{1.2.0,1.2,latest}`.

## License

Proprietary — ModelBox AI. All rights reserved.
