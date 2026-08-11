# Data Engineering, Stakeholder Management & Cloud Infrastructure
## Three Deep-Dive Breakdowns for ModelBox AI Product Strategy & Course Development

**Research Context:** Based on deep analysis of 43+ data modeling job postings (July–August 2026), these three responsibilities rank as the #1, #2, and #8 most frequent secondary responsibilities bundled with data modeling. Together, they represent the **complete operational context** in which modern data modelers work.

---

# PART I: DATA ENGINEERING / ETL-ELT PIPELINES
## The Most Common Secondary Responsibility (~72% of Roles)

---

## 1. What Is Data Engineering in the Modeling Context?

**Data Engineering** is the design, construction, and maintenance of the systems and infrastructure that collect, store, process, and serve data. In the context of data modeling, it is the **implementation layer** — the bridge between the model design and the running system.

### The Engineering-Modeling Stack

```
┌─────────────────────────────────────────────────────────────┐
│  CONSUMPTION LAYER                                          │
│  BI Tools, APIs, AI Agents, Applications                    │
├─────────────────────────────────────────────────────────────┤
│  SEMANTIC LAYER                                             │
│  Metrics, Dimensions, Business Logic                        │
├─────────────────────────────────────────────────────────────┤
│  GOVERNANCE LAYER                                           │
│  Policies, Standards, Contracts, Catalogs                   │
├─────────────────────────────────────────────────────────────┤
│  QUALITY LAYER                                              │
│  Tests, Assertions, Anomaly Detection                     │
├─────────────────────────────────────────────────────────────┤
│  MODELING LAYER                                             │
│  Conceptual, Logical, Physical, Dimensional Models          │
├─────────────────────────────────────────────────────────────┤
│  ENGINEERING LAYER  ←── YOU ARE HERE                        │
│  Ingestion, Transformation, Orchestration, Storage        │
└─────────────────────────────────────────────────────────────┘
```

### The Modern Shift: ETL → ELT

| Era | Pattern | Description | Modeling Role |
|-----|---------|-------------|---------------|
| **Traditional (2010–2018)** | ETL | Extract → Transform → Load. Transformation happens before loading. | Modeler designs target schema; ETL developer implements |
| **Modern (2018–2024)** | ELT | Extract → Load → Transform. Raw data loaded first; transformation in warehouse. | Modeler writes SQL/dbt models that ARE the transformation |
| **Emerging (2024–2026)** | EtLT | Extract → light Transform → Load → heavy Transform. Streaming + batch hybrid. | Modeler designs both streaming and batch models |

**The critical insight:** In modern stacks, the data modeler IS the data engineer. The same person who designs the star schema also writes the dbt models, orchestrates the pipelines, and optimizes the queries.

---

## 2. Pipeline Architecture Patterns

### Pattern A: The Modern dbt-ELT Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   SOURCE    │ →  │   INGEST    │ →  │  TRANSFORM  │ →  │   SERVE     │
│             │    │             │    │             │    │             │
│ Salesforce  │    │ Fivetran    │    │ dbt (SQL)   │    │ Snowflake   │
│ Shopify     │    │ Airbyte     │    │ Staging     │    │ BI Tools    │
│ Segment     │    │ Kafka       │    │ Warehouse   │    │ APIs        │
│ APIs        │    │ Custom      │    │ Marts       │    │ ML Features │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       └──────────────────┴──────────────────┴──────────────────┘
                          Orchestrated by: Airflow / Dagster / Prefect
```

### Pattern B: The Streaming + Batch Hybrid (EtLT)

```
STREAMING PATH (Real-time):
Source → Kafka → Flink/Spark Streaming → Bronze Delta Table → 
→ Silver Aggregations → Real-time Dashboard / API

BATCH PATH (Historical):
Source → Scheduled Ingest → Data Lake → dbt Models → 
→ Gold Marts → BI Reports / ML Training

MODELING RESPONSIBILITY:
- Design bronze schema (raw, append-only)
- Design silver schema (cleaned, deduplicated)
- Design gold schema (aggregated, business-ready)
- Ensure streaming and batch outputs are CONSISTENT
```

### Pattern C: The Data Mesh Pipeline

```
Domain A (Orders)          Domain B (Customers)       Domain C (Products)
├─ Owns ingestion          ├─ Owns ingestion          ├─ Owns ingestion
├─ Owns transformation     ├─ Owns transformation     ├─ Owns transformation
├─ Publishes data product  ├─ Publishes data product  ├─ Publishes data product
└─ Exposes contract        └─ Exposes contract        └─ Exposes contract
         │                           │                           │
         └───────────────────────────┴───────────────────────────┘
                                     │
                         ┌───────────▼───────────┐
                         │   Central Catalog     │
                         │   (DataHub / Atlan)   │
                         │   Cross-domain lineage│
                         └───────────────────────┘
