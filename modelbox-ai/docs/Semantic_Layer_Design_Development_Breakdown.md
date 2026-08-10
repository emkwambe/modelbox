# Semantic Layer Design & Development: A Comprehensive Breakdown
## For ModelBox AI Product Strategy & Course Development

**Context:** Based on deep research of 43+ data modeling job postings (July–August 2026), semantic layer design emerged as the fastest-growing secondary responsibility bundled with data modeling. It is now explicitly required in ~45% of analytics-facing roles and is the #1 breakout skill for 2026.

---

## Table of Contents
1. What Is a Semantic Layer?
2. Why It Matters (The Business Case)
3. Architecture & Core Components
4. Semantic Layer Design Principles
5. The Design Process (Step-by-Step)
6. Development Workflows
7. Tool Landscape (2026)
8. Integration with Data Modeling
9. Governance, Testing & Maintenance
10. Anti-Patterns & Common Failures
11. Practical Examples
12. ModelBox AI Integration Opportunities
13. Course Module: Semantic Layer Mastery

---

## 1. What Is a Semantic Layer?

A **semantic layer** is an abstraction tier that sits between raw data (tables, views, files) and data consumers (analysts, BI tools, AI agents, applications). It translates technical database structures into **business-meaningful concepts** — metrics, dimensions, and relationships — ensuring consistent, governed, and reusable definitions across an organization.

### The Stack Position

```
┌─────────────────────────────────────────┐
│  CONSUMPTION LAYER                      │
│  BI Tools (Tableau, Power BI, Looker)   │
│  AI Agents (RAG, Chatbots)              │
│  Applications (Embedded Analytics)      │
│  APIs (REST, GraphQL)                   │
├─────────────────────────────────────────┤
│  SEMANTIC LAYER  ←── YOU ARE HERE       │
│  Metrics, Dimensions, Filters,          │
│  Business Logic, Access Control         │
├─────────────────────────────────────────┤
│  TRANSFORMATION LAYER                   │
│  dbt Models, SQL Views, Spark Jobs      │
├─────────────────────────────────────────┤
│  STORAGE LAYER                          │
│  Snowflake, BigQuery, Databricks        │
│  Data Lake, Data Warehouse              │
├─────────────────────────────────────────┤
│  INGESTION LAYER                        │
│  Fivetran, Airbyte, Kafka, APIs         │
└─────────────────────────────────────────┘
```

### Key Distinction: Semantic Layer vs. Data Model

| Dimension | Data Model | Semantic Layer |
|-----------|-----------|----------------|
| **Focus** | Structure (tables, columns, keys) | Meaning (metrics, dimensions, business rules) |
| **Audience** | Engineers, DBAs | Analysts, business users, AI agents |
| **Language** | Technical (SQL types, constraints) | Business ("Active Customers," "Revenue LTM") |
| **Granularity** | Row-level | Aggregated, filtered, computed |
| **Governance** | Schema governance | Business logic governance |
| **Tooling** | dbt models, ERDs | MetricFlow, Cube, LookML, AtScale |

**The semantic layer is the "business API" for your data.**

---

## 2. Why It Matters (The Business Case)

### The Problem It Solves

Without a semantic layer, every analyst defines metrics independently:

```
Analyst A:  "Revenue = SUM(order_total) WHERE status = 'completed'"
Analyst B:  "Revenue = SUM(order_total) WHERE status IN ('completed','shipped')"
Analyst C:  "Revenue = SUM(payment_amount) WHERE refunded = FALSE"
CEO sees 3 different "Revenue" numbers in 3 dashboards → Crisis meeting
```

With a semantic layer:

```
Metric Definition (ONE source of truth):
  "Revenue" = SUM(order_total) 
              WHERE status = 'completed' 
              AND order_date <= reporting_date
              AND currency = 'USD'

All analysts, dashboards, and AI agents consume the SAME definition.
```

### Quantified Impact (from 2026 research)

| Metric | Without Semantic Layer | With Semantic Layer |
|--------|----------------------|---------------------|
| Metric consistency | 30–40% of metrics have conflicting definitions | 100% consistency |
| Time to answer business question | 2–4 days (find + validate + query) | Minutes (self-serve) |
| Onboarding new analyst | 3–6 months to understand all business logic | 2–4 weeks |
| Dashboard maintenance | High (every metric change breaks N dashboards) | Low (change once, propagate everywhere) |
| Data governance audit | Painful (reverse-engineer every dashboard) | Trivial (single source of truth) |

### Why It's Exploding in 2026

1. **AI agents need structured context** — LLMs can't reason about raw tables; they need business definitions.
2. **dbt popularized "models as code"** — semantic layers are the natural next step.
3. **Self-serve analytics mandate** — Business users demand direct access without SQL.
4. **Data mesh / domain ownership** — Each domain publishes its own semantic API.
5. **Headless BI** — Decoupling metrics from visualization tools (use any BI tool, same metrics).

---

## 3. Architecture & Core Components

### The Semantic Layer Anatomy

```
┌─────────────────────────────────────────────────────────────┐
│                    SEMANTIC LAYER                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   METRICS   │  │ DIMENSIONS  │  │   ENTITIES /        │  │
│  │             │  │             │  │   SEMANTIC MODELS   │  │
│  │ • Revenue   │  │ • Date      │  │                     │  │
│  │ • Churn Rate│  │ • Customer  │  │ • Orders            │  │
│  │ • LTV       │  │ • Product   │  │ • Customers         │  │
│  │ • NPS       │  │ • Region    │  │ • Products          │  │
│  │ • CAC       │  │ • Status    │  │ • Sessions          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   FILTERS   │  │  CALCULATED │  │   RELATIONSHIPS     │  │
│  │             │  │   FIELDS    │  │                     │  │
│  │ • Time      │  │             │  │ • Orders → Customers│  │
│  │ • Segment   │  │ • YoY Growth│  │ • Orders → Products │  │
│  │ • Status    │  │ • Running   │  │ • Sessions → Users  │  │
│  │ • Region    │  │   Total     │  │ • Events → Sessions │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │              ACCESS CONTROL & GOVERNANCE              │    │
│  │  • Row-level security (RLS)                          │    │
│  │  • Column-level security (CLS)                       │    │
│  │  • Data masking (PII, sensitive fields)              │    │
│  │  • Audit logging                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Component Deep-Dive

#### A. Metrics (The Heart of the Semantic Layer)

A metric is a **business calculation with guaranteed semantics**.

```yaml
# Example: dbt MetricFlow YAML
metric:
  name: revenue
  description: Total recognized revenue from completed orders
  type: simple
  type_params:
    measure: order_total
  filter: |
    {{ Dimension('order__status') }} = 'completed'
    AND {{ Dimension('order__order_date') }} <= {{ Metric('reporting_date', group_by=['order__order_date']) }}

  # Governance
  owners:
    - name: finance_team
      email: finance@company.com

  # Certification
  tier: certified

  # Lineage
  depends_on:
    - ref('fct_orders')
    - ref('dim_date')
