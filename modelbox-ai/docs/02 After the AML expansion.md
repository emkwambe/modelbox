After the AML expansion, I would treat ModelBox as having **one coherent portfolio of use cases**, rather than “original ModelBox use cases \+ separate AML features.”

### **Combined ModelBox use cases**

| \# | Combined use case | What ModelBox does | Primary users |
| ----- | ----- | ----- | ----- |
| 1 | **Requirements → Data Architecture** | Converts PRDs, requirements, Jira stories and natural language into conceptual/logical/physical data models | Data architects, analytics engineers |
| 2 | **Regulated Domain Modeling** | Converts domain requirements—starting with AML—into governed entities, relationships, constraints and analytical structures | Banks, fintechs, architects, compliance data teams |
| 3 | **Warehouse/Lakehouse Design** | Generates deployable Postgres, Snowflake, Databricks, BigQuery, etc. architectures | Data/platform teams |
| 4 | **Multi-Paradigm Transformation** | Transforms models among 3NF, Kimball/star, Data Vault 2.0 and analytical/OBT structures | Data architects, BI/data engineers |
| 5 | **Legacy System Reverse Engineering & Modernization** | Understands existing DDL/schemas, discovers relationships and redesigns them for modern platforms | Migration teams, consultants |
| 6 | **Analytics Engineering Generation** | Produces SQL, dbt models, tests, transformations and semantic-layer definitions | Analytics engineers |
| 7 | **Synthetic Data & Scenario Generation** | Generates referentially correct, privacy-safe datasets; AML adds embedded known behavioral scenarios | QA, analytics, regulated teams |
| 8 | **Feature Engineering** | Defines and generates reusable behavioral, temporal, aggregate and network features | Data scientists, AML analytics/model teams |
| 9 | **Rules & Detection Engineering** | Converts analytical requirements into transparent, versioned detection logic | AML analytics, fraud/risk teams |
| 10 | **Transaction-Monitoring Simulation** | Runs structuring, rapid movement, fan-in/fan-out, circular-flow and other detection scenarios | AML/TM teams |
| 11 | **Graph & Relationship Analytics** | Finds connected entities, shared identifiers, cycles, clusters and transaction networks | Investigators, fraud/AML analytics |
| 12 | **Alert Analytics** | Analyzes which detections produce alerts, alert volumes, overlap, priority and operational burden | AML operations/model teams |
| 13 | **Investigation Analytics** | Creates entity timelines, transaction histories, network views and evidence packages | Investigators, analysts |
| 14 | **Threshold & Rule Tuning** | Tests “what happens if we change this threshold/window/rule?” before deployment | Model/rule owners |
| 15 | **Backtesting & Detection Performance** | Compares rule/model versions against versioned datasets and known synthetic truth | Data scientists, model validation |
| 16 | **Explainability & Evidence Lineage** | Traces source record → transformation → feature → rule/model → detection → alert | Governance, validation, audit |
| 17 | **Model/Rule Validation Environment** | Provides reproducible test environments for independently challenging analytical logic | Model-risk/validation teams |
| 18 | **Data Contracts & Event Schema Engineering** | Generates and validates JSON Schema, Avro, Protobuf and producer/consumer contracts | Platform/data engineering |
| 19 | **Data Catalog & Business Glossary** | Documents tables/fields, maps business terminology and identifies sensitive data | Data governance/stewards |
| 20 | **PII/Sensitive-Data Architecture** | Identifies sensitive fields and supports architectures that minimize unnecessary exposure | Governance/security teams |
| 21 | **Sovereign / Air-Gapped Analytics Design** | Runs architecture/AI workflows locally with zero cloud data egress | Banks, healthcare, government, defense |
| 22 | **M\&A Data Consolidation / MDM** | Finds equivalent entities across systems and proposes unified enterprise models | Enterprise architects, M\&A teams |
| 23 | **Query & Warehouse Optimization** | Uses query patterns to recommend physical modeling, clustering, partitioning, materialization or OBT changes | DBA/FinOps/data platform |
| 24 | **Prototype-to-Production Artifact Generation** | Exports executable DDL, SQL, dbt, contracts, metrics, tests and configuration | Engineering teams |
| 25 | **Regulated Analytics Sandbox** | Lets organizations experiment with architectures, features and detections without exposing production customer data | Banks, fintechs, consultants |
| 26 | **Training / Technical Simulation** | Provides realistic environments for learning SQL, AML analytics, data modeling and investigations | Universities, corporate training, candidates |

### **The important consolidation**

Several of these can be grouped into **six major product jobs**:

**1\. DESIGN**  
 Requirements → domain model → warehouse architecture → schema transformation.

**2\. BUILD**  
 DDL → SQL → dbt → semantic models → contracts → features.

**3\. SIMULATE**  
 Synthetic data → scenarios → AML typologies → rules/models → detections.

**4\. ANALYZE**  
 Transactions → graphs → alerts → investigations → performance.

**5\. VALIDATE**  
 Backtesting → threshold tuning → explainability → lineage → reproducibility.

**6\. GOVERN**  
 Sensitive-data discovery → data contracts → air gap → auditability → deployment artifacts.

That gives ModelBox a much cleaner overall identity:

> **ModelBox turns complex business or regulated-domain requirements into executable, testable and governed analytical systems.**

AML is therefore not an odd add-on. It becomes the **proof that ModelBox can handle a difficult real-world regulated analytical domain**.

And that suggests an interesting longer-term architecture:

                      MODELBOX CORE  
                           │  
        ┌──────────────────┼──────────────────┐  
        │                  │                  │  
     DESIGN              BUILD             GOVERN  
        │                  │                  │  
        └──────────────────┼──────────────────┘  
                           │  
                    DOMAIN PACKS  
                           │  
              ┌────────────┼─────────────┐  
              ▼            ▼             ▼  
             AML         Fraud       Healthcare  
              │  
              ▼  
     Financial Crime Analytics  
              │  
    ┌─────────┼──────────┐  
    ▼         ▼          ▼  
 Simulate   Analyze    Validate  