```

---

## 3. Ingestion Patterns & Tools

### Ingestion Categories

| Category | Tools | When to Use | Modeling Consideration |
|----------|-------|-------------|----------------------|
| **SaaS Connectors** | Fivetran, Airbyte, Stitch, Matillion | Standard SaaS sources (Salesforce, Shopify, etc.) | Schema drift handling, incremental sync keys |
| **Database Replication** | Fivetran, Debezium, AWS DMS | CDC from transactional databases | Primary key preservation, SCD handling |
| **Event Streaming** | Kafka, Kinesis, Pub/Sub | Real-time events, logs, clickstream | Event schema evolution, partitioning strategy |
| **File/Batch** | Airflow, Glue, Dataflow | CSV, JSON, Parquet files | Schema inference, type coercion, partitioning |
| **API Polling** | Python scripts, Airflow, Fivetran | REST APIs, webhooks | Rate limiting, pagination, retry logic |
| **Change Data Capture** | Debezium, Maxwell, AWS DMS | Real-time database changes | Transaction ordering, exactly-once semantics |

### Incremental Ingestion Strategies

```yaml
# Incremental model configuration (dbt)
models:
  - name: stg_orders
    config:
      materialized: incremental
      incremental_strategy: merge  # or append, insert_overwrite
      unique_key: order_id

      # Incremental filter
      incremental_predicates: |
        ordered_at >= (SELECT MAX(ordered_at) FROM {{ this }})
```

| Strategy | How It Works | Best For | Modeling Impact |
|----------|-------------|----------|-----------------|
| **Append** | New rows appended; old rows untouched | Immutable events, logs | Simplest, but requires deduplication downstream |
| **Merge** | Upsert: insert new, update existing | Mutable dimensions, SCD Type 2 | Requires primary key, handles updates cleanly |
| **Insert Overwrite** | Replace partition with new data | Partitioned time-series data | Efficient for large partitions, but loses history |
| **Micro-batch** | Process small batches frequently | Near-real-time without streaming | Balances latency and complexity |

---

## 4. Transformation Patterns

### The dbt Transformation Layer

```sql
-- models/staging/stg_orders.sql
WITH source AS (
  SELECT * FROM {{ source('shopify', 'orders') }}
),

renamed AS (
  SELECT
    id AS order_id,
    customer_id,
    total_price AS order_total,
    financial_status AS order_status,
    created_at AS ordered_at,
    updated_at AS modified_at
  FROM source
)

SELECT * FROM renamed
```

```sql
-- models/warehouse/fct_orders.sql
WITH orders AS (
  SELECT * FROM {{ ref('stg_orders') }}
),

customers AS (
  SELECT * FROM {{ ref('dim_customers') }}
),

enriched AS (
  SELECT
    o.order_id,
    o.customer_id,
    c.customer_segment,
    c.region,
    o.order_total,
    o.order_status,
    o.ordered_at,
    -- Derived metrics
    DATE_TRUNC('month', o.ordered_at) AS order_month,
    CASE 
      WHEN o.order_total > 100 THEN 'high_value'
      ELSE 'standard'
    END AS order_tier
  FROM orders o
  LEFT JOIN customers c ON o.customer_id = c.customer_id
)

SELECT * FROM enriched
```

### Transformation Best Practices

| Practice | Why It Matters | Example |
|----------|---------------|---------|
| **Staging layer** | Isolate raw source logic; one source = one model | `stg_salesforce_accounts` |
| **Warehouse layer** | Business logic, joins, aggregations | `fct_orders`, `dim_customers` |
| **Mart layer** | Department-specific, consumption-ready | `mart_sales_pipeline`, `mart_marketing_attribution` |
| **Incremental builds** | Process only new/changed data | `materialized: incremental` |
| **Partitioning** | Query performance, cost optimization | `partition_by: ordered_at` |
| **Clustering** | Co-locate related data | `cluster_by: [customer_id, order_status]` |

---

## 5. Orchestration & Workflow Management

### Orchestration Tools Comparison

| Tool | Best For | Key Strength | Key Weakness |
|------|----------|-------------|--------------|
| **Apache Airflow** | Complex DAGs, enterprise scale | Mature, massive ecosystem | Complex to operate, Python-heavy |
| **Dagster** | Data-aware orchestration, software-defined assets | Asset-centric, type safety, testing | Smaller ecosystem than Airflow |
| **Prefect** | Modern Python workflows, hybrid execution | Easy to use, great DX | Less mature than Airflow |
| **dbt Cloud** | dbt-native teams | Integrated scheduling, observability | Vendor lock-in, limited non-dbt tasks |
| **GitHub Actions** | Simple CI/CD triggers | Free, integrated with Git | Not designed for complex data workflows |

### The Orchestration-Modeling Connection

```python
# Dagster asset example (data-aware orchestration)
from dagster import asset, AssetIn