```

**Metric Types:**

| Type | Description | Example |
|------|-------------|---------|
| **Simple** | Direct aggregation on a measure | `SUM(revenue)` |
| **Ratio** | Division of two metrics | `Churn Rate = Churned / Total` |
| **Derived** | Calculation from other metrics | `LTV = ARPU / Churn Rate` |
| **Cumulative** | Running total over time | `Cumulative Revenue` |
| **Conversion** | Funnel step ratio | `Checkout Conversion = Purchases / Carts` |

#### B. Dimensions (The "By What?")

Dimensions provide the context for metrics. They answer: "Revenue **by what?**"

```yaml
dimension:
  name: customer_segment
  type: categorical
  description: Marketing-defined customer lifecycle segment

  # Hierarchical (drill-down)
  hierarchy:
    - region
    - country
    - city
    - store

  # Slowly Changing Dimension (SCD) handling
  scd_type: 2  # Track history

  # Values with business definitions
  allowed_values:
    - value: new
      description: First purchase within 30 days
    - value: active
      description: Purchase within last 90 days
    - value: at_risk
      description: No purchase in 90-180 days
    - value: churned
      description: No purchase in 180+ days
```

**Dimension Types:**

| Type | Purpose | Example |
|------|---------|---------|
| **Categorical** | Discrete groupings | Product category, region, status |
| **Temporal** | Time-based analysis | Order date, fiscal quarter, cohort month |
| **Numerical (Bucketed)** | Ranges | Age group, spend tier |
| **Degenerate** | Transaction attributes | Order number, invoice ID |
| **Junk** | Miscellaneous flags | Is_holiday, is_promotion_active |

#### C. Entities / Semantic Models

Entities group related metrics and dimensions into business concepts.

```yaml
semantic_model:
  name: orders
  description: All customer orders with line-item detail

  # The underlying data model reference
  model: ref('fct_orders')

  # Primary entity (grain)
  primary_entity: order_id

  # Measures (aggregatable)
  measures:
    - name: order_total
      agg: sum
      expr: total_amount
    - name: order_count
      agg: count
      expr: order_id
    - name: avg_order_value
      agg: average
      expr: total_amount

  # Dimensions (groupable)
  dimensions:
    - name: order_date
      type: time
      expr: ordered_at
    - name: status
      type: categorical
      expr: order_status
    - name: customer_segment
      type: categorical
      expr: customer_segment  # Joined from dim_customer

  # Relationships to other entities
  relationships:
    - to: semantic_model('customers')
      join_type: left
      join_on: customer_id
    - to: semantic_model('products')
      join_type: left
      join_on: product_id
```

#### D. Calculated Fields

Business logic that doesn't fit simple aggregation:

```yaml
calculated_field:
  name: revenue_per_session
  description: Revenue generated per website session
  expr: |
    CASE 
      WHEN {{ Metric('session_count') }} = 0 THEN 0
      ELSE {{ Metric('revenue') }} / {{ Metric('session_count') }}
    END

  # Data type for downstream tools
  data_type: decimal(18,2)

  # Formatting hint for BI tools
  format: currency
```

#### E. Access Control & Governance

```yaml
access_control:
  # Row-level security
  rls_policies:
    - name: regional_access
      description: Users can only see data for their assigned regions
      condition: |
        {{ Dimension('region') }} IN (
          SELECT region FROM user_permissions 
          WHERE user_id = {{ current_user_id() }}
        )

  # Column-level security
  cls_policies:
    - name: pii_masking
      columns: [email, phone, ssn]
      mask: '***-***-****'
      unmask_for_roles: [data_admin, compliance_officer]

  # Audit
  audit:
    log_all_queries: true
    retention_days: 90
```

---

## 4. Semantic Layer Design Principles

### The 10 Principles of Semantic Layer Design

#### 1. **Business-First Naming**
Use business language, not technical language.

❌ Bad: `fct_orders.order_total_amt_usd`  
✅ Good: `Revenue` (with currency context in definition)

#### 2. **Single Source of Truth (SSOT)**
Every metric is defined exactly once. No duplicates, no variations.

```
❌ Bad:
  metric: revenue_finance
  metric: revenue_sales
  metric: revenue_ga4

✅ Good:
  metric: revenue
    - Finance owns the definition
    - All teams consume the SAME metric
    - If definitions differ, create explicit variants:
      metric: revenue_gaap (finance definition)
      metric: revenue_booked (sales definition)
```

#### 3. **Grain Integrity**
Every semantic model has ONE grain. Never mix grains.

```
❌ Bad: "Orders" model with both order-level and line-item-level measures

✅ Good:
  Semantic Model: orders (grain: order_id)
    - order_total
    - order_count
    - avg_order_value

  Semantic Model: order_line_items (grain: line_item_id)
    - line_item_revenue
    - line_item_quantity
    - product_mix_percentage
```

#### 4. **Dimensional Conformity**
Dimensions shared across fact tables must be identical.

```
✅ Good:
  dim_date is used by:
    - fct_orders (order_date)
    - fct_sessions (session_date)
    - fct_support_tickets (ticket_date)

  All use the SAME dim_date with the SAME attributes.
```

#### 5. **Metric Composability**
Metrics should build on other metrics, not duplicate logic.

```yaml
# ✅ Good: Composable
metric:
  name: ltv
  expr: {{ Metric('arpu') }} / {{ Metric('churn_rate') }}

# ❌ Bad: Duplicated logic
metric:
  name: ltv_bad
  expr: (SUM(revenue) / COUNT(DISTINCT customer_id)) / (COUNT(DISTINCT churned_customers) / COUNT(DISTINCT customer_id))
```

#### 6. **Explicit Time Intelligence**
Time is special. Handle it explicitly, not implicitly.

```yaml
# ✅ Good: Time is a first-class citizen
dimension:
  name: order_date
  type: time

  # Auto-generated time dimensions
  time_granularities: [day, week, month, quarter, year, fiscal_quarter]

  # Relative date filters
  relative_filters:
    - name: last_30_days
      expr: order_date >= CURRENT_DATE - 30
    - name: ytd
      expr: order_date >= DATE_TRUNC('year', CURRENT_DATE)
