# **ModelBox AI: System Dependencies & Technology Stack Specification**

This document details all third-party libraries, frameworks, database connectors, AI orchestration SDKs, and container infrastructure dependencies required to build, run, and maintain **ModelBox AI**.

## **1\. Core Application Stack Summary**

| Layer | Primary Technology / Framework | Key Dependencies |
| :---- | :---- | :---- |
| **Frontend UI** | React 18+ / Next.js 14+ (TypeScript) | @xyflow/react, Monaco Editor, Tailwind CSS, Zustand |
| **Backend API** | Python 3.11+ / FastAPI | Pydantic v2, SQLGlot, NetworkX, Instructor |
| **AI Abstraction** | LiteLLM Proxy / Open Router | litellm, SDKs for OpenAI, Anthropic, Gemini, Mistral |
| **App Databases** | PostgreSQL 16+ & Redis 7+ | SQLAlchemy 2.0, Asyncpg, Redis-py |
| **Local Inference** | vLLM / Ollama Container | CUDA/ROCm runtimes, Ollama Engine |

## **2\. Detailed Dependency Breakdown**

### **2.1 Frontend UI & Visual Canvas (package.json)**

{  
  "name": "modelbox-ui",  
  "version": "1.2.0",  
  "dependencies": {  
    "next": "^14.2.0",  
    "react": "^18.3.0",  
    "react-dom": "^18.3.0",  
    "@xyflow/react": "^12.0.0",   
    "dagre": "^0.8.5",  
    "@monaco-editor/react": "^4.6.0",  
    "zustand": "^4.5.0",  
    "@tanstack/react-query": "^5.28.0",  
    "tailwindcss": "^3.4.0",  
    "@radix-ui/react-dialog": "^1.0.5",  
    "@radix-ui/react-dropdown-menu": "^2.0.6",  
    "@radix-ui/react-tabs": "^1.0.4",  
    "@radix-ui/react-tooltip": "^1.0.7",  
    "lucide-react": "^0.350.0",  
    "clsx": "^2.1.0",  
    "tailwind-merge": "^2.2.0",  
    "axios": "^1.6.8"  
  },  
  "devDependencies": {  
    "typescript": "^5.4.0",  
    "@types/react": "^18.2.0",  
    "@types/dagre": "^0.7.52",  
    "eslint": "^8.57.0",  
    "prettier": "^3.2.5"  
  }  
}

* **Purpose Breakdown:**  
  * @xyflow/react (React Flow): Interactive drag-and-drop node graph canvas for visual entity relationship design.  
  * dagre: Automated layout positioning algorithms for complex ERDs.  
  * @monaco-editor/react: Embedded VS Code editor interface for SQL DDL, dbt models, and Cube.js schemas.  
  * zustand: Lightweight state manager for maintaining canvas entity graphs and undo/redo stacks.

### **2.2 Backend Engine & Modeling Service (requirements.txt)**

\# Web & API Framework  
fastapi\>=0.110.0  
uvicorn\[standard\]\>=0.28.0  
pydantic\>=2.6.0  
pydantic-settings\>=2.2.0

\# Graph Processing & AST Parsing  
sqlglot\>=23.0.0  
networkx\>=3.2.1  
sqlfluff\>=3.0.0

\# AI & LLM Orchestration  
litellm\>=1.35.0  
instructor\>=1.2.0  
openai\>=1.14.0  
anthropic\>=0.19.0  
google-genai\>=0.1.0  
mistralai\>=0.1.0

\# Task Queue & Async Workers  
celery\>=5.3.6  
redis\>=5.0.3  
rq\>=1.16.0

\# Database Access & Drivers  
sqlalchemy\[asyncio\]\>=2.0.28  
asyncpg\>=0.29.0  
psycopg2-binary\>=2.9.9  
duckdb\>=0.10.0

\# Reverse Engineering Data Warehouse Connectors  
snowflake-connector-python\>=3.7.1  
databricks-sql-connector\>=3.1.0  
google-cloud-bigquery\>=3.19.0  
pymysql\>=1.1.0

\# Code & Schema Generation  
jinja2\>=3.1.3  
pyyaml\>=6.0.1

\# Security & Utils  
python-jose\[cryptography\]\>=3.3.0  
passlib\[bcrypt\]\>=1.7.4  
httpx\>=0.27.0

* **Purpose Breakdown:**  
  * sqlglot: Transpiles DDL syntax across 20+ SQL dialects (Snowflake, BigQuery, Postgres, Redshift, ClickHouse, Databricks).  
  * networkx: Directed graph engine for lineage calculation, cyclic dependency detection, and table depth ordering.  
  * instructor: Guarantees structured JSON output validation from LLMs using Pydantic schemas.  
  * sqlfluff: Automated SQL linting and auto-formatting before model output rendering.

### **2.3 LLM Gateways & Local Inference Dependencies**

#### **Cloud LLM Providers**

* **OpenAI API:** GPT-4o, o1, GPT-4o-mini  
* **Anthropic API:** Claude 3.5 Sonnet, Claude 3 Opus  
* **Google Gemini API:** Gemini 1.5 Pro, Gemini 1.5 Flash  
* **Mistral AI API:** Codestral, Mistral Large 2 (Sovereign EU Endpoints)

#### **Air-Gapped / On-Premise Inference Engine Container Dependencies**

* **vLLM Engine:** vllm\>=0.4.0 (Requires NVIDIA CUDA 12.1+ or AMD ROCm 6.0+)  
* **Ollama Runtime:** ollama/ollama:latest container (Supports Llama 3.3, DeepSeek-R1-Distill, Qwen 2.5 Coder)  
* **LiteLLM Gateway:** ghcr.io/berriai/litellm:main-v1.45.0 (Unified proxy and model routing server)

### **2.4 Appliance Infrastructure Dependencies (Docker & System Level)**

To run the full **ModelBox AI "Box"** single-node or clustered deployment:

| Category | Requirement / Dependency | Minimum Version | Recommended Enterprise Spec |
| :---- | :---- | :---- | :---- |
| **Host OS** | Ubuntu LTS / RHEL / Amazon Linux 2023 | 22.04 LTS | RHEL 9.x / Rocky Linux 9 |
| **Container Engine** | Docker Engine & Docker Compose | Docker v24.0+, Compose v2.20+ | Docker v26.0+ |
| **App Database** | PostgreSQL Server | v16.0 | PostgreSQL 16 managed (RDS/Cloud SQL) |
| **Cache & Queue Broker** | Redis Server | v7.0 | Redis Enterprise / AWS ElastiCache |
| **GPU Acceleration** *(Optional for Air-Gap)* | NVIDIA Container Toolkit (nvidia-docker2) | CUDA 12.1+ | 1x NVIDIA A10G / L40S or A100 |
| **Memory & Compute** | Minimum Specs | 4 vCPU, 16 GB RAM | 16 vCPU, 64 GB RAM (Non-GPU) |

### **2.5 Development, Security & QA Dependencies**

* **Code Quality & Testing:** pytest, pytest-asyncio, black, ruff, mypy.  
* **Authentication & Authorization:** OAuth2 with PKCE, OpenID Connect (OIDC) integration (Okta, Keycloak, Azure AD via python-jose).  
* **Vault & Secrets Management:** HashiCorp Vault SDK (hvac) or AWS Secrets Manager for encrypted API key storage.