@asset(
    ins={"raw_orders": AssetIn(key="raw_orders")},
    group_name="analytics"
)
def stg_orders(raw_orders):
    """Cleaned orders data from Shopify."""
    return raw_orders.rename(columns={
        "id": "order_id",
        "total_price": "order_total"
    })

@asset(
    ins={
        "stg_orders": AssetIn(key="stg_orders"),
        "dim_customers": AssetIn(key="dim_customers")
    },
    group_name="analytics"
)
def fct_orders(stg_orders, dim_customers):
    """Fact table: one row per order with customer dimensions."""
    return stg_orders.merge(
        dim_customers[["customer_id", "segment", "region"]],
        on="customer_id",
        how="left"
    )

# Dagster automatically:
# 1. Knows the dependency graph (fct_orders depends on stg_orders + dim_customers)
# 2. Runs upstream assets before downstream
# 3. Skips unchanged assets (partitioning awareness)
# 4. Tests outputs against type signatures
```

---

## 6. Storage & Compute Optimization

### Warehouse Optimization for Modelers

| Technique | What It Does | When to Use | Modeling Impact |
|-----------|-------------|-------------|-----------------|
| **Partitioning** | Divide table into segments | Time-series data, large tables | Choose partition key carefully (date is safest) |
| **Clustering** | Co-locate similar rows | Frequently filtered/joined columns | Cluster on high-cardinality filter columns |
| **Materialized Views** | Pre-compute expensive aggregations | Complex joins, frequent queries | Trade-off: freshness vs. query speed |
| **Zero-Copy Cloning** | Instant table copies | Testing, dev environments | Enables safe experimentation |
| **Time Travel** | Query historical table states | Debugging, audit, recovery | Reduces need for SCD Type 2 on raw data |
| **Search Optimization** | Index for point lookups | Primary key lookups, small result sets | Alternative to clustering for specific queries |

### Cost Optimization

```sql
-- Example: Partitioned, clustered table
CREATE TABLE fct_orders (
  order_id UUID,
  customer_id UUID,
  order_total DECIMAL(18,2),
  order_status VARCHAR(20),
  ordered_at TIMESTAMP
)
PARTITION BY DATE(ordered_at)  -- Partition for time-based pruning
CLUSTER BY (customer_id, order_status);  -- Cluster for join/filter performance

-- Query that benefits from both:
SELECT * FROM fct_orders
WHERE ordered_at >= '2026-08-01'
  AND customer_id = 'abc-123'
  AND order_status = 'completed';
-- Prunes partitions + clusters = minimal data scanned = lower cost
```

---

## 7. Modern Data Engineering Responsibilities for Modelers

### The Converged Role: Analytics Engineer / Data Engineer

From the research, the boundary between Data Engineer and Analytics Engineer has collapsed. Senior Data Engineers are expected to do dimensional modeling; Analytics Engineers are expected to understand orchestration and infrastructure.

**What a modern modeler-engineer is expected to do:**

| Responsibility | Frequency | Skill Level |
|---------------|-----------|-------------|
| Write dbt models (SQL transformations) | ~85% | Core |
| Design incremental loading strategies | ~70% | Core |
| Optimize query performance (partitioning, clustering) | ~65% | Core |
| Orchestrate pipelines (Airflow, Dagster, dbt Cloud) | ~60% | Core |
| Manage schema drift from source systems | ~55% | Advanced |
| Implement CDC (Change Data Capture) | ~40% | Advanced |
| Design streaming pipelines (Kafka, Flink) | ~30% | Specialized |
| Manage infrastructure (Terraform, cloud config) | ~25% | Specialized |
| Build custom ingestion (Python, API clients) | ~45% | Intermediate |
| Monitor pipeline health and SLAs | ~50% | Intermediate |

---

## 8. Anti-Patterns in Data Engineering for Modelers

### Anti-Pattern 1: The "One Big Pipeline"

**Bad:** Single monolithic pipeline that does everything.
```
Source → [Extract + Clean + Join + Aggregate + Export] → Dashboard
# Problem: One failure breaks everything; impossible to debug
```

**Good:** Layered, modular pipelines.
```
Source → Staging → Warehouse → Marts → Consumers
# Each layer independently testable, debuggable, optimizable
```

### Anti-Pattern 2: The "Full Refresh Addiction"

**Bad:** Every run rebuilds everything.
```sql
-- dbt model without incremental config
SELECT * FROM huge_source_table  -- Scans 10TB every run
```

**Good:** Incremental builds with proper filtering.
```sql
-- dbt incremental model
{{ config(materialized='incremental', unique_key='order_id') }}