```

#### 7. **Governance by Design**
Every metric has an owner, a tier, and a lifecycle.

```yaml
metric:
  name: revenue
  owner: finance_team@company.com
  tier: certified        # vs. experimental, deprecated
  review_date: 2026-12-01
  sla: 99.9%             # Uptime expectation
```

#### 8. **Consumer-Agnostic**
The semantic layer should serve ANY consumer: BI tool, API, AI agent, spreadsheet.

```
Same semantic definition → Multiple outputs:
  - Tableau: Drag-and-drop metric
  - Power BI: DAX measure import
  - API: REST endpoint /metrics/revenue?dimensions=region,date
  - AI Agent: Structured context for reasoning
  - Excel: Live connection
```

#### 9. **Versioned & Tested**
Semantic definitions are code. Use Git, CI/CD, and automated testing.

```yaml
# dbt tests on semantic layer
semantic_tests:
  - name: revenue_non_negative
    metric: revenue
    condition: revenue >= 0

  - name: revenue_matches_source
    metric: revenue
    compare_to: source('raw', 'orders')
    tolerance: 0.01  # 1% variance allowed

  - name: grain_integrity
    model: orders
    unique_columns: [order_id]
```

#### 10. **Progressive Disclosure**
Expose complexity gradually. Business users see simple metrics; analysts can drill into logic.

```
Business User sees: "Revenue = $1.2M"
  ↓ Click "Show Definition"
Analyst sees: "SUM(order_total) WHERE status = 'completed'"
  ↓ Click "Show SQL"
Engineer sees: Full compiled SQL with joins, filters, optimizations
```

---

## 5. The Design Process (Step-by-Step)

### Phase 1: Discovery & Requirements (Week 1)

**Stakeholder Interviews:**
- Who will consume this semantic layer? (BI analysts, business users, AI agents, APIs?)
- What are the top 10 questions they ask repeatedly?
- What metrics currently have conflicting definitions?
- What dimensions do they slice by most often?

**Audit Existing Definitions:**
```
Inventory all "Revenue" definitions across:
  - Dashboards (Tableau, Power BI, Looker)
  - Spreadsheets
  - Ad-hoc SQL queries
  - Reports
  - AI agent prompts

Document conflicts and prioritize reconciliation.
```

**Output:** Semantic Layer Requirements Document (SLRD)

### Phase 2: Conceptual Design (Week 2)

**Identify Core Business Entities:**
```
For an e-commerce company:
  Core Entities: Orders, Customers, Products, Sessions, Inventory

For a SaaS company:
  Core Entities: Subscriptions, Users, Events, Features, Accounts
```

**Define the Metric Catalog:**
```
Metric: Revenue
  - Owner: Finance
  - Definition: SUM(order_total) WHERE status = 'completed'
  - Dimensions: Date, Region, Product, Customer Segment
  - Variants: GAAP Revenue, Booked Revenue, Recognized Revenue

Metric: Active Users
  - Owner: Product
  - Definition: COUNT(DISTINCT user_id) WHERE last_activity_date >= CURRENT_DATE - 30
  - Dimensions: Date, Plan, Region, Acquisition Channel
```

**Map to Data Model:**
```
Semantic Model "orders" → refs dbt model fct_orders
Semantic Model "customers" → refs dbt model dim_customers
Relationship: orders.customer_id → customers.customer_id
```

**Output:** Semantic Layer Design Document (SLDD) with ERD

### Phase 3: Logical Design (Week 3)

**Define Semantic Models in YAML:**
```yaml
# models/semantic_layer/_semantic_models.yml
semantic_models:
  - name: orders
    model: ref('fct_orders')
    primary_entity: order_id
    measures:
      - name: order_total
        agg: sum
        expr: total_amount
      - name: order_count
        agg: count_distinct
        expr: order_id
    dimensions:
      - name: order_date
        type: time
        expr: ordered_at
      - name: status
        type: categorical
        expr: order_status
    relationships:
      - to: ref('dim_customers')
        join_type: left
        join_on: customer_id
```

**Define Metrics:**
```yaml
# models/semantic_layer/_metrics.yml
metrics:
  - name: revenue
    description: Total recognized revenue
    type: simple
    type_params:
      measure: order_total
    filter: |
      {{ Dimension('orders__status') }} = 'completed'

  - name: revenue_yoy_growth
    description: Year-over-year revenue growth
    type: derived
    type_params:
      expr: ({{ Metric('revenue', grain='month') }} - {{ Metric('revenue', grain='month', offset=12) }}) / {{ Metric('revenue', grain='month', offset=12) }}
```

**Output:** Version-controlled YAML files in Git

### Phase 4: Physical Implementation (Week 4)

**Compile & Deploy:**
```bash
# dbt compile generates the semantic layer
dbt compile

