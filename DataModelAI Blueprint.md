# **ModelBox AI: Architectural Blueprint & Technical Specification**

**An LLM-Agnostic, AI-Powered Enterprise Business Data Modeling Platform**

## **1\. Executive Summary & Vision**

**ModelBox AI** is an enterprise-grade, containerized ("Box") data modeling workspace that uses generative AI and graph reasoning to automate, standardize, and accelerate enterprise data architecture.

### **Core Differentiators**

1. **100% LLM-Agnostic:** Plug-and-play adapter layer allowing seamless switching between commercial APIs (OpenAI, Anthropic Claude, Google Gemini) and local/air-gapped models (Ollama, vLLM, DeepSeek, Llama 3\) via a unified gateway.  
2. **Multi-Paradigm Engine:** Automatic translation between 3rd Normal Form (3NF), Dimensional Models (Kimball Star/Snowflake), Data Vault 2.0, and One Big Table (OBT).  
3. **NL-to-Schema & Unstructured Ingestion:** Ingests PRDs, Jira tickets, legacy DDLs, and business requirements to synthesize conceptual, logical, and physical data models.  
4. **Active Governance & Semantic Layer:** Automated PII tagging, business glossary mapping, and semantic layer export (dbt, Cube.js, LookML).  
5. **Air-Gap Ready:** Can run completely offline in high-security, privacy-restricted environments (defense, healthcare, finance).

## 

## 

## 

## 

## 

## 

## 

## 

## **2\. High-Level System Architecture**

                                 \+-------------------------------------------------+  
                                 |                User Interface                   |  
                                 |  Visual Canvas (React Flow) | Prompt Studio      |  
                                 |  Lineage Viewer            | Governance Center  |  
                                 \+------------------------+------------------------+  
                                                          |  
                                                          v  
                                 \+-------------------------------------------------+  
                                 |               API Gateway / REST / WS           |  
                                 \+------------------------+------------------------+  
                                                          |  
                                        \+-----------------+-----------------+  
                                        |                                   |  
                                        v                                   v  
\+-----------------------------------------------+   \+-----------------------------------------------+  
|             Data Modeling Engine              |   |          Agnostic LLM Orchestrator           |  
|  \- Graph Parser & Canvas State Engine         |   |  \- Task-Based Dynamic Router                  |  
|  \- Schema Synthesizer (3NF, Kimball, DV2.0)   |   |  \- Fallback & Rate Limit Manager              |  
|  \- Reverse-Engineering Pipeline (SQL DBs)     |   |  \- Context Compressor & Prompt Templates      |  
|  \- Artifact Exporters (dbt, SQL, LookML, etc.)|   |  \- Token Cost & Audit Logging                 |  
\+-----------------------+-----------------------+   \+-----------------------+-----------------------+  
                        |                                                   |  
                        \+-------------------------+-------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                 LLM Provider Abstraction Layer                                    |  
|                                                                                                   |  
|  \[ Cloud Providers \]                      \[ On-Premise / Air-Gapped Providers \]                  |  
|  \- OpenAI (GPT-4o, o1)                    \- Ollama (Llama 3.3, Qwen 2.5)                          |  
|  \- Anthropic (Claude 3.5 Sonnet)          \- vLLM / LocalAI (DeepSeek-R1, Mistral)                |  
|  \- Google Gemini 1.5 Pro                  \- Custom vLLM / HuggingFace Endpoints                  |  
|  \- AWS Bedrock / Azure OpenAI             \- Enterprise LiteLLM Gateway                            |  
\+---------------------------------------------------------------------------------------------------+

## **3\. LLM-Agnostic Provider Framework**

The core engine relies on a unified adapter abstraction powered by **LiteLLM / Custom Proxy**, allowing administrators to assign specific LLM providers to specific data modeling tasks based on cost, context window, and reasoning capability.

### **3.1 Task-Based Model Router Configuration (model\_router.yaml)**

version: "1.0"  
settings:  
  default\_fallback\_enabled: true  
  cost\_optimization\_mode: "balanced" \# performance | balanced | cost\_optimized | air\_gapped

providers:  
  anthropic\_cloud:  
    type: "anthropic"  
    api\_key\_env: "ANTHROPIC\_API\_KEY"  
    default\_model: "claude-3-5-sonnet-20241022"  
    
  openai\_cloud:  
    type: "openai"  
    api\_key\_env: "OPENAI\_API\_KEY"  
    default\_model: "gpt-4o"

  local\_ollama:  
    type: "ollama"  
    base\_url: "http://ollama-service:11434"  
    default\_model: "qwen2.5-coder:32b"

  airgapped\_vllm:  
    type: "openai\_compatible"  
    base\_url: "http://vllm-server.internal:8000/v1"  
    api\_key\_env: "INTERNAL\_VLLM\_KEY"  
    default\_model: "deepseek-ai/DeepSeek-R1-Distill-Llama-70B"