SELECT * FROM source
WHERE ordered_at >= (SELECT MAX(ordered_at) FROM {{ this }})
```

### Anti-Pattern 3: The "No-Test Pipeline"

**Bad:** Pipeline runs without validating outputs.
```
Ingest → Transform → Load → Done
# No quality checks, no row count validation, no freshness checks
```

**Good:** Quality gates at every stage.
```
Ingest → [Validate schema, row count] → Transform → [Validate business rules] 
→ Load → [Validate freshness, reconciliation] → Done
```

### Anti-Pattern 4: The "Hardcoded Connection"

**Bad:** Credentials and connection strings in code.
```python
# BAD
conn = snowflake.connect(
    user="admin",
    password="password123",  # In plain text!
    account="myaccount"
)
```

**Good:** Environment variables + secret managers.
```python
# GOOD
conn = snowflake.connect(
    user=os.environ["SNOWFLAKE_USER"],
    password=secret_manager.get("snowflake_password"),
    account=os.environ["SNOWFLAKE_ACCOUNT"]
)
```

### Anti-Pattern 5: The "No Documentation Pipeline"

**Bad:** Pipeline exists but no one knows how it works.
```
# 50 Airflow DAGs, 200 dbt models
# No documentation
# On-call engineer has no idea what depends on what
```

**Good:** Self-documenting, lineage-aware pipelines.
```
# dbt docs auto-generated
# Dagster asset graph visible in UI
# DataHub lineage tracked automatically
# Runbooks for every critical pipeline
```

---

## 9. ModelBox AI Integration Opportunities

### Feature 1: Auto-Generate dbt Models from Schema Design

**Input:** ModelBox AI designs a Kimball star schema.

**Auto-Output:**
```sql
-- models/marts/fct_orders.sql (auto-generated)
{{ config(
    materialized='incremental',
    unique_key='order_id',
    partition_by={'field': 'ordered_at', 'data_type': 'timestamp'},
    cluster_by=['customer_id', 'order_status']
) }}

WITH stg_orders AS (
  SELECT * FROM {{ ref('stg_orders') }}
),

dim_customers AS (
  SELECT * FROM {{ ref('dim_customers') }}
),

final AS (
  SELECT
    o.order_id,
    o.customer_id,
    c.customer_segment,
    c.region,
    o.order_total,
    o.order_status,
    o.ordered_at,
    DATE_TRUNC('month', o.ordered_at) AS order_month
  FROM stg_orders o
  LEFT JOIN dim_customers c
    ON o.customer_id = c.customer_id
)

SELECT * FROM final
```

### Feature 2: Pipeline Orchestration Scaffolding

**Auto-generate:**
- Airflow DAG definitions
- Dagster asset definitions
- dbt Cloud job configurations
- GitHub Actions CI/CD workflows

### Feature 3: Incremental Strategy Advisor

**ModelBox suggests the optimal incremental strategy based on:**
- Source data characteristics (mutable vs. immutable)
- Table size
- Update frequency
- Primary key structure

```
Source: Shopify orders (immutable events, append-only)
→ Recommended: incremental_strategy: append

Source: Salesforce accounts (mutable records, updates common)
→ Recommended: incremental_strategy: merge (SCD Type 2)

Source: Daily snapshot (full replace acceptable)
→ Recommended: incremental_strategy: insert_overwrite
```

### Feature 4: Performance Optimization Recommendations

**From schema design, ModelBox suggests:**
- Partition keys (time-based for event data)
- Cluster keys (high-cardinality filter columns)
- Materialization strategy (table vs. view vs. incremental)
- Index recommendations

---

# PART II: STAKEHOLDER MANAGEMENT & BUSINESS ANALYSIS
## The Soft Skill That Differentiates Seniority (~68% of Roles)

---

## 1. Why Stakeholder Management Is a Modeling Responsibility

Data modeling is fundamentally **translation work**:
- **Business speaks:** "I need to see revenue by customer segment, but only for completed orders, and I want to compare it to last year."
- **Engineering speaks:** `SELECT segment, SUM(total) FROM fct_orders WHERE status = 'completed' GROUP BY segment`
- **The modeler bridges both.**

From the research:
- **68%** of Data Modeler roles require "stakeholder management" or "requirements gathering"
- **75%** of Data Architect roles require "business process analysis" or "executive communication"
- **80%** of Analytics Engineer roles require "partnering with business teams"

**The insight:** Technical modeling skills get you hired. Stakeholder skills get you promoted.

---

## 2. The Stakeholder Landscape

### Stakeholder Types in Data Projects

| Stakeholder | What They Care About | How They Consume Data | Modeling Impact |
|-------------|---------------------|----------------------|-----------------|
| **CEO / CFO** | Revenue, growth, risk, compliance | Executive dashboards, board decks | Metrics must be bulletproof; lineage must be audit-ready |
| **VP of Product** | Feature usage, churn, adoption | Product analytics, cohort analysis | Event schemas must capture user behavior accurately |
| **VP of Marketing** | Attribution, CAC, LTV, campaigns | Marketing dashboards, CRM integrations | Customer 360 models must unify touchpoints |
| **VP of Sales** | Pipeline, forecast, quota attainment | Salesforce reports, forecast models | Opportunity models must handle stage transitions |
| **Compliance Officer** | GDPR, SOC 2, data lineage | Audit reports, data catalogs | PII classification, retention policies, access logs |
| **Data Analysts** | Self-serve exploration, ad-hoc queries | SQL, BI tools, notebooks | Semantic layers must be intuitive; documentation must be complete |
| **Engineering Teams** | API contracts, performance, reliability | API docs, monitoring | Data contracts must be machine-readable and versioned |
| **AI/ML Teams** | Feature stores, training data, bias | Feature platforms, experiment tracking | Feature schemas must be consistent and well-documented |

---

## 3. The Requirements Gathering Process

### Phase 1: Discovery

**Objective:** Understand the business problem before designing the solution.

**Questions to ask:**
1. **What decision will this data support?** (Not "what report do you want?")
2. **Who will consume this data?** (Executives? Analysts? AI agents?)
3. **How often does this need to be updated?** (Real-time? Daily? Monthly?)
4. **What is the source of truth?** (If two systems disagree, which wins?)
5. **What are the known edge cases?** (Refunds? Cancellations? Multi-currency?)
6. **What happens when the data is wrong?** (Who gets paged? What's the financial impact?)
7. **What is the minimum viable version?** (Can we ship a simple version first?)

### Phase 2: Translation

**Business Requirement → Technical Specification**

```
Business: "I want to see which marketing campaigns are driving the most revenue."

