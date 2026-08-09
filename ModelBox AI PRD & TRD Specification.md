# **ModelBox AI: Product & Technical Requirements Document (PRD / TRD)**

**Document Version:** 1.0.0

**Status:** Approved for Engineering

**Target Release:** v1.2 Enterprise Appliance

**Author:** Lead Data Architect & Product Engineering

## **SECTION 1: Product Requirements Document (PRD)**

### **1.1 Executive Product Vision**

**ModelBox AI** is an enterprise-grade, LLM-agnostic business data modeling workspace. It bridges the gap between raw business requirements (PRDs, Jira stories, natural language) and production-ready data warehouse architecture (Snowflake, Databricks, BigQuery, Postgres).

The platform accelerates data modeling velocity by up to 80% while enforcing strict governance, multi-paradigm design standards (3NF, Kimball, Data Vault 2.0, OBT), and zero-data-egress privacy options for regulated industries.

### **1.2 Target Personas & Primary Pain Points**

| Persona | Primary Goal | Current Pain Points | ModelBox AI Solution |
| :---- | :---- | :---- | :---- |
| **Data Architect** | Enforce enterprise data standards across teams. | Manual schema design in static tools (Visio/Lucidchart) that go out of sync with code. | Dynamic visual canvas synchronized with LLM schema synthesis & git-like diffing. |
| **Analytics Engineer** | Speed up dbt/SQL modeling pipelines. | Writing tedious boilerplate SQL DDL, staging models, and surrogate key logic by hand. | Automated multi-dialect SQL and dbt model code generation in seconds. |
| **CISO / Compliance Lead** | Ensure zero PII leakage & data sovereignty. | Public AI APIs risk sending enterprise metadata or sensitive schemas to external servers. | Local LLM fallback (vLLM/Ollama) and EU-compliant sovereign model routing (Mistral). |
| **BI Lead / Analyst** | Define consistent business metrics. | Fragmented semantic definitions across disparate BI tools (Looker, Tableau, PowerBI). | Unified export to Cube.js, MetricFlow, and LookML semantic layers. |

### **1.3 Functional Requirements (FR)**

#### **FR-1: Natural Language & Unstructured Document Ingestion**

* **FR-1.1:** The system MUST accept unformatted text, PRDs, PDF specifications, and user stories as input.  
* **FR-1.2:** The system MUST extract domain entities, attributes, primary keys, foreign key relationships, and cardinality (![][image1]).  
* **FR-1.3:** The system MUST display an interactive confidence score for inferred relationships.

#### **FR-2: Visual Graph Canvas & Interactive Editing**

* **FR-2.1:** The visual canvas MUST render entity-relationship diagrams (ERDs) using interactive node graphs.  
* **FR-2.2:** Users MUST be able to manually drag nodes, edit column names, modify data types, and draw explicit foreign key connectors.  
* **FR-2.3:** The canvas MUST feature real-time syntax and topological linting (e.g., detecting circular foreign key references or missing primary keys).

#### **FR-3: Automated Multi-Paradigm Switcher**

* **FR-3.1:** The system MUST allow one-click transformation between four core architectural paradigms:  
  1. **3rd Normal Form (3NF):** Fully normalized operational layout.  
  2. **Kimball Dimensional:** Facts, Dimensions (SCD Type 1/2/3), and grain definitions.  
  3. **Data Vault 2.0:** Automatic separation into Hubs, Links, and Satellites.  
  4. **One Big Table (OBT):** Flattened, columnar-optimized analytical views.  
* **FR-3.2:** The transformation engine MUST preserve underlying column descriptions and business semantic tags across paradigm switches.

#### **FR-4: Code Generation & Artifact Export**

* **FR-4.1:** Synthesized models MUST export directly to dialect-specific DDL (Snowflake, Databricks, BigQuery, PostgreSQL, DuckDB).  
* **FR-4.2:** The system MUST generate modular dbt (data build tool) project files including SQL transformation models, schema test .yml files, and surrogate key logic.  
* **FR-4.3:** The system MUST export semantic layer specifications for Cube.js and MetricFlow/LookML.

#### **FR-5: LLM Agnosticism & Routing Engine**

* **FR-5.1:** System admins MUST be able to dynamically bind specific tasks (parsing, DDL syntax, enrichment) to chosen cloud or local LLM providers.  
* **FR-5.2:** The platform MUST support OpenAI, Anthropic, Google Gemini, Mistral AI (EU sovereign endpoints), and local runtimes (vLLM / Ollama).  
* **FR-5.3:** System MUST feature automatic failover routing when primary model providers encounter rate limits or outages.

#### **FR-6: Active Governance & Security Controls**