task\_routing:  
  \# Unstructured PRD/BRD parsing \-\> High reasoning context model  
  unstructured\_doc\_parsing:  
    primary: "anthropic\_cloud"  
    fallback: \["openai\_cloud", "airgapped\_vllm"\]  
    temperature: 0.1

  \# Schema Normalization & Constraint Checking \-\> Reasoning heavy model  
  schema\_reasoning\_and\_erd:  
    primary: "airgapped\_vllm" \# or "anthropic\_cloud"  
    fallback: \["openai\_cloud"\]  
    temperature: 0.0

  \# High-volume SQL DDL generation & syntax translation \-\> Fast code model  
  ddl\_code\_generation:  
    primary: "local\_ollama"  
    fallback: \["openai\_cloud"\]  
    temperature: 0.0

  \# Business description & dictionary generation \-\> Cost-effective LLM  
  data\_dictionary\_enrichment:  
    primary: "local\_ollama"  
    fallback: \["openai\_cloud"\]  
    temperature: 0.3

## **4\. Core Data Modeling Capabilities**

### **4.1 Automated Paradigm Translation Engine**

ModelBox AI allows engineers and business analysts to toggle between four data architecture paradigms in real-time.

| Paradigm | Target Use Case | AI Synthesis Strategy |
| :---- | :---- | :---- |
| **3rd Normal Form (3NF)** | Operational Data Stores (ODS), OLTP | Normalizes entities up to 3NF/BCNF. Eliminates redundancies, derives foreign key relationships. |
| **Dimensional (Kimball)** | Enterprise Data Warehouse, BI reporting | Identifies Business Processes ![][image1] Declares Grain ![][image1] Separates Facts (additive/semi-additive metrics) and Dimensions (SCD Type 1/2/3). |
| **Data Vault 2.0** | Scalable Data Lakes, Agile DW | Extracts core business concepts into **Hubs**, relationships into **Links**, and context/attributes into **Satellites**. |
| **One Big Table (OBT)** | Modern Analytics Engine (Snowflake, ClickHouse) | Denormalizes dimension and fact tables into flattened, columnar-optimized structures with nested JSON support. |

### **4.2 Workflow: From Natural Language to Deployable dbt Project**

\+--------------------------+  
|  Business Doc / PRD / NL | "We need to track customer orders, subscription renewals,   
\+------------+-------------+  churn risk, and monthly recurring revenue (MRR)."  
             |  
             v  
\+--------------------------+  
| Entity & Concept Extractor| Extracts: Customer, Order, Subscription, Invoice, ChurnEvent  
\+------------+-------------+  
             |  
             v  
\+--------------------------+  
| Logical Schema Synthesis | Generates Conceptual graph with Cardinality (1:N, N:M)  
\+------------+-------------+  
             |  
             v  
\+--------------------------+  
| Physical Model Refinement| Adds Primary Keys, Foreign Keys, Indexes, Partitioning Keys  
\+------------+-------------+  
             |  
             v  
\+--------------------------+  
| Artifact Generation      | Exports SQL DDLs, dbt models, Cube.js schemas, Data Catalog  
\+--------------------------+

## **5\. System Components & Engine Design**

### **5.1 Interactive Canvas Engine (Frontend)**

* **Visual Graph Interface:** Built on React Flow with interactive node connectors, entity card layout, column-level mapping, and real-time validation warnings (e.g., missing primary key, cyclic dependencies).  
* **AI Copilot Sidebar:** Context-aware assistant that listens to canvas state changes and offers recommendations (e.g., *"Table orders has 42 columns. Would you like to split this into 3 dimensional tables?"*).  
* **Diff & Merge Viewer:** Visually compares AI-suggested schema updates against current production databases using Git-like visual diffing.

### **5.2 Reverse Engineering Engine**

* **Metadata Extractors:** Connectors for PostgreSQL, MySQL, Snowflake, Databricks Unity Catalog, BigQuery, and DuckDB.  
* **Schema Refactoring Agent:** Analyzes raw tables, automatically infers missing foreign key constraints via data distribution analysis, detects JSON payload structures, and suggests clean dimensional models.

### **5.3 Automated Governance & Security Engine**

* **PII & Sensitivity Tagging:** Automatic detection of sensitive fields (SSN, Email, Credit Cards) using regex \+ LLM semantics.  
* **Business Glossary Linker:** Maps column names like usr\_lgn\_dt to standardized enterprise definitions (User Last Login Timestamp).