Translation:
├─ Metric: attributed_revenue
├─ Definition: SUM(order_total) WHERE order_date BETWEEN campaign_start AND campaign_end
│              AND customer_first_touch_source = campaign_id
├─ Dimensions: campaign_name, channel, date_range, customer_segment
├─ Grain: one row per campaign per day
├─ Source: fct_orders + dim_campaigns + dim_customers
├─ Known Issues: 
│   - Multi-touch attribution is complex; start with first-touch
│   - Offline campaigns have no digital tracking; flag as "unattributed"
│   - Returns reduce attributed revenue; decide if net or gross
└─ SLA: Updated daily by 8 AM
```

### Phase 3: Validation

**Before building, validate understanding:**

```markdown
# Requirements Validation Document

## Business Objective
Enable marketing team to optimize campaign spend by measuring 
revenue attribution per campaign.

## Proposed Metrics
1. **Attributed Revenue (First-Touch)**
   - Definition: Revenue from orders where the customer's first 
     interaction was with the campaign.
   - Formula: SUM(order_total) for orders linked to campaign
   - Caveat: Does not account for multi-touch journeys.

## Stakeholder Sign-off
- [ ] Marketing VP: Confirms first-touch is acceptable for v1
- [ ] Finance: Confirms revenue definition matches GL
- [ ] Data Architect: Confirms model is feasible
- [ ] Engineering: Confirms pipeline can deliver by 8 AM SLA
```

---

## 4. Communication Frameworks for Modelers

### Framework A: The Business-Technical Spectrum

```
Business Language                    Technical Language
─────────────────────────────────────────────────────────
"Revenue"                    →     SUM(order_total) WHERE status='completed'
"Active Customer"            →     COUNT(DISTINCT customer_id) WHERE last_order >= now-90d
"Churned"                  →     customer_id NOT IN (recent orders) AND was previously active
"Campaign Performance"       →     JOIN fct_orders, dim_campaigns, dim_attribution
"Real-time"                →     Latency < 5 minutes, streaming pipeline
"Self-serve"               →     Semantic layer + BI tool + documented metrics
```

### Framework B: The Stakeholder Presentation Structure

```
1. CONTEXT (30 seconds)
   "We are building a customer 360 model to unify data from 5 systems."

2. PROBLEM (30 seconds)
   "Currently, marketing sees 100K customers, sales sees 98K, and 
    support sees 105K. No one knows the real number."

3. PROPOSED SOLUTION (1 minute)
   "A unified customer dimension with golden record logic, 
    updated daily, with full lineage and audit trail."

4. TRADE-OFFS (1 minute)
   "Option A: Real-time (expensive, complex). Option B: Daily batch 
    (cheaper, simpler). We recommend B for v1."

5. WHAT WE NEED FROM YOU (30 seconds)
   "Sign-off on the customer matching rules. Define 'active customer' 
    for your use case."

6. TIMELINE (30 seconds)
   "Design complete by Aug 20. Prototype by Aug 30. Production by Sep 15."
```

### Framework C: The Workshop Facilitation Guide

**Data Modeling Workshop Agenda (2 hours)**

```
0:00–0:15  Icebreaker + Context Setting
            "What is the one question you wish you could answer 
             with data but currently can't?"

0:15–0:45  Entity Discovery
            Whiteboard exercise: "What are the core things our 
             business cares about?" (Customers, Orders, Products, etc.)

0:45–1:15  Relationship Mapping
            "How do these entities connect?" Draw lines, identify 
             cardinality, flag ambiguous relationships.

1:15–1:30  Break