* **FR-6.1:** System MUST automatically run PII/PHI semantic scanners on column names to assign privacy classification flags (e.g., PII\_EMAIL, PII\_SSN).  
* **FR-6.2:** System MUST support an explicit **Air-Gapped / Zero-Egress Mode** (AIRGAPPED=true), restricting all LLM communications to on-premise local containers.

### **1.4 Non-Functional Requirements (NFR)**

#### **NFR-1: Performance & Latency**

* **NFR-1.1:** Visual canvas node rendering MUST remain smooth (![][image2]) for schemas up to 250 entities.  
* **NFR-1.2:** End-to-end schema synthesis from a text prompt MUST return an initial graph within ![][image3] on standard cloud APIs and ![][image4] on local GPU nodes.

#### **NFR-2: Reliability & Availability**

* **NFR-2.1:** Backend API services MUST maintain ![][image5] uptime in single-node container deployment.  
* **NFR-2.2:** Schema parsing jobs MUST execute with exponential backoff retries (![][image6]) for transient LLM timeouts.

#### **NFR-3: Security & Compliance**

* **NFR-3.1:** All stored database credentials and API key tokens MUST be encrypted at rest using AES-256-GCM.  
* **NFR-3.2:** Metadata transmission MUST enforce TLS 1.3 in transit.  
* **NFR-3.3:** The platform MUST fulfill GDPR compliance requirements, ensuring no schema payload or column metadata is retained by third-party LLM vendors when using zero-retention parameters.

## **SECTION 2: Technical Requirements Document (TRD)**

### **2.1 System Architecture & Technical Stack**

                     \+---------------------------------------+  
                     |         React 18 / Next.js 14         |  
                     |   (@xyflow/react, Monaco, Zustand)    |  
                     \+-------------------+-------------------+  
                                         | REST / WebSocket  
                                         v  
                     \+---------------------------------------+  
                     |         FastAPI Engine (Python)       |  
                     |  (SQLGlot, NetworkX, Instructor SDK)  |  
                     \+----+-----------------------------+----+  
                          |                             |  
                          v                             v  
           \+------------------------------+   \+-------------------+  
           |    SQLAlchemy / Asyncpg       |   | LiteLLM Routing   |  
           |  (PostgreSQL 16 / Redis 7\)    |   |     Gateway       |  
           \+------------------------------+   \+---------+---------+  
                                                        |  
                                \+-----------------------+-----------------------+  
                                |                                               |  
                                v                                               v  
                 \+------------------------------+               \+------------------------------+  
                 |    Cloud APIs (SaaS Mode)    |               |  Local / Air-Gapped Engine   |  
                 | OpenAI / Anthropic / Mistral |               |  vLLM Container / Ollama     |  
                 \+------------------------------+               \+------------------------------+

### **2.2 Core Component Specifications**

#### **Component A: Graph Parsing & Validation Engine**

* **Library Dependencies:** sqlglot, networkx, pydantic-v2  
* **Responsibilities:**  
  1. Converts JSON schema representations from LLM outputs into directed acyclic graph (DAG) objects using NetworkX.  
  2. Runs cycle detection algorithms (![][image7]) to prevent circular foreign key dependencies.  
  3. Uses SQLGlot to parse generated DDL and transpile it deterministically across 20+ SQL dialects.

#### **Component B: Agnostic LLM Gateway & Orchestrator**

* **Library Dependencies:** litellm, instructor  
* **Responsibilities:**  
  1. Enforces rigid structural adherence on LLM outputs using Pydantic models via Instructor.  
  2. Reads task routing rules from /app/config/model\_router.yaml.  
  3. Intercepts outgoing API payloads to mask sensitive schema names if MASK\_METADATA\_IN\_PROMPTS=true.

### **2.3 System Database Schema Design (Metadata Store)**

The internal metadata store runs on PostgreSQL 16\. Below is the relational DDL for core platform state:

\-- Workspace & Project Isolation  
CREATE TABLE workspaces (  
    workspace\_id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
    name VARCHAR(255) NOT NULL,  
    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP  
);

\-- Data Models (Schema Instances)  
CREATE TABLE data\_models (  
    model\_id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
    workspace\_id UUID REFERENCES workspaces(workspace\_id) ON DELETE CASCADE,  
    title VARCHAR(255) NOT NULL,  
    current\_paradigm VARCHAR(32) CHECK (current\_paradigm IN ('3NF', 'KIMBALL', 'DATA\_VAULT', 'OBT')),  
    target\_dialect VARCHAR(64) NOT NULL DEFAULT 'snowflake',  
    version\_number INT NOT NULL DEFAULT 1,  
    created\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP,  
    updated\_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT\_TIMESTAMP  
);