## **6\. API Specification (Core Endpoints)**

### **POST /api/v1/model/synthesize**

Generates a data model from raw natural language or unstructured text.

#### **Request Payload**

{  
  "source\_type": "natural\_language",  
  "content": "Build an e-commerce data model tracking Users, Product Catalogs, Shopping Carts, Orders, and Payment Transactions. We need to measure Customer Lifetime Value (CLV) and Monthly Active Users.",  
  "target\_paradigm": "DIMENSIONAL",  
  "dialect": "snowflake",  
  "llm\_override": "anthropic\_cloud"  
}

#### **Response Payload**

{  
  "model\_id": "mod\_89f2a41d",  
  "paradigm": "DIMENSIONAL",  
  "entities": \[  
    {  
      "id": "dim\_customer",  
      "type": "DIMENSION",  
      "columns": \[  
        {"name": "customer\_hk", "type": "VARCHAR(64)", "is\_pk": true, "description": "Surrogate Hash Key for Customer"},  
        {"name": "customer\_id", "type": "VARCHAR(32)", "is\_pk": false, "description": "Natural Business Key"},  
        {"name": "email", "type": "VARCHAR(255)", "is\_pii": true, "pii\_type": "EMAIL"},  
        {"name": "created\_at", "type": "TIMESTAMP\_NTZ", "is\_pk": false}  
      \]  
    },  
    {  
      "id": "fact\_orders",  
      "type": "FACT",  
      "grain": "One record per order line item",  
      "columns": \[  
        {"name": "order\_id", "type": "VARCHAR(32)", "is\_pk": true},  
        {"name": "customer\_hk", "type": "VARCHAR(64)", "is\_fk": true, "references": "dim\_customer.customer\_hk"},  
        {"name": "total\_amount", "type": "NUMBER(18,2)", "is\_metric": true, "aggregation": "SUM"}  
      \]  
    }  
  \],  
  "relationships": \[  
    {  
      "from": "fact\_orders.customer\_hk",  
      "to": "dim\_customer.customer\_hk",  
      "cardinality": "N:1"  
    }  
  \],  
  "suggested\_metrics": \[  
    {  
      "name": "Customer Lifetime Value (CLV)",  
      "formula": "SUM(fact\_orders.total\_amount)",  
      "group\_by": "dim\_customer.customer\_id"  
    }  
  \]  
}

## **7\. Artifact Export Code Generation Example**

### **7.1 Generated dbt Model (marts/core/fact\_orders.sql)**

{{ config(  
    materialized='incremental',  
    unique\_key='order\_id',  
    cluster\_by=\['order\_date'\]  
) }}

with raw\_orders as (  
    select \* from {{ ref('stg\_orders') }}  
),

dim\_customers as (  
    select customer\_hk, customer\_id from {{ ref('dim\_customers') }}  
)

select  
    md5(cast(coalesce(cast(r.order\_id as text), '\_dbt\_utils\_surrogate\_key\_null\_') as text)) as order\_hk,  
    r.order\_id,  
    c.customer\_hk,  
    r.order\_date,  
    r.total\_amount,  
    current\_timestamp() as dbt\_updated\_at  
from raw\_orders r  
left join dim\_customers c on r.customer\_id \= c.customer\_id

{% if is\_incremental() %}  
  where r.order\_date \>= (select max(order\_date) from {{ this }})  
{% endif %}

### **7.2 Generated Cube.js Semantic Schema (schema/Orders.js)**