1:30–1:50  Metric Definition
            "For each entity, what are the top 3 metrics?" 
             Write exact definitions, agree on formulas.

1:50–2:00  Next Steps & Owners
            Assign action items, schedule follow-up, document decisions.
```

---

## 5. Managing Conflicting Requirements

### Common Conflicts

| Conflict | Business A Says | Business B Says | Resolution |
|----------|----------------|-----------------|------------|
| **Revenue Definition** | "Booked revenue" (order placed) | "Recognized revenue" (GAAP) | Create BOTH metrics with clear labels |
| **Customer Definition** | "Anyone who ever bought" | "Active in last 90 days" | Create lifecycle segments |
| **Real-time vs. Batch** | "I need it now" | "Daily is fine" | Tiered SLAs by use case |
| **Data Granularity** | "I need individual transactions" | "I need aggregates only" | Build detailed model; create aggregate marts |
| **Historical Data** | "Keep everything forever" | "Delete after 2 years (GDPR)" | Tiered retention: raw 7 years, PII 2 years |

### The Resolution Framework

```
1. DOCUMENT both positions exactly
2. IDENTIFY the business impact of each choice
3. PROPOSE a hybrid or tiered solution
4. ESCALATE to executive sponsor if deadlock
5. DECISION is recorded in governance registry
6. BOTH parties are notified of the decision
```

---

## 6. ModelBox AI Integration Opportunities

### Feature 1: Business Requirement Translator

**Input:** Natural language business requirement.

**Auto-Output:**
```yaml
business_requirement: |
  "I want to see which marketing campaigns are driving 
   the most revenue, compared to last year."

translation:
  metrics:
    - name: attributed_revenue
      definition: SUM(order_total) WHERE attribution_source = campaign_id

    - name: attributed_revenue_yoy
      definition: (current_year - prior_year) / prior_year

  dimensions:
    - campaign_name
    - channel
    - date_range
    - customer_segment

  grain: campaign_day

  sources:
    - fct_orders
    - dim_campaigns
    - dim_customers

  suggested_model: mart_campaign_performance

  trade_offs:
    - attribution_model: first_touch (simple) vs. multi_touch (complex)
    - refresh_frequency: daily (recommended) vs. real-time (expensive)

  questions_for_stakeholder:
    - "Is first-touch attribution acceptable for v1?"
    - "Should revenue be gross or net of returns?"
    - "What is the minimum viable date range?"
```

### Feature 2: Workshop Output Auto-Generation

**From a whiteboard photo or meeting notes:**
```
Input: Photo of whiteboard with entities and relationships
Output: 
  - Auto-generated ERD
  - Auto-generated business glossary entries
  - Auto-generated stakeholder validation document
  - Auto-generated dbt model stubs
```

### Feature 3: Stakeholder Communication Templates

**Auto-generated based on model complexity:**
```
Model: fct_orders (Tier 1, 15 columns, 5 downstream consumers)
→ Generate: Executive summary (1 paragraph)
→ Generate: Technical specification (for engineers)
→ Generate: Business user guide (for analysts)
→ Generate: On-call runbook (for incident response)
```

---

# PART III: CLOUD PLATFORM & INFRASTRUCTURE
## Increasingly Required (~42% of Roles, Growing Fast)

---

## 1. Cloud Data Platforms: The 2026 Landscape

### The Big Three + Databricks

| Platform | Strength | Best For | Pricing Model |
|----------|----------|----------|---------------|
| **Snowflake** | Separation of compute/storage, ease of use | General analytics, dbt-native teams | Credit-based, pay-per-query |
| **Google BigQuery** | Serverless, ML integration, cost controls | GCP-native, ML-heavy workloads | On-demand or flat-rate slots |
| **AWS Redshift** | Deep AWS integration, RA3 nodes | AWS-native, traditional DW workloads | Node-based or serverless |
| **Databricks** | Lakehouse, Spark, ML, Delta Lake | Streaming, ML, data science | DBU-based |
| **Azure Synapse** | Tight Microsoft integration, SQL Server familiarity | Microsoft shops, enterprise | DTU-based or serverless |

### Platform Selection Criteria for Modelers

```
┌─────────────────────────────────────────────────────────────┐
│  PLATFORM SELECTION DECISION TREE                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Q1: What is your primary cloud provider?                   │
│      AWS → Redshift or Databricks on AWS                    │
│      GCP → BigQuery or Databricks on GCP                    │
│      Azure → Synapse or Databricks on Azure                 │
│      Multi-cloud → Snowflake or Databricks                  │
│                                                             │
│  Q2: What is your dominant workload?                        │
│      SQL analytics → Snowflake or BigQuery                  │
│      Spark/ML → Databricks                                  │
│      Mixed → Databricks (lakehouse) or Snowflake            │
│                                                             │
│  Q3: What is your team's skill set?                         │
│      SQL-only → Snowflake or BigQuery                       │
│      Python + SQL → Databricks or Snowflake               │
│      Spark experts → Databricks                             │
│                                                             │
│  Q4: What is your data volume?                              │
│      < 10 TB → Any platform                                 │
│      10–100 TB → Snowflake, BigQuery, Databricks            │
│      > 100 TB → Databricks or BigQuery                      │
│                                                             │
│  Q5: What is your budget sensitivity?                       │
│      High (need cost controls) → BigQuery (flat-rate)      │
│      Medium → Snowflake (credit monitoring)                   │
│      Low → Any platform                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Storage Architectures