# Deploy to semantic layer engine
dbt sl serve  # MetricFlow
# OR
cube deploy   # Cube.js
# OR
looker deploy # LookML
```

**Connect Consumers:**
```
Tableau → Semantic Layer API
Power BI → Import semantic measures
Looker → Native LookML
Custom App → REST API / GraphQL
AI Agent → Structured context endpoint
```

### Phase 5: Governance & Iteration (Ongoing)

**Monitoring:**
```
- Query performance (slow metrics?)
- Usage analytics (most/least used metrics)
- Definition drift (are dashboards bypassing the semantic layer?)
- Error rates (broken relationships, missing dimensions)
```

**Iteration Cycle:**
```
1. Business requests new metric
2. Semantic layer team evaluates against existing catalog
3. Design in YAML, review via PR
4. Automated tests validate logic
5. Deploy, announce, document
6. Monitor adoption and accuracy
```

---

## 6. Development Workflows

### Workflow A: The dbt + MetricFlow Stack (Most Common in 2026)

```
┌─────────────────────────────────────────────────────────────┐
│  DEVELOPER WORKFLOW                                         │
├─────────────────────────────────────────────────────────────┤
│  1. Define in YAML                                          │
│     models/semantic_layer/_semantic_models.yml              │
│     models/semantic_layer/_metrics.yml                      │
│                                                             │
│  2. Version Control (Git)                                   │
│     git add .                                               │
│     git commit -m "Add revenue_yoy metric"                  │
│     git push origin feature/revenue-metric                  │
│                                                             │
│  3. CI/CD Pipeline                                          │
│     ├─ dbt compile (validate YAML syntax)                   │
│     ├─ dbt test (run semantic tests)                        │
│     ├─ dbt docs generate (update documentation)             │
│     └─ PR review by semantic layer owner                    │
│                                                             │
│  4. Deploy to Production                                    │
│     dbt sl serve --environment production                   │
│                                                             │
│  5. Consumer Access                                         │
│     Tableau → dbt Semantic Layer JDBC connection            │
│     Power BI → dbt Semantic Layer REST API                  │
│     Custom App → GraphQL endpoint                           │
│     AI Agent → Structured JSON context                      │
└─────────────────────────────────────────────────────────────┘
```

### Workflow B: The Cube.js Stack (API-First / Headless BI)

```javascript
// cube.js configuration
cube('Orders', {
  sql: `SELECT * FROM fct_orders`,

  measures: {
    revenue: {
      sql: 'order_total',
      type: 'sum',
      filters: [{ sql: `${CUBE}.status = 'completed'` }]
    },

    orderCount: {
      sql: 'order_id',
      type: 'countDistinct'
    },

    avgOrderValue: {
      sql: `${revenue} / ${orderCount}`,
      type: 'number'
    }
  },

  dimensions: {
    orderDate: {
      sql: 'ordered_at',
      type: 'time'
    },

    status: {
      sql: 'order_status',
      type: 'string'
    },

    customerSegment: {
      sql: 'customer_segment',
      type: 'string'
    }
  },

  segments: {
    completed: {
      sql: `${CUBE}.status = 'completed'`
    }
  },

  preAggregations: {
    revenueByMonth: {
      measures: [revenue],
      dimensions: [customerSegment],
      timeDimension: orderDate,
      granularity: 'month'
    }
  }
});
```

### Workflow C: The LookML Stack (Looker-Native)

```lookml
# views/orders.view.lkml
view: orders {
  sql_table_name: fct_orders ;;

  dimension: order_id {
    primary_key: yes
    type: number
    sql: ${TABLE}.order_id ;;
  }

  dimension_group: ordered {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    sql: ${TABLE}.ordered_at ;;
  }

  dimension: status {
    type: string
    sql: ${TABLE}.order_status ;;
  }

  measure: revenue {
    type: sum
    sql: ${TABLE}.order_total ;;
    filters: [status: "completed"]
    value_format_name: usd
    drill_fields: [order_id, customers.customer_name, products.product_name]
  }

  measure: order_count {
    type: count_distinct
    sql: ${order_id} ;;
  }

  measure: avg_order_value {
    type: number
    sql: ${revenue} / NULLIF(${order_count}, 0) ;;
    value_format_name: usd
  }
}

# explores/orders.explore.lkml
explore: orders {
  join: customers {
    type: left_outer
    sql_on: ${orders.customer_id} = ${customers.customer_id} ;;
    relationship: many_to_one
  }

  join: products {
    type: left_outer
    sql_on: ${orders.product_id} = ${products.product_id} ;;
    relationship: many_to_one
  }
}
```

---

## 7. Tool Landscape (2026)

### Semantic Layer Engines

| Tool | Vendor | Best For | Key Strength | Key Weakness |
|------|--------|----------|-------------|--------------|
| **dbt MetricFlow** | dbt Labs | dbt-native teams, analytics engineers | Tight dbt integration, open-source | Still maturing, limited BI connectors |
| **Cube** | Cube Dev | API-first, headless BI, embedded analytics | Fast API, pre-aggregations, multi-tenant | Requires JavaScript knowledge |
| **LookML** | Google (Looker) | Looker-native organizations | Mature, powerful, native visualization | Vendor lock-in, steep learning curve |
| **AtScale** | AtScale | Enterprise, multi-platform | Universal semantic layer (works with any BI) | Expensive, complex |
| **MetriQL** | Rakam | Lightweight, startup-friendly | Simple YAML, quick setup | Limited enterprise features |
| **Zenlytic** | Zenlytic | AI-native semantic layer | Natural language to metrics | Newer, smaller ecosystem |
| **GoodData** | GoodData | Embedded analytics in apps | Headless, API-first | Less popular in data community |
| **Supergrain** | Supergrain | Product analytics | Event-based semantic models | Niche use case |

### BI Tool + Semantic Layer Integration

| BI Tool | Native Semantic Layer | dbt MetricFlow | Cube | LookML |
|---------|:---------------------:|:--------------:|:----:|:------:|
| **Tableau** | ❌ (limited) | ✅ (via connector) | ✅ (via JDBC) | ❌ |
| **Power BI** | ✅ (Datasets) | ✅ (via connector) | ✅ (via REST) | ❌ |
| **Looker** | ✅ (LookML) | ✅ (via connector) | ✅ (via API) | ✅ (native) |
| **Metabase** | ❌ | ✅ (via API) | ✅ (via driver) | ❌ |
| **Superset** | ❌ | ✅ (via API) | ✅ (via driver) | ❌ |
| **Mode** | ❌ | ✅ | ✅ | ❌ |
| **Hex** | ❌ | ✅ | ✅ | ❌ |
| **Custom App** | N/A | ✅ (API) | ✅ (GraphQL/REST) | ✅ (API) |

---

## 8. Integration with Data Modeling

### The Handoff: Data Model → Semantic Layer

```
┌──────────────────────────────────────────────────────────────┐
│  DATA MODEL (dbt)                                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  fct_orders.sql                                        │  │
│  │  ├── order_id (PK)                                     │  │
│  │  ├── customer_id (FK)                                  │  │
│  │  ├── product_id (FK)                                   │  │
│  │  ├── ordered_at                                        │  │
│  │  ├── order_status                                      │  │
│  │  ├── total_amount                                      │  │
│  │  └── ...                                               │  │
│  └────────────────────────────────────────────────────────┘  │
│                           ↓                                  │
│  SEMANTIC LAYER (MetricFlow YAML)                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  semantic_model: orders                                │  │
│  │  ├── entity: order_id                                  │  │
│  │  ├── measures:                                         │  │
│  │  │   ├── revenue = SUM(total_amount)                   │  │
│  │  │   └── order_count = COUNT_DISTINCT(order_id)        │  │
│  │  ├── dimensions:                                       │  │
│  │  │   ├── order_date (time)                             │  │
│  │  │   └── status (categorical)                          │  │
│  │  └── relationships:                                    │  │
│  │      ├── customers (via customer_id)                   │  │
│  │      └── products (via product_id)                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                           ↓                                  │
│  CONSUMPTION (BI, API, AI)                                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  "Show me Revenue by Region, last quarter"             │  │
│  │  → Semantic layer compiles to SQL                      │  │
│  │  → Executes against warehouse                          │  │
│  │  → Returns consistent, governed result                 │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Modeling Patterns for Semantic Layers