\-- Entity Nodes (Tables / Hubs / Dimensions)  
CREATE TABLE model\_entities (  
    entity\_id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
    model\_id UUID REFERENCES data\_models(model\_id) ON DELETE CASCADE,  
    entity\_name VARCHAR(128) NOT NULL,  
    entity\_type VARCHAR(64) NOT NULL, \-- FACT, DIMENSION, HUB, LINK, SATELLITE, TABLE  
    canvas\_position\_x FLOAT NOT NULL DEFAULT 0.0,  
    canvas\_position\_y FLOAT NOT NULL DEFAULT 0.0,  
    description TEXT,  
    UNIQUE(model\_id, entity\_name)  
);

\-- Attribute Columns  
CREATE TABLE entity\_columns (  
    column\_id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
    entity\_id UUID REFERENCES model\_entities(entity\_id) ON DELETE CASCADE,  
    column\_name VARCHAR(128) NOT NULL,  
    data\_type VARCHAR(64) NOT NULL,  
    is\_primary\_key BOOLEAN DEFAULT FALSE,  
    is\_foreign\_key BOOLEAN DEFAULT FALSE,  
    is\_pii BOOLEAN DEFAULT FALSE,  
    pii\_type VARCHAR(64),  
    description TEXT,  
    ordinal\_position INT NOT NULL  
);

\-- Relationships (Edges)  
CREATE TABLE entity\_relationships (  
    relationship\_id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
    model\_id UUID REFERENCES data\_models(model\_id) ON DELETE CASCADE,  
    from\_entity\_id UUID REFERENCES model\_entities(entity\_id) ON DELETE CASCADE,  
    from\_column\_id UUID REFERENCES entity\_columns(column\_id),  
    to\_entity\_id UUID REFERENCES model\_entities(entity\_id) ON DELETE CASCADE,  
    to\_column\_id UUID REFERENCES entity\_columns(column\_id),  
    cardinality VARCHAR(16) NOT NULL \-- '1:1', '1:N', 'N:M'  
);

### **2.4 Internal API Contracts & Specifications**

#### **1\. Transform Paradigm (POST /api/v1/model/{model\_id}/transform-paradigm)**

Transforms an existing data model graph into another data modeling paradigm.

**Request Payload:**

{  
  "target\_paradigm": "DATA\_VAULT",  
  "preserve\_descriptions": true,  
  "options": {  
    "hash\_key\_algorithm": "SHA256",  
    "satellite\_split\_strategy": "BY\_UPDATE\_FREQUENCY"  
  }  
}

**Response Payload:**

{  
  "model\_id": "7f8b9c2a-4d3e-41a2-b9e1-2c3d4e5f6a7b",  
  "previous\_paradigm": "KIMBALL",  
  "new\_paradigm": "DATA\_VAULT",  
  "generated\_entities\_count": 8,  
  "entities": \[  
    {  
      "entity\_name": "hub\_customer",  
      "entity\_type": "HUB",  
      "columns": \[  
        {"name": "hk\_customer\_hash", "data\_type": "VARCHAR(64)", "is\_primary\_key": true},  
        {"name": "customer\_id", "data\_type": "VARCHAR(32)", "is\_primary\_key": false},  
        {"name": "load\_datetime", "data\_type": "TIMESTAMP\_NTZ", "is\_primary\_key": false},  
        {"name": "record\_source", "data\_type": "VARCHAR(128)", "is\_primary\_key": false}  
      \]  
    }  
  \],  
  "transformation\_execution\_time\_ms": 340  
}

### **2.5 Verification & Acceptance Criteria (QA Test Matrix)**

| Test Suite ID | Test Description | Target Requirement | Pass Criteria |
| :---- | :---- | :---- | :---- |
| **TS-01** | NL-to-Schema Extraction | FR-1.1, FR-1.2 | Extract ![][image8] of explicitly named entities and attributes from standard PRD text. |
| **TS-02** | Cyclic FK Detection | FR-2.3 | Flag cyclic table references (![][image9]) instantly on visual canvas. |
| **TS-03** | Transpilation Integrity | FR-4.1 | Generated SQL DDL executes without syntax errors on target engines (Snowflake & Postgres test instances). |
| **TS-04** | Air-Gap Network Isolation | FR-6.2 | Zero outgoing HTTP/HTTPS packets detected beyond local subnet when AIRGAPPED=true. |
| **TS-05** | LLM Provider Failover | FR-5.3 | Automatically switch from primary LLM to designated fallback within ![][image10] of API timeout. |

## **SECTION 3: Acceptance Sign-Off**