### Data Lake vs. Data Warehouse vs. Lakehouse

| Architecture | Data Types | Schema | Use Case | Modeling Approach |
|-------------|-----------|--------|----------|-----------------|
| **Data Lake** | Raw files (JSON, CSV, Parquet) | Schema-on-read | Storage, exploration | Minimal modeling; land everything |
| **Data Warehouse** | Structured tables | Schema-on-write | SQL analytics, BI | Kimball star schema, 3NF |
| **Lakehouse** | Structured + semi-structured | Schema enforcement + flexibility | Unified analytics, ML | Medallion architecture (bronze/silver/gold) |

### The Medallion Architecture (Databricks / Modern Lakehouse)

```
┌─────────────────────────────────────────────────────────────┐
│                    MEDALLION ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  BRONZE (Raw)                                               │
│  ├─ Ingested as-is from source                              │
│  ├─ Append-only, immutable                                  │
│  ├─ Schema: inferred or minimal                             │
│  └─ Quality: none (raw data)                                │
│                                                             │
│  SILVER (Cleaned)                                           │
│  ├─ Deduplicated, typed, validated                          │
│  ├─ Business rules applied                                  │
│  ├─ Schema: enforced, documented                            │
│  └─ Quality: tested, monitored                              │
│                                                             │
│  GOLD (Aggregated)                                          │
│  ├─ Business-ready aggregates                                 │
│  ├─ Dimensional models, metrics                             │
│  ├─ Schema: optimized for consumption                         │
│  └─ Quality: certified, SLA-backed                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Modeling responsibilities by layer:**
- **Bronze:** Minimal — just land the data, preserve source schema
- **Silver:** Moderate — clean, type, validate, deduplicate, basic relationships
- **Gold:** Heavy — dimensional modeling, aggregations, metrics, semantic layers

---

## 3. Infrastructure as Code for Data

### Terraform for Data Infrastructure

```hcl
# terraform/snowflake_warehouse.tf
resource "snowflake_warehouse" "analytics" {
  name           = "ANALYTICS_WH"
  warehouse_size = "MEDIUM"
  auto_suspend   = 60
  auto_resume    = true

  # Cost control
  resource_monitor = snowflake_resource_monitor.analytics.name
}

resource "snowflake_database" "analytics" {
  name    = "ANALYTICS_DB"
  comment = "Primary analytics database"
}

resource "snowflake_schema" "marts" {
  database = snowflake_database.analytics.name
  name     = "MARTS"
  comment  = "Business-ready data marts"
}

resource "snowflake_table" "fct_orders" {
  database = snowflake_database.analytics.name
  schema   = snowflake_schema.marts.name
  name     = "FCT_ORDERS"

  column {
    name = "ORDER_ID"
    type = "VARCHAR(36)"
  }

  column {
    name = "CUSTOMER_ID"
    type = "VARCHAR(36)"
  }

  column {
    name = "ORDER_TOTAL"
    type = "DECIMAL(18,2)"
  }

  column {
    name = "ORDERED_AT"
    type = "TIMESTAMP"
  }
}
```

### Why Modelers Need to Understand Infrastructure

| Scenario | Infrastructure Knowledge Required |
|----------|----------------------------------|
| "My query is too slow" | Warehouse sizing, clustering, partitioning |
| "Our costs are exploding" | Resource monitors, auto-suspend, query optimization |
| "We need a dev environment" | Zero-copy cloning, Terraform workspaces |
| "We need to scale to 10x data" | Elastic scaling, multi-cluster warehouses |
| "We need disaster recovery" | Cross-region replication, time travel, backups |

---

## 4. Security & Access Control

### Role-Based Access Control (RBAC) for Data Models

```sql
-- Snowflake RBAC example
-- 1. Create roles
CREATE ROLE data_engineer;
CREATE ROLE analytics_engineer;
CREATE ROLE bi_analyst;
CREATE ROLE data_consumer;

-- 2. Grant privileges
GRANT USAGE ON WAREHOUSE analytics_wh TO ROLE data_engineer;
GRANT USAGE ON DATABASE analytics_db TO ROLE analytics_engineer;
GRANT USAGE ON SCHEMA analytics_db.marts TO ROLE bi_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics_db.marts TO ROLE data_consumer;