#### Pattern 1: The Kimball Star Schema (Most Common)

```sql
-- fct_orders.sql (Fact Table)
SELECT
  o.order_id,
  o.customer_id,
  o.product_id,
  o.ordered_at,
  o.order_status,
  o.total_amount,
  o.discount_amount,
  o.shipping_cost,
  o.quantity
FROM raw_orders o

-- dim_customers.sql (Dimension Table)
SELECT
  c.customer_id,
  c.customer_name,
  c.email,
  c.segment,
  c.region,
  c.signup_date,
  c.lifecycle_stage
FROM raw_customers c

-- Semantic Model maps to these dbt models
```

**Semantic Layer Benefits:**
- Fact table measures are auto-aggregated
- Dimension attributes are auto-groupable
- Relationships are pre-defined (no analyst guesswork)

#### Pattern 2: One Big Table (OBT) for Simple Analytics

```sql
-- obt_orders_enriched.sql
SELECT
  o.*,
  c.customer_name,
  c.segment,
  c.region,
  p.product_name,
  p.category,
  p.brand
FROM fct_orders o
LEFT JOIN dim_customers c ON o.customer_id = c.customer_id
LEFT JOIN dim_products p ON o.product_id = p.product_id
```

**Semantic Layer Benefits:**
- Simpler for non-technical users
- No join complexity
- Faster for simple queries (pre-joined)
- Trade-off: Redundancy, larger storage

#### Pattern 3: Data Vault → Semantic Layer

```sql
-- hub_customer.sql, sat_customer_details.sql, link_customer_order.sql
-- (Data Vault raw vault)

-- Semantic layer sits ON TOP of Data Vault
-- Business vault (BV) models create business-friendly views
-- Semantic layer exposes metrics on BV

semantic_model: customers
  model: ref('bv_customer_enriched')  -- Business vault output
```

**Semantic Layer Benefits:**
- Handles complex many-to-many relationships
- Tracks history (SCD Type 2) natively
- Supports audit and lineage requirements

#### Pattern 4: Activity Schema (for Event Analytics)

```sql
-- fct_activity.sql
SELECT
  activity_id,
  ts,                    -- timestamp
  customer,              -- entity
  activity,              -- 'completed_order', 'viewed_page', 'sent_email'
  feature_1, feature_2,  -- activity-specific attributes
  revenue_impact         -- monetary impact
FROM all_activities
```

**Semantic Layer Benefits:**
- Unified event stream
- Metrics like "conversion rate" are derived from activity sequences
- Supports funnel analysis natively

---

## 9. Governance, Testing & Maintenance

### Governance Framework

```yaml
# governance/semantic_layer_policy.yml
semantic_layer_governance:

  # 1. Ownership
  ownership_model:
    - metric_tier: certified
      owner_required: true
      review_cycle: quarterly
      approvers: [data_architect, domain_owner]

    - metric_tier: experimental
      owner_required: true
      review_cycle: monthly
      approvers: [team_lead]

    - metric_tier: deprecated
      sunset_period: 90_days
      notification: all_consumers

  # 2. Naming Conventions
  naming_standards:
    metrics: snake_case, business_terms
    dimensions: snake_case, business_terms
    semantic_models: snake_case, entity_name

    forbidden_patterns:
      - "tmp_"
      - "test_"
      - "_v1", "_v2"  # Use Git for versioning

  # 3. Documentation Requirements
  documentation:
    metric: [description, business_owner, calculation_logic, caveats]
    dimension: [description, allowed_values, scd_type]
    semantic_model: [description, grain, primary_entity, relationships]

  # 4. Access Control
  access_control:
    default: read_only

    roles:
      - name: semantic_admin
        permissions: [create, update, delete, approve]
      - name: semantic_contributor
        permissions: [create, update]
      - name: semantic_consumer
        permissions: [read]

  # 5. Change Management
  change_management:
    breaking_changes:
      - rename_metric
      - remove_dimension
      - change_grain
      - change_calculation_logic
      approval_required: [data_architect, all_consumers]

    non_breaking_changes:
      - add_metric
      - add_dimension
      - update_description
      approval_required: [team_lead]
```

### Testing Strategy

```yaml
# tests/semantic_layer_tests.yml
semantic_tests:

  # 1. Accuracy Tests
  - name: revenue_matches_gl
    metric: revenue
    compare_to: source('finance', 'general_ledger')
    tolerance: 0.005  # 0.5%

  - name: customer_count_matches_crm
    metric: active_customers
    compare_to: source('salesforce', 'contact_count')
    tolerance: 0.02

  # 2. Integrity Tests
  - name: revenue_non_negative
    metric: revenue
    condition: revenue >= 0

  - name: conversion_rate_bounded
    metric: checkout_conversion
    condition: conversion_rate BETWEEN 0 AND 1

  # 3. Grain Tests
  - name: orders_grain_unique
    model: orders
    unique_columns: [order_id]

  - name: no_fan_out
    model: orders
    test: |
      COUNT(*) = COUNT(DISTINCT order_id)

  # 4. Relationship Tests
  - name: all_customers_have_segment
    model: customers
    condition: segment IS NOT NULL

  - name: orders_reference_valid_customers
    model: orders
    relationship:
      from: customer_id
      to: ref('dim_customers')
      field: customer_id

  # 5. Performance Tests
  - name: revenue_query_under_5s
    metric: revenue
    dimensions: [region, month]
    max_execution_time: 5  # seconds

  # 6. Drift Detection
  - name: no_unauthorized_dashboard_metrics
    check: |
      SELECT dashboard_id, metric_name 
      FROM dashboard_definitions
      WHERE metric_name NOT IN (SELECT name FROM semantic_metrics)
```

### Maintenance Checklist

**Weekly:**
- [ ] Review query performance logs (slow metrics?)
- [ ] Check for broken relationships (schema changes upstream?)
- [ ] Monitor consumer feedback (metric confusion reports?)

**Monthly:**
- [ ] Usage analytics review (unused metrics? popular new requests?)
- [ ] Definition drift audit (are dashboards bypassing semantic layer?)
- [ ] Documentation freshness check