cube(\`Orders\`, {  
  sql: \`SELECT \* FROM ${fact\_orders.sql()}\`,  
    
  joins: {  
    Customers: {  
      sql: \`${CUBE}.customer\_hk \= ${Customers}.customer\_hk\`,  
      relationship: \`belongsTo\`  
    }  
  },  
    
  measures: {  
    count: {  
      type: \`count\`,  
      drillMembers: \[orderId, orderDate\]  
    },  
      
    totalRevenue: {  
      sql: \`total\_amount\`,  
      type: \`sum\`,  
      format: \`currency\`  
    }  
  },  
    
  dimensions: {  
    orderId: {  
      sql: \`order\_id\`,  
      type: \`string\`,  
      primaryKey: true  
    },  
      
    orderDate: {  
      sql: \`order\_date\`,  
      type: \`time\`  
    }  
  }  
});

## **8\. Deployment Architecture ("The Box")**

The platform is designed to be shipped as a single-node or clustered dockerized appliance for fast deployment inside private clouds (AWS VPC, Azure VNet, GCP Custom Network) or bare-metal enterprise servers.

\# docker-compose.appliance.yml  
version: '3.8'

services:  
  modelbox-ui:  
    image: modelbox/web-ui:v1.2.0  
    ports:  
      \- "3000:3000"  
    environment:  
      \- NEXT\_PUBLIC\_API\_URL=http://localhost:8000  
    depends\_on:  
      \- modelbox-backend

  modelbox-backend:  
    image: modelbox/core-engine:v1.2.0  
    ports:  
      \- "8000:8000"  
    environment:  
      \- DATABASE\_URL=postgresql://modelbox:secret@postgres-db:5432/modelbox\_metadata  
      \- REDIS\_URL=redis://redis-cache:6379  
      \- LLM\_GATEWAY\_URL=http://litellm-proxy:4000  
    depends\_on:  
      \- postgres-db  
      \- redis-cache  
      \- litellm-proxy

  litellm-proxy:  
    image: ghcr.io/berriai/litellm:main-v1.45.0  
    ports:  
      \- "4000:4000"  
    volumes:  
      \- ./config/model\_router.yaml:/app/config.yaml  
    command: \["--config", "/app/config.yaml"\]

  \# Optional local inference engine for offline/air-gapped setups  
  ollama-engine:  
    image: ollama/ollama:latest  
    ports:  
      \- "11434:11434"  
    volumes:  
      \- ollama\_storage:/root/.ollama

  postgres-db:  
    image: postgres:16-alpine  
    environment:  
      POSTGRES\_USER: modelbox  
      POSTGRES\_PASSWORD: secret  
      POSTGRES\_DB: modelbox\_metadata  
    volumes:  
      \- pgdata:/var/lib/postgresql/data

  redis-cache:  
    image: redis:7-alpine

volumes:  
  pgdata:  
  ollama\_storage:

## **9\. Security, Governance & Compliance Controls**

1. **Zero Data Egress Mode:** Enable AIRGAPPED=true in environment variables. Blocks all external network calls and routes all AI requests to local vLLM / Ollama backends.  
2. **RBAC & Schema Masking:** Role-based access controls to obscure column names or sensitive PII tags before sending prompts to external LLMs.  
3. **Deterministic Seed Prompts:** Fixed parameters (![][image2]) and rigid output JSON Schemas (via Instructor / TypeChat) ensure 100% predictable DDL generation without syntax errors.  
4. **Audit Trail:** Every AI-generated schema change records the exact model ID, prompt hash, user ID, and timestamp in an append-only audit database.

## **10\. Roadmap & Implementation Phasing**

* **Phase 1 (MVP):** Visual Canvas \+ NL-to-Schema Engine \+ OpenAI/Claude/Ollama connectors \+ SQL DDL export.  
* **Phase 2 (Paradigm Shift):** Multi-Paradigm Switcher (3NF ![][image3] Kimball ![][image3] Data Vault 2.0) \+ Reverse engineering of existing live databases.  
* **Phase 3 (Semantic & Lineage):** Full semantic layer generation (dbt, Cube.js, LookML) \+ Column-level data lineage graph.  
* **Phase 4 (Enterprise Autopilot):** Autonomous data modeling agents that monitor warehouse query logs and automatically suggest index optimizations and denormalizations.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAWCAYAAADNX8xBAAAAsklEQVR4XmNgGAWjgHigoKDAIScnlyYqKsqDLkcqYJSXl28FGmaMLkEyABkCNKwXyGRBlyMVMAK9WAA0MA7EhosCBQWANkiSgpWUlIDmyM0HsierqKjwMYiLi3MDOdVAPItUDDRoB5D+CsTNcFeRCmRlZU2ABqyWlpaWQZcjGgA1CwMNWayoqCiPLkcSABqSBQzXCHRxkgAoQQINmiojIyONLkcqYFRXV+cF0egSowA/AAAM0CdxkhJuEQAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,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>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAYCAYAAAAVibZIAAAA6klEQVR4Xu2SuwrCQBREE1Cw8FFICkmym4RAWiE2fomCYGlh5TfY2CpiZWFhKf6jM2oRh8Q02uXAssudc3c3D8dpaPgvnud1jTGrKIo6mhHWmdPTrBJr7RRNO60XgbOFk2u9lDzP27jJoa6BB9PDsqWZ4kJeQ95wraHg0sPhS641fJKmaR8bHjmSJDGYR3WDHriwh/265xOcHEG4YxprVkYYhhP4N9/3A80+iOMYnj3jFgPNimCjIbwrfc1KgbzAbWdaL2Jf736u9Ur4OGjYOxVflv8pNj0FQeBr9g03y7IeZw3e1OUNDb/mAfRMJY7qfvryAAAAAElFTkSuQmCC>