-- 3. Row-level security
CREATE ROW ACCESS POLICY customer_region_policy AS (region VARCHAR) RETURNS BOOLEAN ->
  CASE
    WHEN CURRENT_ROLE() = 'ADMIN' THEN TRUE
    WHEN CURRENT_ROLE() = 'SALES_MANAGER' THEN region = CURRENT_REGION()
    ELSE FALSE
  END;

ALTER TABLE fct_orders ADD ROW ACCESS POLICY customer_region_policy ON (region);
```

### Column-Level Security & Masking

```sql
-- Dynamic data masking
CREATE MASKING POLICY email_mask AS (val VARCHAR) RETURNS VARCHAR ->
  CASE
    WHEN CURRENT_ROLE() IN ('DATA_ADMIN', 'COMPLIANCE') THEN val
    ELSE REGEXP_REPLACE(val, '.+@', '***@')
  END;

ALTER TABLE dim_customers ALTER COLUMN email SET MASKING POLICY email_mask;
```

---

## 5. Cost Management for Modelers

### Cost Optimization Strategies

| Strategy | How | Impact |
|----------|-----|--------|
| **Auto-suspend** | Pause warehouse after idle period | 30–50% cost reduction |
| **Right-sizing** | Match warehouse size to query complexity | 20–40% cost reduction |
| **Query optimization** | Reduce data scanned (partitioning, pruning) | 50–80% cost reduction |
| **Materialized views** | Pre-compute expensive aggregations | 40–60% cost reduction |
| **Storage tiering** | Move old data to cold storage | 60–90% storage cost reduction |
| **Resource monitors** | Set spend limits and alerts | Prevents runaway costs |

### Cost Attribution by Model

```sql
-- Example: Track query cost by dbt model
SELECT 
  query_tag,  -- Set by dbt to model name
  warehouse_name,
  SUM(credits_used) as total_credits,
  SUM(total_elapsed_time/1000) as total_seconds,
  COUNT(*) as query_count
FROM snowflake.account_usage.warehouse_metering_history
WHERE start_time >= CURRENT_DATE - 30
GROUP BY 1, 2
ORDER BY total_credits DESC;
```

---

## 6. ModelBox AI Integration Opportunities

### Feature 1: Platform-Native DDL Generation

**From one ModelBox schema, generate platform-specific DDL:**
```
ModelBox Schema ──┬──→ Snowflake DDL (with clustering, partitioning)
                  ├──→ BigQuery DDL (with partitioning, clustering)
                  ├──→ Databricks Delta DDL (with liquid clustering)
                  ├──→ Redshift DDL (with DISTKEY, SORTKEY)
                  └──→ PostgreSQL DDL (with indexes, constraints)
```

### Feature 2: Cost Estimation

**Before deploying a model, estimate:**
- Storage cost (based on row count, column types)
- Compute cost (based on query patterns, warehouse size)
- Optimization recommendations (partitioning, clustering, materialization)

### Feature 3: Infrastructure-as-Code Export

**Auto-generate Terraform / CloudFormation / Pulumi:**
```hcl
# Auto-generated from ModelBox schema
resource "snowflake_table" "fct_orders" {
  # ... DDL from schema design
}

resource "snowflake_warehouse" "analytics" {
  # ... Sized based on estimated query complexity
}
```

### Feature 4: Security Policy Recommendations

**From PII classification in ModelBox:**
```
Auto-detect: column "customer_email" = PII
Auto-generate: masking policy, RBAC restrictions
Auto-generate: GDPR retention policy
Auto-generate: audit logging configuration
```

---

## Appendix: The Complete Secondary Responsibility Stack

| Rank | Responsibility | Frequency | Core Skill | ModelBox Relevance |
|------|---------------|-----------|------------|-------------------|
| 1 | SQL / Database Development | ~78% | Universal | DDL generation, query optimization |
| 2 | Data Engineering / ETL-ELT | ~72% | dbt, pipelines, orchestration | Auto-generate dbt models, pipeline scaffolding |
| 3 | Stakeholder / Business Analysis | ~68% | Requirements, communication | Requirement translator, workshop tools |
| 4 | Documentation / Metadata | ~65% | Data dictionaries, glossaries | Auto-generate docs, business glossary |
| 5 | Data Governance | ~58% | Standards, lineage, catalog | Governance metadata, contract export |
| 6 | Data Quality | ~55% | Testing, validation, observability | Auto-generate tests, synthetic data |
| 7 | BI / Reporting | ~50% | Dashboards, semantic layers | Semantic layer export, BI integration |
| 8 | Data Architecture / Platform | ~48% | Cloud, storage, infrastructure | Platform-native DDL, cost estimation |
| 9 | Performance Tuning | ~45% | Indexing, partitioning, query optimization | Optimization recommendations |
| 10 | Cloud / Platform Engineering | ~42% | AWS/Azure/GCP, infrastructure | IaC export, security policies |

---

*Document compiled for ModelBox AI product strategy and educational course development. Based on 2026 market research of 43+ data modeling job postings.*