**Quarterly:**
- [ ] Metric owner review meetings
- [ ] Tier re-assessment (experimental → certified? deprecated?)
- [ ] Consumer satisfaction survey
- [ ] Technology stack evaluation (new semantic layer features?)

---

## 10. Anti-Patterns & Common Failures

### Anti-Pattern 1: The "Everything Metric"

❌ **Bad:** One metric tries to handle all contexts.
```yaml
metric: revenue
  # Tries to be GAAP, cash, and booked simultaneously
  expr: CASE 
          WHEN context = 'finance' THEN gaap_revenue
          WHEN context = 'sales' THEN booked_revenue
          ELSE total_amount
        END
```

✅ **Good:** Explicit, separate metrics with clear ownership.
```yaml
metric: revenue_gaap
  owner: finance

metric: revenue_booked
  owner: sales

metric: revenue_total
  owner: analytics
  description: "Raw total before adjustments. Use specific variants for reporting."
```

### Anti-Pattern 2: The "Leaky Abstraction"

❌ **Bad:** Business users need to know underlying table names.
```
User query: "Show me fct_orders.total_amount by dim_date.month"
# User is exposed to raw table names
```

✅ **Good:** Pure business language.
```
User query: "Show me Revenue by Month"
# Semantic layer handles the mapping
```

### Anti-Pattern 3: The "Zombie Metric"

❌ **Bad:** Metrics that exist but no one owns or trusts them.
```yaml
metric: old_revenue_calculation
  owner: former_employee@company.com  # Bounced email
  tier: experimental
  last_reviewed: 2023-01-01
  # Still appears in dashboards, but no one knows if it's right
```

✅ **Good:** Explicit deprecation lifecycle.
```yaml
metric: old_revenue_calculation
  tier: deprecated
  sunset_date: 2026-09-01
  replacement: revenue
  notification_sent: 2026-06-01
```

### Anti-Pattern 4: The "Over-Engineered Dimension"

❌ **Bad:** Dimensions with 50+ attributes, most unused.
```yaml
dimension: customer
  attributes: [id, name, email, phone, address, city, state, zip, country, 
               signup_date, last_login, plan, mrr, arr, nps_score, 
               support_tickets, acquisition_channel, referral_source, 
               device_type, browser, os, ... 40 more]
```

✅ **Good:** Core dimensions + extended dimensions.
```yaml
dimension: customer
  core_attributes: [id, name, segment, region, lifecycle_stage]

dimension: customer_extended
  extends: customer
  additional_attributes: [mrr, arr, nps_score, acquisition_channel]
```

### Anti-Pattern 5: The "Silent Grain Change"

❌ **Bad:** Changing grain without notifying consumers.
```yaml
# v1: Grain = order_id
semantic_model: orders
  measures: [revenue, order_count]

# v2: Changed to grain = order_line_item_id (BREAKING!)
semantic_model: orders
  measures: [revenue, order_count, line_item_count]
  # order_count now means "line items" not "orders"
  # Dashboards break silently
```

✅ **Good:** New model, explicit migration.
```yaml
# Keep old model, create new one
semantic_model: orders          # Grain: order_id (unchanged)
semantic_model: order_line_items # Grain: line_item_id (NEW)

# Migration guide published
# Dashboards updated explicitly
```

### Anti-Pattern 6: The "BI Tool Silo"

❌ **Bad:** Each BI tool has its own semantic layer.
```
Tableau: "Revenue" = SUM(order_total) WHERE status = 'completed'
Power BI: "Revenue" = SUM(order_total) WHERE status = 'completed'
Looker: "Revenue" = SUM(order_total) WHERE status = 'completed'
# Three definitions, three places to maintain
```

✅ **Good:** One semantic layer, multiple BI tools.
```
Semantic Layer: "Revenue" = defined ONCE
Tableau → consumes semantic layer
Power BI → consumes semantic layer
Looker → consumes semantic layer
```

---

## 11. Practical Examples

### Example A: E-Commerce Semantic Layer

```yaml
# models/semantic_layer/ecommerce/_semantic_models.yml

semantic_models:
  - name: orders
    model: ref('fct_orders')
    primary_entity: order_id
    measures:
      - name: revenue
        description: Total recognized revenue from completed orders
        agg: sum
        expr: total_amount
        filter: order_status = 'completed'
      - name: orders
        description: Count of unique orders
        agg: count_distinct
        expr: order_id
      - name: aov
        description: Average order value
        agg: average
        expr: total_amount
      - name: items_sold
        description: Total quantity of items sold
        agg: sum
        expr: quantity
    dimensions:
      - name: order_date
        type: time
        expr: ordered_at
      - name: status
        type: categorical
        expr: order_status
      - name: channel
        type: categorical
        expr: acquisition_channel
    relationships:
      - to: ref('dim_customers')
        join_type: left
        join_on: customer_id
      - to: ref('dim_products')
        join_type: left
        join_on: product_id
      - to: ref('dim_date')
        join_type: left
        join_on: DATE(ordered_at) = date_day

  - name: customers
    model: ref('dim_customers')
    primary_entity: customer_id
    measures:
      - name: customer_count
        agg: count_distinct
        expr: customer_id
      - name: active_customers
        description: Customers with activity in last 30 days
        agg: count_distinct
        expr: customer_id
        filter: last_activity_date >= CURRENT_DATE - 30
    dimensions:
      - name: segment
        type: categorical
      - name: region
        type: categorical
      - name: lifecycle_stage
        type: categorical
      - name: signup_date
        type: time

metrics:
  - name: revenue
    type: simple
    type_params:
      measure: revenue

  - name: revenue_yoy_growth
    type: derived
    type_params:
      expr: |
        ({{ Metric('revenue', grain='month') }} - 
         {{ Metric('revenue', grain='month', offset=12) }}) / 
        {{ Metric('revenue', grain='month', offset=12) }}

  - name: conversion_rate
    type: ratio
    type_params:
      numerator: orders
      denominator: sessions  # from sessions semantic model

  - name: ltv
    type: derived
    type_params:
      expr: {{ Metric('revenue') }} / {{ Metric('churned_customers') }}
```

### Example B: SaaS Subscription Semantic Layer