| Stakeholder Role | Name / Title | Sign-Off Status | Date |
| :---- | :---- | :---- | :---- |
| **Head of Product** | Lead Data Product Manager | Approved | August 2026 |
| **Principal Architect** | Platform Enterprise Architect | Approved | August 2026 |
| **Security Officer** | CISO / Compliance Lead | Approved | August 2026 |

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAKAAAAAaCAYAAAAwnlc+AAAFeklEQVR4Xu2ZXWgdVRDHNySFaq3fMZiPO7lJIASVGoKIVsEWFatURKEV4oNQpEEKiqXG9kmQIhVtkYiC9UWkBKH0SaUUEcGXgr4o+IFQUKgVKbUgtWDF6P/PzklP5u7eu2fv5uFezw+G3T0zO2fn7Jyv3SSJRCKRSCQSifzvGU150pZXjYhM1+v1B215KFX5aQbq2AQ5C/mXUqvVjg8PD1/h9BMTE1ejzU44vcqxgYGBdb6fVuCeHZALno+3UNzj9ENDQ8Mo+8GvB/W+6bmoBPi9G/KrV8+3g4ODN1o7B9rjAdj8o7Y8fopnvcHa5YIbpiDPQj6jAwT1vrWpAvi9Ew/7Iur4kg+L83lrU4Sq/ATSg7rehVyC/AW5yxqg7HHIUT85Q+nv779Kk5n1nIbUrQ3K9iHmV3Haa3VVgnpeh/zC52DyWz1hokG/CPmDsaOoz9q0BDdOIejHJM3806ucgFtRx8OQP8smTlV+QkAd17FdcHxOMkYngrIXILN+WSjwPwYfhyGvaT27rA3KFmB3jy2vEnYE1PMBR1ht4xlrA3qgn4Pshc0S47cGQcDBzZCfVysBHQxGg2orcaryUwRM8xtQzyFto++lcXTqw/Vh2nllwcDHFsiekZGRW3E8Dzk5NjZ2jdNrR/gQ9Qz491WN6wg4bpN0ltlqbVA+rQn4Es7/brtTaOOGJmAvGyUxo0EzqkqcMn4Q21r2blveCtQzi3t38hzHl/lSxBuduEbSEZJtURr6ho/7kzShObUtoewhp8f1FPTvUH/5rnzKxosO8Cju3YvjHajzopjRjcsMPiuOQ9B9DDnVdqcok4Cwf0Nfxm6ry6NM4mQR6kfXK19LOrJMW30zYH+Q9fE8a3Ri78f1wsq7wuCmBT7e40vlNRNP0qltMdGEw/msFJzq2onXdQRJ9wfnIPuNfjv1moA/Sdn1n4+US8DdbCTcM2d1eYQmTh6hfrwF/lncc4vV58FRjW3i7QQbRiccd0pF6z/4WstrJjeuT0LOM+lZBt0BJvvKO7MpG69b/3HjwVEN56cgRxKd5eBzVNu8T5O0/fUfkRIJSFyDFSU0cfIo6ad3ZmZmjS1shlv/Jd4yg4mnDb/I6YiJU9X6z5TtkvRzC0ekMuu/4Hj9jqDJ+DlFp3Im3TyTUG3npYr1HymbgKGUTJwGqvLTCvHWfw5/dIJsZpsxQXybUDTJuP5bBr7rkm54uPHZVAtY/5XFrf/0kp+fjoiu8fh80G2nggkqVa3/SEzATPgCFrgYtwrU+5Sk69/v0GYHrD4Ef9ozKtb/itbzle0Iq4HtCKh3P+Qcyu9jnO47p34YZ+dof/1HpEQCcnhH9kvIMN8qcVD/tRRbbmnlJwuOXEimwaTgrp2jGtsj60+Aro84MjE5ctd/ReKpmfWfj7fpCZ7qQuPVjrDI53Flkn7f5E74qHibGSapVLX+I6IJKN6CsxWiu2D2GqvLwyUOZJ/V4aVOovw3afzO1kAzP1l4u8LMPxlZwG4z5BgS8EqrI4xb0l3ilNWRgvH0wM/T0L/Nc6tMLm96mv4Ss5SJF226EbYfTU5OrvfK+NGf75jT8vLzSToyBneKBjST2UDufx7lAir8BsPtbdbeBzbPS/rb6Amrs8B2DnZnvDoov0O+GB8fv4k2Oqyz0ZYYuPVBivjJQnv3J7j/R47aVu+jbeL/l+VLfMTacXSC7XGOlFZHWsWjsbD9XD1nUHZ7hh03PcufY4oQEi/iuFfSUdY9B59pB3Xs6PBxwv3fRflBWdk2l9gGyJXrV3rtYBDQMwhsiy3vVLotnm6HUw5/hOdNWZ1Gt8XT3XC6GU13lVnroY6j2+Lpdvihc5v/A77D6bZ4IpFIJBKJRCKRSKRz+Q/2E/HgcWOjowAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFYAAAAZCAYAAACrWNlOAAAEmUlEQVR4Xu2YXWhcVRDH79KKFb8QjdF87NlsoktR/CCoWLSolILYaqmKonnRIkpRfCgolihIEUQRoUYqRVAfRNH6UMQXFSoqNKAUH6x9sQ9KpVCJeamiBaO/f+45YXa8N9nNVkW8f/hz98yZOzNnztzzsVlWoUKFChWWQqPRWAVvGBkZWT84OHiuZAMDA+chu8Dr/iOo1+t3hhDW9PX1nUGzNjo6ej6yCQK6wuoNDQ2dht49cDd8jgG0bL8HNh5H748OOANXyy/P/a7vd3gEHo+/P8fvWszXrC/kN8Nv4STcAj+GLzOGD4ljo9UtBMo3wmleuHt8fPwU378MrMTeO3EQlu82m82zk5J+I/sI7tAEKOn8/gbebo0VAZ3t0eZmK1f8DPoB5DPDw8NXJTnVNhTyZH5B/zlJronF79PI5+C2LCYXnUtoH8bG9UlXfcgfk9+OEivEyrkffgW39Pf3n+51ugE2XoVfE8D3PPfAWxCvsDqx+toGSvteeIgK6re6HqlySwZYo2/K9tG+EH4HP4lf0QL0aSM/CGdJ5KWSFcUmxGKYLvFbDs24KpeXv4STY2NjZ3mdTsC7L+F83MsTFLACx9cbVq4qQ36c561W7lGUWMWeCoK+zdJJfYslVm3JrT3FRfso7abVFZA/03ViDVZg4Cb4GXw+LdydYqnE0r8azvjE6h3kPyt4K/coSmyclK36jd0GfRtSX1gksWmS4Ry/10nG6w/KPnwPuwNWX8uKqtzKloMaTq7BwT44pQC9QhGkS5Av8jwQ8rVNG8iVqT8lsCyxXu5RkFgVwqTkbYoRijuUJFbrKPLf4PtaEiWLa/Ih+YicxfbrPNdkbknrCSwJp2L4KQwfwfmY7/dA9zWS80QWg6A9wbs/sXZeHdsbFbBPYLeJlc3I+QR0kNgfFVvITyG78bOX5wm40+8rqnrwabJtfOzqeZO3mxoGH/XOy9Bqtc7MzMyaXfmtLD816CjTc2JTxWqgtJ/sILE/MLmXx/Y88bXK61uowrG7Dr6C/i/R74TX6whKoBKJkQONk3AMMwM7rB2/LIFlcg+f2Ci7Dj5i9RKMf3HJ5YyCuqioiBr5sqg94IOlJqQNOgWE/ECsc+1t2TLWE967j/fneD6UZH5gJKDJ86hPYEos3G7lHkWJtacCD+/f93uE8s1XX5uOj39ZqwsRHWtz2hd6XKDToG1izVIwH5A54rTNvD45ZCf0TLIiFCV2McTxdZxYTTh6D3t5lp+R34R7+L3Sd7aB4DZgaC+f6GWZu9YtBzi9Fk7Z5QP7dyH7NZhbFX4n6vkFYiSKFPQOOG1vaEUI8ealBPu+IpiJ7SaxsyEvsgVo4w75jWzRc/bfBSVoW8irX3fsnSG/u+uMuTBx8fq5S3oMZFPIk3qw4f5PsNBXgM6x0L5TH8PO20XLQPyvQGdx7fxJX19EoX5CPT/VPNvITwX6sraGfInUOBauvv8KGNSwEsaXsH6RCqzRdzEDuQO9tb1ukicLxNKKsegcL2zSstPVRUkGtFMHcwQpoyog62H9/V9Bn16IB+YO+IIS7G1UqFChQoUKFf7j+BOUIKayvoUppwAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,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>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADYAAAAZCAYAAAB6v90+AAAEF0lEQVR4Xu2XS2iVRxTHb4hCxReUplfzuPPloSGIqKQqgooLEQutiLrwWUpbESEFTUGtdBGRLBQRCahBBF8Uu9JNRUxdtGajIpiNtYgiQlsXpS4CSlVI+vvf78x17pfv5l5wI3j/cJg5Z/5nZs7MmfPdm8lUUcVboa6ubkpra+vHdGuTYwFq29vbpyaN7yycc+uQQWQ/cimKohlJDqjFvo/x7uRAKhobGydB3oycQnobGhoakxyhubm5nfHDxlufGf9kQ9SwocX49CEnmGe5bH6QW2rCPpTL5ZZKp92K/gyfHvY2i/5M+quRAcau6Wa9b0noZCD/RntMAdH/jIke+0UM2tiXyIOmpqZlbAyK+xE5r0MJeGPQ2dk5URtEbsOdi0+HrXcgY8Fh+xR54g+U8Rb0o0gz/Q20W+Cvpb2ELChaoAQmQDyN3GezWW9E70VutrS0TJfO5J3oz5Euz7HF/2bBjd6WBhen2CuduLfp0LD9iywxfS/9J8hM89ENnQtvBn2HqzQFIXbYAr+Gk7DQ59hGaFcaTyk0KrvniC8/5AqLfuDtIWTXOPJch+Pt2rgF0me6gi8EZpnT7+elP4exCxWloBDcRFpgCmSvdJ3eOIEVNpREwCkVWH5de7t/kOYLNa7bRXarr1TH96yrMAXzKBcYclp6mcCG2dg8bw9RQWCP7AnU0P+OdW7QfoX87N8b/W5JYdJKoDeE001kMPw2uPiNjSog6bQbpSPrPCcXv7GnLrHpJPDtgfPC34aQi9/Ya5e4bW6nTYfX1tY2TTpjC9B/8ofuqzJzblJR8n6pgLge+QfyYum0Efr9MDA7gOsscsYmVJXU92SkXGCqoHAfIN+j1sjfxQVrNBlYCAWjoBScdOZZhH7Lgt3OfLsywScjDTW5uMQ/tIUuR3EFKrwxgdP80MUl/i/b6M4oTp2Sm/Oww7ouX+Qu824zv6InEMIVp6Cq90WkV4q9u37ahsClPCywkZxVxTTU19d/BOeeG6cqloJ7U43zVTEJNzYFs9gehQdN/9vxMiVPwGlQKWMm3eAZF3zHrPzqo1q4fk0KZzgq/o7pJ49QCFSFBd4QtrXexntbg+2Fs+9YiGQKCs6KTRgYeleafwFRXPFeepJymf5TLe45FoSq50XUCfZOTuE7EKYStq9d/HbyPPPNV1i4PdKD93rSc0Iw1q2MCW0qbNgHg8BURY8gHSGvCHZ6vyPfID8gfzLBF5ngYVrZvqpgXPzzZoD2lyjxQ9WC+I92T8b8ddvY7iAHXRz4HWVENpudHPoKLk7Bs2k/0xQU45d1qFY99cbG8IqgHNamaFelLShoQg7hE3gbOPXZmTIVKYRSE1mhdNQP3uS4IA4bP65NJ8cEBQHnkIv/AehQ5yc5VVRRRRVVvFf4H+5XQ7Q3gKuZAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADgAAAAaCAYAAADi4p8jAAAChklEQVR4Xu2WPWgUQRTH98hZ+IEa9Dy8j937EgkELQ4RwcYgKKQR0UJiZ2EjCFrY2ogIouQSFD8aq1hI6iBWVhY2QtBasdEQbVTQwvj7uzM6O3crZ7Mnsn/4szfv/WfmvZ15by8IcuTI8c8giqJDcAWuiWEYLtVqtfXW3+l0NjcajcfWb7hYLpc3uutkgAJx7GfvHrxFnCf/JoYCk+7Cb/ArPOALsB2Hj9zkM0SR5GbZ/0q1WiWE2i7GTxkvN5vNyBf3gbcxzoQHPM+bE5rHXHA12C7AGdeWFdh3Aq7qJpVKpU3GNmNi7fn6PvAW9pLcTcQ74Sv4FjYdSZHxPekcW2Zg393s/w6+4AS3yRbFN0oJ3vf1fdDb4O2c1W+el83Ec9ZfqVS2mxMe/z0rW7D/Vnt6QVxS8/C7Ek0IBwHRDYLv6ne9Xp9k/BE+a7VaW2TDd5DxXHLWyKBmc4R4PsDr3W53nS9IwNafTsmYdB0X9HawH5VBp6tTdqalggbQQfucdd8MS9Y/5a8zCGgPS8/675lzx4k5Hbb+AqepKDFz/AvqmtEI6y8FY8R8VTdNSfvOBHQytv4sdDV1Rc1VnRp1/Q0CpbSP2L7A5Xa7vcP3W6hY5yT2HSR0OoqbzUsSvOb7/4AxbRjFHXkoOs1jILg9e9D19LQ2M/c1/Bya/tEHnYpXf7/AYuUo/mSsRUPWn6B/F+inWfvEsEQ/4a/jQjEqDj2tTUkpObiaOh/HFFwkwQ2+T2jEn4z0BTICyVwihhXb9Izt5w3jeZth0ZHH3QjnJ3M6ov6eTSdEQfzJQLsUjrj+TE9QZ38Cz8CLip+4HtpP2f8Aff+EYyJ1XvcFOXLkyJEjR44g+AEE4bqcuhHYwgAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFoAAAAaCAYAAAA38EtuAAAEzklEQVR4Xu1YTWhUVxR+QyJY2lpLTUP+5r5MAiHU0tShpQFxkf7QLCwiKgXdlZLSZa3YtBtBsnAjmgimIRClhEAVN6VYQqhCSxe6K4QIKlYJSiu2UMjGtsbvyzt35njy5k3mJxaG+eDw3j3f/Tn33HvPPe8FQR111JGApqam58Iw3Gj1tYZMJvNCNpvdYPVloa2t7aXOzs730un0HudcL1QNto4GHNyHulM0wnK1BvjlTfhkupK5ptDJDjjtCjq6CNlPQXkWz+sdHR1v2AYEFqUd/CU4+hWvQ5tj0D2ELHuB7qRuh/oHDD/b3d29SddZb2DcQW1DEfnMt6PtkPGSdzYbiHNuWYeSg34C8hfkdc0BKbQ7ATli9JxEC+S2SIvlCRi7D9yPXV1dL1vuaQL2n4Ud/8Ce7YZKQb9N5rDbK9vb259B+TutKwo6EgOcRqM/eSwsT4DrhTyAnEIx5fVYlK3QXeNTVV8BYza4y5B76D9jeR49cOf0SSgFsLUZ7Seam5uftVwpwPgvop+rkN/gwDbLE+AmUe8drcPifAj9L2sOIWjwCRo84tNyHsqY+dbW1i1Kfxi678P4S7AR3HnIEuplLYk2Q04dx1KBti3ciVxQy5UCLNhr6Otv2opio6gb0XefDw14P8l6+VYrc8+gzY2YU7AaWMFuVL4LWeAOsbyHcnQuDNC5dDLkS1vfA9wkZBntd2q9jHuBl67Wl4JqOdpFdxFtPOx13Nm03Z8WvO/GWJvzrYKAHPRzSfPPAY2PcBDIiOU0ZPXuOeVoPlm2TtSQHc+LbsjrJFSNQ97VdUtFFR3NzfAv+trFPrHhHN6/LuYTguOj3nSgwukqqBj6yMYfC/KsB/mpp6fnedFlUf496eg42S1OrTodDANPBPljWhaq4Wh1Uv+DLKJ8B88/WC7mE0I20uVEG2ioi3YoLznmygUBfpQO4wnwOjqahvGpqj4BJ+kTHcIyQwXKMyiHpmoieGzF3pxIbD0nYegJLnHiCrJZlpyKz9xIKH+bzl/gDX5zWYijr3LBLJeDGJWYfhFIvTrAX4fcT6sMYS2OVhOZky/HL6A7YOslQWLhVy5KMbVMQ26hv6kY7iPbTxxc/sTlLmXJZsZCueDDKLv4NN8qD3H0zaT7LWD2gErzLtnRzJOHxZiDmliLo+VjZtFFq/425AxzUFuvHNDmCkNHShYpLn9egYTXbyCdliPE0cmhI4jSr5mkgZhXu+hDZcJ+BaWjC5IZy6DWa6jFZB+X3OoPnrLhKnR0Oh+fC+5Inj7wY0GByw7cCGSuaC7PidMJXFnrSOgHXHQxHI/bhd6JocooLNSFyzg9HBQwuBxUwdGr4rMHHccwB+4+pF9zCvxqZPgatUQs+MmNyjfC6B/Hyv8NyEWUf8VzICjsHH/0EgeiM9h3JTlzHMp1dDrKoHgSl0VyGQfFqX80KP8Qt8kIngjOC/77wHJJaEDHvWi8B7ITjVuDwg7OgRcFB+OglvOAoa8yN7X6SlGuo6sFjN8PWXAF4ndVIenaz5jw+5Zbb9DBWOC9QYX5eJlg2DhK4bsl1wU8Oi7KZ2OPWC1Ccve59TipSeDqHqLw3ZK1BvmFMOVK+UVaLcg/688RQt6yXK0BTv74/wiVddRRRx11VB+PAQtveJsprfCIAAAAAElFTkSuQmCC>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADQAAAAWCAYAAACPHL/WAAAA8UlEQVR4XmNgGAWjYBSMAnQgLy/vCMQnFBQUIoyNjVnR5YckkJGR4QR6KgmILwBxsri4ODe6miEJQDEEiimgp84AcY2KigofupqhCpiBHnIC4sNA3C0tLS2MrmCoAkZgjJkDPbUfiKcAsSS6giEJgEmPXU5Org7ooSfA/KaCLj9kAHJhAfRQ/pAtLEAOB3kA6JFzQ7o4B5VqoNJNHlIv+QOFmNHVDAkAyuzQTA/K/FYMQ9UjIABMWj7A2NioqKioB+QyosuPglFAZQAqwYDJTRyaj/BiZWVlMYbBnr+A+ccA6NhZROJekMfQzRgFo4A4AACVVzRU1EPlKQAAAABJRU5ErkJggg==>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAI0AAAAXCAYAAAA2o8yAAAAEsElEQVR4Xu2ZW4gcRRSGe9h4wyvouu5tamZ3ZM16A1cUbyBiVPCCxCjIRhDxAhFEhY0afFMfNCgKihINEkIUwcUnL0gegg/qmyIBHySoIRhUNCgKEnHj96erTXnSk+6e7t2dQH9wqJ46VadPVZ269URRTU1NTU3N0YlzbhjZ0Gq1TrO6mkoYGB8fn6R/b22329dNTEycmijo93an0zkuLHw00MDxp5A9o6OjY1a53NDRd+Lbr8iBQPT7J/+8H3mdcmfZusvN2NjYCfg2h/yBfIE8h2xAPkfWNZvN20nn8f14W7evwfEZHP9Tomer7wfUqfj3vksJbHy+Qr5T5uPBwcGTQt1ygk8rka8VLPg4HepmZmaOwd930C0oiEJd3+NnwlYatZv0b9IrbZl+AD9H8e87BY6dlQoU8nf0U9CzFV2MPz8j28OtKARfr0W/X6nV9TU4vRrZyEA8TnqABtxsy5RFA4mssvlFUDD7oH7M6oKA2oO0rb5XeNdN2D7f5mcxOTl5Jn7sRHbRry2rT1C/oP7Krpxl0JkUu/fzuMLqKsE3bp50XIOhoEFmbbmyMOvOw+7zPDasLi/ev4WUWdmgo56Q76QPG10psHcD8ojNzyA5H2oCHhbgIQoayr1lV84yaOfA7muaSFZXCTg8xwvW6lkrTJ6G9sgKBY06ySpyovrvInuRi1x80xumY84m3YR8g1wTlQjKNPy294YmldV1g/JtF694e2nvhNWH6FzTbesqA+9e3UOwZ0ODzsX41uTgmAQN8owtWwVcM50GoNXDDSfYfr51cZAcFGxtcfFB80HNMFuvCvD7Et7z0tDQ0IlWlwar6i2+Hw87ey0V/pD9bMqq3DsySqNepoFXJXlNf2bQQIRl01B9OnPI+RlfQG508VWz0KqQ+Ja2CuLvpS6++c1nBY4GMcWnPHIvdT9pmhtQGvLRVTv5Gpx5Tk/x6YiCv+eQfoA/67P6JRcYWoXBf9z/v3skkjlDKHO5C2Z8AdmM/ODiK2jurcoPxELazAluTr8TyBdafQj116T4lEe2Ifuo/5FWTGs3JAmatAAPcfHgPj09PX2s1YX4c+fGFJ/yyKfIb/hyH6YGrO3caA/F0NtEXyfMd3Ejvkd2LMa3Dr9kvoj9e6ICDfCrQ+r3GeFXPG1RvyArrb4svr+24cf1UY7VkbKzLl/QzGLzAZtfFS6+FW/qdDqnWF1hMPRomrNB0OzSQFh9WXxnzkU5Oj7kSN9nBIOz1g/Sq1H110zdhJ5EbrOKbtB3U5T/UatSt22BdrQ0oItxCBZaEHjFlirsN5rx2eBLjDWt0s+oz3zgDFt9GRSEvPvNXhqhLcmlfDXVyqVl18Xb7Ie92M7Cfyp4JSoWjOrn9S4+H96t36GSvrgA3XtZ21wJFOj6q+IyqyiEDrwY2ecOnVt0HfzvUMfvF1z8/02i1/PmrP02Lxr4VsErIHXucof+WzroE3m7JS4+FylYdvL7jqjAdlcEBaVuQzY/BwPUfQj//nLx+U1BtA7Zri26ki2jCyMjI2do1V2MI8aSom0lbWvpd3TN1opm8/Pi2301g7hG6RIN5MDU1NTJNrOmpqampqampqamJgf/Anh8dC874NMBAAAAAElFTkSuQmCC>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAWCAYAAACCAs+RAAAAzElEQVR4XmNgGAWjYBSMgmENxMXFuY2NjVnRxYcMUFRUVJeXl18NxMtUVFRE0eUHO2BUUFAwBzp+PxBPUVZWlkVXMNgBM9DhTkB8GIi7paWlhdEVDHbADIwBf6DjTwBxDTAJ8aErGNQAlHmBHogAOv6cnJxcPihDo6sZEgDoAUcgfgD0TIaMjAwnuvyQAmixUjbkkhUWAMsnp4dqRkcHKEUvEEuiKxhqgBFYGeoBPbIdiOcCsSK6giEHQJ4A4i5ggaCCLjcKRsEoGNwAAPf+Iwm5yMq6AAAAAElFTkSuQmCC>