```yaml
# models/semantic_layer/saas/_semantic_models.yml

semantic_models:
  - name: subscriptions
    model: ref('fct_subscriptions')
    primary_entity: subscription_id
    measures:
      - name: mrr
        description: Monthly Recurring Revenue
        agg: sum
        expr: monthly_amount
      - name: arr
        description: Annual Recurring Revenue
        agg: sum
        expr: monthly_amount * 12
      - name: subscription_count
        agg: count_distinct
        expr: subscription_id
      - name: churned_subscriptions
        agg: count_distinct
        expr: subscription_id
        filter: status = 'churned' AND churn_date BETWEEN {{ start_date }} AND {{ end_date }}
    dimensions:
      - name: plan
        type: categorical
      - name: billing_interval
        type: categorical
        expr: CASE WHEN monthly_amount * 12 = annual_amount THEN 'annual' ELSE 'monthly' END
      - name: start_date
        type: time
      - name: cohort_month
        type: time
        expr: DATE_TRUNC('month', start_date)

metrics:
  - name: mrr
    type: simple
    type_params:
      measure: mrr

  - name: net_mrr_growth
    type: derived
    type_params:
      expr: |
        {{ Metric('new_mrr') }} + 
        {{ Metric('expansion_mrr') }} - 
        {{ Metric('contraction_mrr') }} - 
        {{ Metric('churned_mrr') }}

  - name: logo_churn_rate
    type: ratio
    type_params:
      numerator: churned_subscriptions
      denominator: subscription_count

  - name: net_revenue_retention
    type: derived
    type_params:
      expr: |
        ({{ Metric('mrr', cohort='prior_year') }} + 
         {{ Metric('expansion_mrr') }} - 
         {{ Metric('churned_mrr') }}) / 
        {{ Metric('mrr', cohort='prior_year') }}
```

### Example C: AI Agent Context Export

```json
{
  "semantic_context": {
    "version": "1.0",
    "generated_at": "2026-08-10T12:00:00Z",
    "metrics": [
      {
        "name": "revenue",
        "description": "Total recognized revenue from completed orders",
        "calculation": "SUM(order_total) WHERE status = 'completed'",
        "dimensions": ["date", "region", "product", "customer_segment"],
        "owner": "finance@company.com",
        "tier": "certified",
        "caveats": [
          "Excludes refunds processed after reporting date",
          "Uses order_date, not payment_date"
        ]
      },
      {
        "name": "active_users",
        "description": "Users with activity in the last 30 days",
        "calculation": "COUNT(DISTINCT user_id) WHERE last_activity >= CURRENT_DATE - 30",
        "dimensions": ["date", "plan", "region", "acquisition_channel"],
        "owner": "product@company.com",
        "tier": "certified"
      }
    ],
    "relationships": {
      "orders": {
        "grain": "order_id",
        "related_to": ["customers", "products", "sessions"]
      },
      "customers": {
        "grain": "customer_id",
        "related_to": ["orders", "subscriptions", "support_tickets"]
      }
    },
    "common_queries": [
      {
        "question": "What was revenue last month?",
        "metric": "revenue",
        "filter": "date = last_month"
      },
      {
        "question": "How many active users do we have?",
        "metric": "active_users",
        "filter": "date = today"
      }
    ]
  }
}
```

---

## 12. ModelBox AI Integration Opportunities

### Feature 1: Auto-Generate Semantic Layer from Physical Model

**Input:** ModelBox AI generates a Kimball star schema.

**Auto-Output:**
```yaml
# Generated automatically from ModelBox schema
semantic_model: orders
  model: ref('fct_orders')  # Auto-mapped from ModelBox output
  primary_entity: order_id   # Auto-detected PK
  measures:
    - name: revenue          # Auto-detected numeric columns
      agg: sum
      expr: total_amount
  dimensions:
    - name: order_date       # Auto-detected timestamp columns
      type: time
      expr: ordered_at
  relationships:
    - to: ref('dim_customers')  # Auto-detected FK relationships
      join_type: left
      join_on: customer_id
```

**Value:** Eliminates the manual handoff from data modeler to analytics engineer.

### Feature 2: Semantic Layer Diff & Migration

**Input:** User changes a model in ModelBox (e.g., adds a new dimension).

**Auto-Output:**
```yaml
# ModelBox detects the change and generates:
semantic_migration:
  action: add_dimension
  model: orders
  dimension: 
    name: payment_method
    type: categorical

  impact_analysis:
    - metric: revenue
      impact: none  # Revenue doesn't depend on payment_method
    - metric: aov_by_payment_method
      impact: new_metric_possible
    - dashboard: "Sales Overview"
      impact: can_add_new_filter

  breaking_change: false
  consumer_notification: optional
```

**Value:** Prevents silent breaking changes in the semantic layer.

### Feature 3: Business Glossary Auto-Generation

**Input:** ModelBox schema with business requirements.

**Auto-Output:**
```yaml
business_glossary:
  term: Revenue
  definition: Total recognized revenue from completed orders
  calculation: SUM(order_total) WHERE status = 'completed'
  synonyms: [Sales, Gross Revenue, Bookings]
  owner: Finance Team
  related_metrics: [Net Revenue, GAAP Revenue]

  data_lineage:
    source: raw_orders
    transformations: [clean_orders, fct_orders]
    semantic_layer: revenue_metric
    consumers: [Tableau_Sales_Dashboard, PowerBI_Executive_Report, API_Revenue_Endpoint]
```

**Value:** Bridges the gap between technical models and business understanding.

### Feature 4: Multi-Format Export for Semantic Engines

**From one ModelBox schema, export to:**

```
┌─────────────────────────────────────────────────────────────┐
│  ModelBox AI Schema                                         │
│  (Kimball Star Schema)                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ dbt MetricFlow│   │   Cube.js     │   │   LookML      │
│   YAML        │   │   JavaScript  │   │   .lkml       │
└───────────────┘   └───────────────┘   └───────────────┘
        ↓                   ↓                   ↓
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ OpenDataContract│  │  GraphQL      │   │  AI Context   │
│   YAML        │   │   Schema      │   │   JSON        │
└───────────────┘   └───────────────┘   └───────────────┘
```

**Value:** One model, any semantic engine. Eliminates re-work.

### Feature 5: "Spot the Flaw" — Semantic Layer Edition

**Challenge:** Given a semantic layer definition, identify issues.

```yaml
# Flawed semantic layer (presented to student)
semantic_model: orders
  measures:
    - name: revenue
      agg: sum
      expr: total_amount
      # ❌ MISSING: filter for completed orders only
      # ❌ MISSING: owner
      # ❌ MISSING: description
    - name: customer_count
      agg: count_distinct
      expr: customer_id
      # ❌ ISSUE: This counts customers at order grain, 
      #           but model grain is order_id
      #           Should be in customers semantic model

  dimensions:
    - name: order_date
      type: time
      # ❌ MISSING: time_granularities
    - name: status
      type: categorical
      # ❌ MISSING: allowed_values documentation
```

**AI Tutor Response:**
```
"I see several issues in this semantic layer definition:

1. Revenue metric lacks a filter. Should it include cancelled orders? 
   In most businesses, revenue should only count 'completed' orders.

2. customer_count is in the wrong semantic model. Since the grain 
   of 'orders' is order_id, counting distinct customers here is valid 
   but misleading. Consider moving this to a 'customers' semantic model 
   with grain = customer_id.

3. No owner is assigned. Who is accountable if this metric is wrong?

4. order_date lacks time_granularities. Consumers won't know if they 
   can group by week, month, or quarter.

5. status dimension has no documented allowed_values. A new analyst 
   won't know if valid statuses are ['pending','completed','cancelled'] 
   or something else."
```

---

## 13. Course Module: Semantic Layer Mastery

### Module Outline (8-Week Course)

#### Week 1: Foundations
- What is a semantic layer and why it exists
- The modern data stack: where semantic layers fit
- Comparison: traditional BI semantic models vs. modern headless semantic layers
- **Lab:** Explore an existing semantic layer in dbt MetricFlow

#### Week 2: Metrics Design
- Metric taxonomy: simple, ratio, derived, cumulative, conversion
- Grain integrity and why it matters
- Time intelligence in metrics
- **Lab:** Design a metric catalog for an e-commerce business

#### Week 3: Dimensions & Entities
- Dimension types: categorical, temporal, numerical, degenerate
- Dimensional conformity across fact tables
- Slowly Changing Dimensions (SCD) in semantic layers
- Hierarchies and drill-down paths
- **Lab:** Build a dimensional model with conforming dimensions

#### Week 4: Semantic Layer Implementation (dbt MetricFlow)
- YAML syntax for semantic models and metrics
- dbt project structure for semantic layers
- CI/CD for semantic layers
- Testing semantic definitions
- **Lab:** Implement a semantic layer in dbt MetricFlow

#### Week 5: Alternative Engines (Cube, LookML)
- Cube.js: JavaScript-based semantic modeling
- LookML: Looker-native semantic layer
- AtScale: Enterprise universal semantic layer
- When to choose which engine
- **Lab:** Port a dbt semantic model to Cube.js

#### Week 6: Governance & Maintenance
- Ownership models and tiering (certified, experimental, deprecated)
- Change management for semantic layers
- Access control: RLS, CLS, data masking
- Documentation and business glossary
- **Lab:** Implement governance policies on a semantic layer

#### Week 7: Integration & Consumption
- Connecting BI tools to semantic layers
- Building APIs on semantic layers
- AI agent context provision
- Headless BI patterns
- **Lab:** Build a dashboard AND an API from the same semantic layer

#### Week 8: Capstone Project
- **Scenario:** A mid-size SaaS company has 3 BI tools, each with its own metric definitions. Revenue is defined 4 different ways. The CEO is frustrated.
- **Task:** Design, implement, and govern a unified semantic layer.
- **Deliverables:**
  - Semantic layer design document
  - Implemented YAML definitions
  - Governance policy
  - Migration plan from existing definitions
  - Stakeholder presentation

### Assessment Rubric

| Criteria | Weight | Excellent (A) | Good (B) | Needs Work (C) |
|----------|--------|--------------|----------|----------------|
| Metric Design | 20% | All metrics have correct grain, clear definitions, and appropriate types | Most metrics correct, minor grain issues | Significant grain or definition problems |
| Semantic Model Structure | 20% | Clean entity relationships, proper PK/FK, no fan-outs | Mostly correct, minor relationship issues | Significant structural problems |
| Governance | 15% | Complete ownership, tiering, documentation, and change management | Good governance, minor gaps | Missing critical governance elements |
| Tool Implementation | 20% | Clean YAML, working CI/CD, passing tests | Working implementation, minor issues | Non-functional or major errors |
| Business Alignment | 15% | Metrics directly answer business questions, stakeholder-ready | Mostly aligned, minor gaps | Misaligned with business needs |
| Presentation | 10% | Clear, persuasive, handles Q&A confidently | Good presentation, minor clarity issues | Unclear or unpersuasive |

---

## Appendix: Quick Reference Card

### Semantic Layer Checklist

**Before deploying a semantic layer:**
- [ ] All metrics have owners and tiers
- [ ] Grain is explicitly defined and tested
- [ ] Dimensions are conformed across models
- [ ] Relationships are validated (no fan-outs)
- [ ] Business glossary is generated
- [ ] Access control policies are configured
- [ ] CI/CD pipeline includes semantic tests
- [ ] Consumer documentation is published
- [ ] Migration plan exists for existing dashboards
- [ ] Performance baseline is established

### Common Metric Patterns

| Business Concept | Pattern | Example |
|-----------------|---------|---------|
| **Running Total** | Cumulative metric | `SUM(revenue) OVER (ORDER BY date)` |
| **YoY Growth** | Derived metric with offset | `(current - prior) / prior` |
| **Conversion Rate** | Ratio metric | `conversions / sessions` |
| **Cohort Retention** | Metric with cohort dimension | `active_users / cohort_size` |
| **Moving Average** | Derived metric with window | `AVG(revenue) OVER (ORDER BY date ROWS 6 PRECEDING)` |
| **Rank / Percentile** | Calculated field | `RANK() OVER (PARTITION BY region ORDER BY revenue DESC)` |

### Glossary of Terms

| Term | Definition |
|------|-----------|
| **Semantic Layer** | Abstraction tier translating technical data into business concepts |
| **Metric** | A business calculation with guaranteed semantics (e.g., Revenue) |
| **Dimension** | A categorical or temporal attribute for slicing metrics (e.g., Region, Date) |
| **Grain** | The finest level of detail in a semantic model (e.g., order_id) |
| **Measure** | A raw numeric column that can be aggregated (e.g., total_amount) |
| **Headless BI** | Decoupling metrics from visualization tools via API |
| **MetricFlow** | dbt's semantic layer engine |
| **Cube** | Open-source semantic layer for APIs and embedded analytics |
| **LookML** | Looker's semantic modeling language |
| **SCD** | Slowly Changing Dimension — tracking historical changes |
| **Conformed Dimension** | A dimension shared consistently across multiple fact tables |
| **Fan-out** | An unintended many-to-many relationship causing duplicate rows |

---

*Document compiled for ModelBox AI product strategy and educational course development. Based on 2026 market research of 43+ data modeling job postings and semantic layer implementations.*
