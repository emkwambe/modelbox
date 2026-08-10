# Data Governance & Data Contract Architecture: A Comprehensive Breakdown
## For ModelBox AI Product Strategy & Course Development

**Research Context:** Based on deep analysis of 43+ data modeling job postings (July–August 2026), data governance appeared as a secondary responsibility in **~58% of roles** and was identified as the **fastest-growing responsibility** across seniority levels. It is the pivot point where modelers become architects and architects become strategists.

---

## Table of Contents
1. What Is Data Governance in the Modeling Context?
2. Why It Matters Now (The 2026 Imperative)
3. Governance Architecture & Core Components
4. Data Contract Architecture (Deep-Dive)
5. Governance Operating Models
6. Metadata Management & Business Glossaries
7. Standards Enforcement & Automation
8. PII, Compliance & Security Frameworks
9. Ownership, Tiering & Lifecycle Management
10. Lineage Design & Impact Analysis
11. Modern Governance Technology Stacks
12. Anti-Patterns & Common Failures
13. Practical Examples & Templates
14. ModelBox AI Integration Opportunities
15. Course Module: Governance & Contract Mastery

---

## 1. What Is Data Governance in the Modeling Context?

**Data governance** is the system of decision rights, policies, standards, and processes that ensure data is managed as a strategic asset. In the context of data modeling, governance is not an afterthought — it is **baked into the model itself**.

### The Governance-Modeling Stack

```
┌─────────────────────────────────────────────────────────────┐
│  STRATEGIC LAYER                                            │
│  Data Strategy, Domain Ownership, Executive Sponsorship     │
├─────────────────────────────────────────────────────────────┤
│  GOVERNANCE LAYER  ←── YOU ARE HERE                         │
│  Policies, Standards, Contracts, Catalogs, Lineage, Quality│
├─────────────────────────────────────────────────────────────┤
│  SEMANTIC LAYER                                             │
│  Metrics, Dimensions, Business Logic, Access Control        │
├─────────────────────────────────────────────────────────────┤
│  MODELING LAYER                                             │
│  Conceptual, Logical, Physical, Dimensional Models          │
├─────────────────────────────────────────────────────────────┤
│  ENGINEERING LAYER                                          │
│  dbt, Pipelines, ETL/ELT, Storage, Infrastructure           │
├─────────────────────────────────────────────────────────────┤
│  CONSUMPTION LAYER                                          │
│  BI Tools, APIs, AI Agents, Applications                    │
└─────────────────────────────────────────────────────────────┘
```

### Governance vs. Modeling: The Relationship

| Dimension | Data Modeling | Data Governance |
|-----------|--------------|-----------------|
| **Focus** | Structure, relationships, performance | Rules, ownership, compliance, trust |
| **Output** | Schemas, ERDs, DDL, dbt models | Policies, contracts, catalogs, lineage |
| **Audience** | Engineers, architects | Legal, compliance, business, executives |
| **Time Horizon** | Project delivery (weeks) | Organizational lifecycle (years) |
| **Success Metric** | Query performance, model accuracy | Data trust, audit pass rate, incident reduction |
| **Tooling** | ERwin, dbt, SQL | Collibra, Alation, DataHub, Atlan, OpenDataContract |

**The critical insight:** In 2026, employers no longer separate "the person who builds the model" from "the person who governs the model." **The same role does both.**

---

## 2. Why It Matters Now (The 2026 Imperative)

### The Governance Crisis

Modern data stacks have created a **governance debt explosion**:

```
2020: 10 tables, 3 analysts, 1 BI tool → Governance: spreadsheet
2023: 500 tables, 20 analysts, 5 BI tools → Governance: wiki page (outdated)
2026: 5,000 tables, 100+ consumers, 15+ tools, AI agents → Governance: ???
```

**The symptoms:**
- Dashboards show conflicting numbers and no one knows why
- PII leaks through "shadow" tables created by well-meaning analysts
- Regulatory audits require 6-month forensic investigations
- Schema changes break downstream systems with no warning
- New hires spend 3 months learning "how we actually define things here"

### Regulatory & Market Drivers (2026)

| Regulation / Standard | Impact on Data Modeling | Governance Requirement |
|----------------------|------------------------|------------------------|
| **GDPR (EU)** | Right to erasure, data portability | PII classification, lineage to source, retention policies |
| **CCPA/CPRA (California)** | Consumer data rights, opt-out | Data inventory, access logging, deletion workflows |
| **HIPAA (Healthcare)** | Minimum necessary standard, audit trails | Column-level security, PHI tagging, access control |
| **SOC 2 Type II** | Data integrity, access controls | Change management, approval workflows, evidence collection |
| **BCBS 239 (Banking)** | Risk data aggregation accuracy | Single source of truth, lineage, reconciliation |
| **DAMA-DMBOK** | Industry standard framework | Role definitions, stewardship models, metadata management |
| **AI Act (EU)** | Transparency, data quality for AI | Provenance tracking, bias detection, training data governance |

### Quantified Impact

| Metric | Without Governance | With Governance |
|--------|-------------------|-----------------|
| Time to find a data asset | 2–4 hours (asking in Slack) | 30 seconds (catalog search) |
| Regulatory audit preparation | 3–6 months | 2–3 weeks |
| Incident response (bad data in production) | 2–5 days to root cause | 2–4 hours via lineage |
| Onboarding time for new data hire | 3–6 months | 2–4 weeks |
| Schema change breakage rate | 30–50% of changes break something | <5% with contract validation |
| PII exposure incidents | Frequent (unknown unknowns) | Rare (classified and monitored) |

---

## 3. Governance Architecture & Core Components

### The Governance Framework Anatomy

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA GOVERNANCE FRAMEWORK                        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │
│  │  POLICIES   │  │  STANDARDS  │  │      PROCESSES          │   │
│  │             │  │             │  │                         │   │
│  │ • Data      │  │ • Naming    │  │ • Change management     │   │
│  │   quality   │  │   standards │  │ • Incident response     │   │
│  │ • Retention │  │ • Modeling  │  │ • Onboarding            │   │
│  │ • Access    │  │   standards │  │ • Deprecation           │   │
│  │ • Privacy   │  │ • Metadata  │  │ • Certification         │   │
│  │ • Security  │  │   standards │  │ • Review cycles         │   │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │
│  │   ROLES &   │  │  TECHNOLOGY │  │      METRICS            │   │
│  │  OWNERSHIP  │  │    STACK    │  │                         │   │
│  │             │  │             │  │ • Data quality score    │   │
│  │ • Data      │  │ • Catalog   │  │ • Catalog coverage      │   │
│  │   owners    │  │ • Lineage   │  │ • Time-to-find          │   │
│  │ • Stewards  │  │ • Contracts │  │ • Incident frequency    │   │
│  │ • Custodians│  │ • Quality   │  │ • Audit pass rate       │   │
│  │ • Consumers │  │ • Security  │  │ • Trust score           │   │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Deep-Dive

#### A. Policies (The "What Must Be True")

Policies are high-level statements of intent. They answer: **"What must be true about our data?"**

```yaml
# governance/policies/data_quality_policy.yml
policy:
  name: data_quality_policy
  version: 2.1
  owner: chief_data_officer
  effective_date: 2026-01-01

  statements:
    - id: DQ-001
      statement: "All production data assets must have documented data quality tests"
      scope: [production, staging]
      enforcement: automated

    - id: DQ-002
      statement: "Critical metrics (Tier 1) must have freshness checks with SLA < 1 hour"
      scope: [tier_1_metrics]
      enforcement: automated

    - id: DQ-003
      statement: "All tables containing PII must have classification tags and access controls"
      scope: [all_tables]
      enforcement: automated + manual_review

    - id: DQ-004
      statement: "Schema changes to Tier 1 models require approval from data architecture"
      scope: [tier_1_models]
      enforcement: pull_request_gate
```

**Policy Categories:**

| Category | Example Policy | Enforcement Mechanism |
|----------|---------------|----------------------|
| **Data Quality** | "No nulls in primary keys" | dbt tests, Great Expectations |
| **Data Privacy** | "PII columns encrypted at rest" | Column-level tags, encryption policies |
| **Data Retention** | "Raw data retained for 7 years, aggregates indefinitely" | Automated archival jobs |
| **Data Access** | "Financial data accessible only to Finance + CFO" | RBAC, row-level security |
| **Data Lineage** | "All production models must have documented lineage" | Catalog auto-capture |
| **Change Management** | "Breaking changes require 30-day notice" | CI/CD gates, deprecation workflows |

#### B. Standards (The "How We Do It")

Standards are prescriptive rules. They answer: **"How must we build and maintain data assets?"**

```yaml
# governance/standards/naming_standards.yml
standard:
  name: database_naming_standard
  version: 3.0
  owner: data_architecture_team

  rules:
    - category: tables
      pattern: "{domain}_{entity}_{type}"
      examples:
        - "finance_revenue_fact"
        - "customer_profile_dim"
        - "marketing_campaign_bridge"

    - category: columns
      pattern: "{attribute}_{modifier}"
      examples:
        - "order_total_amount"
        - "customer_email_address"
        - "product_category_code"

    - category: primary_keys
      pattern: "{entity}_id"
      examples:
        - "order_id"
        - "customer_id"

    - category: foreign_keys
      pattern: "{referenced_entity}_id"
      examples:
        - "customer_id" (in orders table)
        - "product_id" (in orders table)

  linting:
    tool: sqlfluff
    severity: error
    auto_fix: true
```

**Standard Domains:**

| Domain | Scope | Example Standard |
|--------|-------|-----------------|
| **Naming** | Tables, columns, files, models | fct_orders, dim_customers, stg_raw_orders |
| **Modeling** | Kimball vs Data Vault vs 3NF | "Analytics marts use Kimball star schema" |
| **Metadata** | Required tags, descriptions, owners | Every model must have owner, description, tier |
| **Documentation** | ERDs, data dictionaries, runbooks | "Every production model has auto-generated docs" |
| **Versioning** | Semantic versioning for models | "Breaking schema changes = major version bump" |
| **Testing** | Minimum test coverage | "100% of PKs tested for uniqueness and non-null" |

#### C. Processes (The "How We Work")

Processes define workflows. They answer: **"What happens when...?"**

```yaml
# governance/processes/change_management.yml
process:
  name: schema_change_management
  trigger: pull_request_to_production_branch

  steps:
    - step: automated_validation
      actions:
        - run_dbt_tests
        - run_sqlfluff_linter
        - check_naming_standards
        - check_metadata_completeness
        - check_lineage_impact

    - step: impact_assessment
      conditions:
        - if: breaking_change
          then: [notify_all_consumers, require_architect_approval]
        - if: non_breaking_change
          then: [notify_direct_consumers, require_team_lead_approval]

    - step: approval_gate
      roles:
        - data_architect: required_for_tier_1
        - domain_owner: required_for_all
        - security_officer: required_for_pii_changes

    - step: deployment
      actions:
        - deploy_to_staging
        - run_smoke_tests
        - deploy_to_production
        - update_catalog
        - notify_consumers
```

---

## 4. Data Contract Architecture (Deep-Dive)

### What Is a Data Contract?

A **data contract** is a formal agreement between a data producer and data consumer that specifies:
- The schema (structure, types, constraints)
- The semantics (business meaning, allowed values)
- The quality expectations (freshness, completeness, accuracy)
- The service level (availability, latency, support)
- The ownership and lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA CONTRACT                            │
├─────────────────────────────────────────────────────────────┤
│  Producer: Analytics Engineering Team                       │
│  Consumer: Finance Dashboard + ML Feature Store             │
├─────────────────────────────────────────────────────────────┤
│  SCHEMA:                                                    │
│    order_id: UUID (PK, non-null)                            │
│    customer_id: UUID (FK, non-null)                         │
│    order_total: DECIMAL(18,2) (non-null, >= 0)            │
│    order_status: ENUM('pending','completed','cancelled')   │
│    ordered_at: TIMESTAMP (non-null)                         │
├─────────────────────────────────────────────────────────────┤
│  QUALITY:                                                   │
│    - Freshness: < 1 hour                                    │
│    - Completeness: 100% (no nulls in required fields)       │
│    - Accuracy: Matches source system within 0.1%            │
├─────────────────────────────────────────────────────────────┤
│  SLA:                                                       │
│    - Availability: 99.9%                                    │
│    - Latency: p95 < 2s                                      │
│    - Support: Business hours, 4-hour response               │
├─────────────────────────────────────────────────────────────┤
│  LIFECYCLE:                                                 │
│    - Version: 2.1.0                                         │
│    - Review Date: 2026-12-01                                │
│    - Deprecation Policy: 90-day notice for breaking changes │
└─────────────────────────────────────────────────────────────┘
```

### Contract Types & Formats

#### A. OpenDataContract (YAML)

The emerging open standard for data contracts.

```yaml
# contract: orders_v2.1.0.yml
apiVersion: opendatacontract/v1.0
kind: DataContract
id: orders-fact-v2.1.0
name: Orders Fact Table
version: 2.1.0
status: active

schema:
  - name: order_id
    type: uuid
    required: true
    primaryKey: true
    description: Unique identifier for the order

  - name: customer_id
    type: uuid
    required: true
    foreignKey:
      table: dim_customers
      column: customer_id
    description: Reference to the customer who placed the order

  - name: order_total
    type: decimal
    precision: 18
    scale: 2
    required: true
    quality:
      - rule: non_negative
        type: custom
        expression: order_total >= 0
    description: Total monetary value of the order in USD

  - name: order_status
    type: string
    required: true
    allowedValues:
      - pending
      - completed
      - cancelled
      - refunded
    description: Current status of the order in the fulfillment lifecycle

  - name: ordered_at
    type: timestamp
    required: true
    description: Timestamp when the order was placed

quality:
  freshness:
    - column: ordered_at
      threshold: 1h

  completeness:
    - column: order_id
      threshold: 1.0
    - column: order_total
      threshold: 1.0

  accuracy:
    - source: raw_orders
      target: fct_orders
      tolerance: 0.001

sla:
  availability: 99.9%
  latency: p95 < 2s
  support:
    hours: business_hours
    response_time: 4h

ownership:
  team: analytics_engineering
  owner: jane.doe@company.com
  steward: john.smith@company.com

lifecycle:
  created: 2025-01-15
  reviewed: 2026-06-01
  nextReview: 2026-12-01
  deprecationPolicy: 90_days_notice
```

#### B. Apache Avro (Binary + JSON Schema)

Best for streaming data, Kafka, and event-driven architectures.

```json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.company.data.orders",
  "doc": "Represents a customer order event",
  "fields": [
    {
      "name": "order_id",
      "type": "string",
      "doc": "UUID v4 identifier",
      "logicalType": "uuid"
    },
    {
      "name": "customer_id",
      "type": "string",
      "doc": "Reference to customer entity"
    },
    {
      "name": "order_total",
      "type": {
        "type": "bytes",
        "logicalType": "decimal",
        "precision": 18,
        "scale": 2
      },
      "doc": "Total order value in USD"
    },
    {
      "name": "order_status",
      "type": {
        "type": "enum",
        "name": "OrderStatus",
        "symbols": ["PENDING", "COMPLETED", "CANCELLED", "REFUNDED"]
      },
      "doc": "Order fulfillment status"
    },
    {
      "name": "ordered_at",
      "type": {
        "type": "long",
        "logicalType": "timestamp-millis"
      },
      "doc": "Order placement timestamp"
    }
  ],
  "metadata": {
    "contract_version": "2.1.0",
    "owner": "analytics_engineering",
    "sla_availability": "99.9%",
    "pii_classification": "none",
    "retention_days": 2555
  }
}
```

#### C. Protocol Buffers (Protobuf)

Best for microservices, gRPC APIs, and cross-language systems.

```protobuf
// orders.proto
syntax = "proto3";
package company.data.orders;

import "google/protobuf/timestamp.proto";
import "company/data/common/metadata.proto";

message Order {
  // Contract metadata
  DataContractMetadata contract = 1;

  // Business fields
  string order_id = 2;           // UUID v4
  string customer_id = 3;        // FK to customers

  // Decimal handling: store as integer (cents) to avoid float issues
  int64 order_total_cents = 4;   // USD cents, non-negative

  OrderStatus status = 5;
  google.protobuf.Timestamp ordered_at = 6;

  // Quality annotations
  DataQualityScores quality = 7;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_COMPLETED = 2;
  ORDER_STATUS_CANCELLED = 3;
  ORDER_STATUS_REFUNDED = 4;
}

message DataQualityScores {
  float completeness = 1;    // 0.0 - 1.0
  float freshness_hours = 2; // Age of data
  float accuracy_score = 3;  // Match to source
}
```

#### D. dbt Contracts (Model-Level)

Native to dbt, enforced at build time.

```yaml
# models/fct_orders.yml
models:
  - name: fct_orders
    description: Fact table containing all customer orders

    config:
      contract:
        enforced: true

    columns:
      - name: order_id
        data_type: uuid
        constraints:
          - type: not_null
          - type: unique
        description: Primary key for orders

      - name: customer_id
        data_type: uuid
        constraints:
          - type: not_null
          - type: foreign_key
            expression: "customer_id REFERENCES dim_customers(customer_id)"
        description: Foreign key to dim_customers

      - name: order_total
        data_type: decimal(18,2)
        constraints:
          - type: not_null
          - type: check
            expression: "order_total >= 0"
        description: Total order value in USD

      - name: order_status
        data_type: varchar(20)
        constraints:
          - type: not_null
          - type: check
            expression: "order_status IN ('pending','completed','cancelled','refunded')"
        description: Order fulfillment status

      - name: ordered_at
        data_type: timestamp
        constraints:
          - type: not_null
        description: Order placement timestamp

    tests:
      - dbt_utils.recency:
          date_column: ordered_at
          interval: 1
          unit: hour

      - dbt_expectations.expect_column_values_to_be_between:
          column: order_total
          min_value: 0
```

### Contract Lifecycle Management

```
┌─────────────────────────────────────────────────────────────┐
│              DATA CONTRACT LIFECYCLE                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌────────┐ │
│  │ DRAFT   │ → │ REVIEW  │ → │ ACTIVE  │ → │ DEPRECATED│ │
│  └─────────┘    └─────────┘    └─────────┘    └────────┘ │
│       ↑                            │                │      │
│       └────────────────────────────┘                ↓      │
│                              ┌─────────┐         ┌────────┐ │
│                              │ UPDATED │ ←────── │ SUNSET │ │
│                              └─────────┘         └────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| Stage | Activities | Exit Criteria |
|-------|-----------|---------------|
| **Draft** | Schema design, quality rules, SLA negotiation | Producer and consumer agree on contract |
| **Review** | Architecture review, security review, compliance check | All approvals obtained |
| **Active** | Contract enforced in production, monitored, supported | Contract is the source of truth |
| **Updated** | Version bump, breaking vs non-breaking change assessment | Consumer migration complete |
| **Deprecated** | 90-day notice, migration path documented, replacement active | No active consumers remain |
| **Sunset** | Contract removed, data archived, documentation archived | Audit trail preserved |

---

## 5. Governance Operating Models

### Model A: Centralized Governance

```
┌─────────────────────────────────────────┐
│         CENTRAL GOVERNANCE TEAM         │
│  (Data Governance Office / CDO)         │
│                                         │
│  ├─ Sets all standards                  │
│  ├─ Approves all schema changes         │
│  ├─ Owns the catalog                    │
│  ├─ Manages all access requests         │
│  └─ Enforces all policies               │
├─────────────────────────────────────────┤
│         DOMAIN TEAMS                    │
│  (Implement but do not decide)          │
└─────────────────────────────────────────┘
```

**Best for:** Regulated industries (finance, healthcare, government), small data teams, early maturity.

**Pros:** Consistent, auditable, clear accountability.
**Cons:** Slow, bottlenecked, disempowers domain experts.

### Model B: Federated Governance

```
┌─────────────────────────────────────────┐
│         GOVERNANCE COUNCIL              │
│  (Sets framework, resolves disputes)    │
│                                         │
│  ├─ Defines minimum standards           │
│  ├─ Cross-domain lineage                │
│  ├─ Dispute resolution                  │
│  └─ Enterprise catalog backbone         │
├─────────────────────────────────────────┤
│    DOMAIN A        │    DOMAIN B        │
│  ├─ Owns models    │  ├─ Owns models     │
│  ├─ Sets local std │  ├─ Sets local std  │
│  ├─ Local catalog  │  ├─ Local catalog   │
│  └─ Local access   │  └─ Local access    │
└─────────────────────────────────────────┘
```

**Best for:** Medium-to-large enterprises, multi-domain organizations.

**Pros:** Balanced speed and consistency, domain expertise leveraged.
**Cons:** Requires mature coordination, risk of domain silos.

### Model C: Data Mesh (Decentralized)

```
┌─────────────────────────────────────────┐
│         PLATFORM TEAM                   │
│  (Provides infrastructure, not rules)   │
│                                         │
│  ├─ Catalog platform                    │
│  ├─ Contract validation tools           │
│  ├─ Access control infrastructure       │
│  └─ Monitoring and observability        │
├─────────────────────────────────────────┤
│    DOMAIN A (Self-Governed)             │
│  ├─ Owns data products                  │
│  ├─ Publishes contracts                 │
│  ├─ Manages own quality                 │
│  └─ Owns access policies                │
├─────────────────────────────────────────┤
│    DOMAIN B (Self-Governed)             │
│  ├─ Owns data products                  │
│  ├─ Publishes contracts                 │
│  ├─ Manages own quality                 │
│  └─ Owns access policies                │
└─────────────────────────────────────────┘
```

**Best for:** Large tech companies, SaaS, modern data-native organizations.

**Pros:** Maximum autonomy, fastest iteration, scales with organization.
**Cons:** Requires high maturity, risk of inconsistency, "tragedy of the commons."

### Model D: The Hybrid (Recommended for Most)

```
┌─────────────────────────────────────────────────────────────┐
│  ENTERPRISE LAYER (Centralized)                             │
│  ├─ Cross-domain standards (naming, security, compliance)     │
│  ├─ Enterprise catalog (unified search, lineage)            │
│  ├─ Regulatory policies (GDPR, HIPAA, SOC 2)                │
│  └─ Tier 1 asset governance (critical metrics, financials)  │
├─────────────────────────────────────────────────────────────┤
│  DOMAIN LAYER (Federated)                                   │
│  ├─ Domain-specific models and contracts                    │
│  ├─ Domain team ownership and stewardship                   │
│  ├─ Local quality standards (above enterprise minimum)      │
│  └─ Self-service access management (within policy bounds)     │
├─────────────────────────────────────────────────────────────┤
│  PLATFORM LAYER (Enabling)                                  │
│  ├─ Automated contract validation                           │
│  ├─ CI/CD governance gates                                  │
│  ├─ Catalog auto-discovery                                  │
│  └─ Observability and alerting                              │
└─────────────────────────────────────────────────────────────┘
```

**This is the model most 2026 job postings implicitly describe.**

---

## 6. Metadata Management & Business Glossaries

### The Metadata Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│  METADATA STACK                                             │
├─────────────────────────────────────────────────────────────┤
│  L4: BUSINESS METADATA                                      │
│  ├─ Business terms ("Revenue", "Active Customer")             │
│  ├─ Business definitions                                    │
│  ├─ Ownership and stewardship                               │
│  ├─ Data quality scores                                     │
│  └─ Regulatory classification                               │
├─────────────────────────────────────────────────────────────┤
│  L3: TECHNICAL METADATA                                     │
│  ├─ Table schemas, column types, constraints                │
│  ├─ Indexes, partitions, clustering keys                    │
│  ├─ Storage size, row counts, freshness                       │
│  └─ Query patterns, access logs                             │
├─────────────────────────────────────────────────────────────┤
│  L2: OPERATIONAL METADATA                                   │
│  ├─ Pipeline jobs, schedules, dependencies                   │
│  ├─ Run times, failure rates, retry counts                  │
│  ├─ dbt tests, Great Expectations results                   │
│  └─ Data freshness, latency SLAs                            │
├─────────────────────────────────────────────────────────────┤
│  L1: GOVERNANCE METADATA                                    │
│  ├─ Data lineage (column-level, table-level)                │
│  ├─ Data contracts, versions, status                        │
│  ├─ Access policies, PII tags, retention rules              │
│  └─ Change history, audit trails                            │
└─────────────────────────────────────────────────────────────┘
```

### Business Glossary Structure

```yaml
# governance/business_glossary.yml
business_glossary:
  version: 3.0
  last_updated: 2026-08-10

  terms:
    - term: Revenue
      definition: |
        Total recognized revenue from completed customer orders, 
        net of discounts but before taxes and shipping.
      calculation: |
        SUM(order_total) WHERE status = 'completed' AND 
        order_date <= reporting_date
      synonyms: [Gross Revenue, Bookings, Sales]
      related_terms: [Net Revenue, GAAP Revenue, MRR]
      owner: finance_team
      steward: jane.doe@company.com
      tier: certified

      lineage:
        sources:
          - raw_orders (source system)
        transformations:
          - stg_orders (staging)
          - fct_orders (fact table)
        semantic_layer:
          - revenue_metric (MetricFlow)
        consumers:
          - tableau_executive_dashboard
          - powerbi_finance_report
          - api_revenue_endpoint
          - ml_ltv_model

      quality:
        freshness: < 1 hour
        accuracy: 99.9% match to GL
        completeness: 100%

      governance:
        pii: false
        regulatory: [SOX, BCBS_239]
        retention: 7_years
        access_classification: internal

    - term: Active Customer
      definition: |
        A customer who has placed at least one order in the last 90 days.
      calculation: |
        COUNT(DISTINCT customer_id) WHERE 
        last_order_date >= CURRENT_DATE - 90
      synonyms: [Engaged Customer, Recent Customer]
      related_terms: [Churned Customer, At-Risk Customer, New Customer]
      owner: product_team
      steward: john.smith@company.com
      tier: certified

      lineage:
        sources:
          - raw_customers
          - raw_orders
        transformations:
          - dim_customers
        semantic_layer:
          - active_customers_metric
        consumers:
          - product_analytics_dashboard
          - marketing_segmentation
          - executive_kpi_report
```

---

## 7. Standards Enforcement & Automation

### Automated Governance Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  DEVELOPER COMMITS CODE                                     │
│  (dbt model, YAML contract, schema change)                  │
├─────────────────────────────────────────────────────────────┤
│  CI/CD PIPELINE                                             │
│  ├─ sqlfluff: Naming standard linting                       │
│  ├─ dbt compile: Schema validation                          │
│  ├─ dbt test: Quality rule validation                     │
│  ├─ custom checks:                                          │
│  │   ├─ Metadata completeness (owner, description, tier)    │
│  │   ├─ PII classification verification                     │
│  │   ├─ Lineage connectivity check                          │
│  │   └─ Contract version compliance                         │
│  ├─ catalog sync: Push metadata to DataHub/Atlan            │
│  └─ impact analysis: Notify downstream consumers            │
├─────────────────────────────────────────────────────────────┤
│  APPROVAL GATES                                             │
│  ├─ Auto-pass: Non-breaking, low-risk, all checks green     │
│  ├─ Team lead: Medium-risk, new metrics, new domains        │
│  └─ Architect: Breaking changes, Tier 1 assets, PII        │
├─────────────────────────────────────────────────────────────┤
│  PRODUCTION DEPLOYMENT                                      │
│  ├─ Schema change executed (with rollback plan)             │
│  ├─ Catalog updated with new metadata                       │
│  ├─ Contracts published to registry                         │
│  └─ Consumers notified of changes                           │
└─────────────────────────────────────────────────────────────┘
```

### Naming Standard Enforcement (sqlfluff)

```ini
# .sqlfluff
[sqlfluff]
dialect = snowflake
templater = dbt

[sqlfluff:rules:convention.terminology]
# Enforce table naming: {domain}_{entity}_{type}
# e.g., finance_revenue_fact, customer_profile_dim

[sqlfluff:rules:convention.column_names]
# Enforce: {attribute}_{modifier}
# e.g., order_total_amount, customer_email_address

[sqlfluff:rules:convention.primary_key]
# Enforce: {entity}_id
# e.g., order_id, customer_id

[sqlfluff:rules:convention.foreign_key]
# Enforce: {referenced_entity}_id
# e.g., customer_id (in orders table)
```

### Metadata Completeness Check

```python
# governance/checks/metadata_completeness.py
import yaml

def check_model_metadata(model_path):
    # Ensure every production model has required metadata.
    required_fields = [
        'description',
        'owner',
        'tier',
        'columns.*.description'
    ]

    with open(model_path) as f:
        model = yaml.safe_load(f)

    errors = []
    for field in required_fields:
        if not resolve_path(model, field):
            errors.append(f"Missing required field: {field}")

    return errors

# In CI:
# for model in models/production/:
#     errors = check_model_metadata(model)
#     if errors: fail_build(errors)
```

---

## 8. PII, Compliance & Security Frameworks

### PII Classification Framework

```yaml
# governance/pii_classification.yml
pii_classification:
  levels:
    - level: public
      description: No restrictions
      examples: [product_name, order_status, category_code]

    - level: internal
      description: Company-internal use only
      examples: [revenue, employee_count, strategy_documents]
      access: all_employees

    - level: confidential
      description: Restricted to specific roles
      examples: [customer_email, phone_number, address]
      access: [finance, support, data_team]
      masking: partial

    - level: restricted
      description: Highly sensitive, minimal access
      examples: [ssn, credit_card, health_records, biometric_data]
      access: [compliance_officer, specific_owners]
      masking: full
      encryption: at_rest + in_transit
      audit: all_access_logged

  tagging_rules:
    - pattern: "*email*"
      classification: confidential
      auto_tag: true

    - pattern: "*ssn*" OR "*social_security*"
      classification: restricted
      auto_tag: true
      alert_security: true

    - pattern: "*password*" OR "*token*" OR "*secret*"
      classification: restricted
      auto_tag: true
      alert_security: true
      block_from_logs: true
```

### Compliance Mapping by Regulation

| Regulation | Modeling Requirement | Governance Control |
|-----------|---------------------|-------------------|
| **GDPR** | Right to erasure | Lineage to all copies, deletion workflows, retention policies |
| **GDPR** | Data portability | Standardized export formats, schema documentation |
| **GDPR** | Privacy by design | PII classification at model creation, minimization principles |
| **HIPAA** | Minimum necessary | Column-level access, role-based filtering, audit trails |
| **HIPAA** | Audit controls | Immutable access logs, query history, data lineage |
| **SOC 2** | Change management | PR approval gates, test requirements, rollback procedures |
| **SOC 2** | Logical access | RBAC, MFA, quarterly access reviews |
| **BCBS 239** | Single source of truth | Enterprise data model, canonical definitions, reconciliation |
| **BCBS 239** | Data lineage | End-to-end traceability, impact analysis, data dictionary |
| **AI Act** | Training data quality | Provenance tracking, bias detection, fairness metrics |

---

## 9. Ownership, Tiering & Lifecycle Management

### Asset Tiering System

```yaml
# governance/tiering_system.yml
asset_tiers:
  - tier: tier_1_critical
    description: |
      Assets that directly impact financial reporting, 
      regulatory compliance, or executive decision-making.
    examples:
      - revenue metrics
      - customer count
      - financial statements
    governance:
      owner_required: true
      steward_required: true
      review_cycle: quarterly
      approval_for_changes: [data_architect, domain_owner, compliance_officer]
      test_coverage: 100%
      documentation: comprehensive
      sla: 99.9% availability, < 1h freshness
      backup: real-time replication

  - tier: tier_2_important
    description: |
      Assets used for operational decision-making, 
      product analytics, or team-level reporting.
    examples:
      - product usage metrics
      - marketing campaign performance
      - support ticket analytics
    governance:
      owner_required: true
      review_cycle: semi_annual
      approval_for_changes: [team_lead]
      test_coverage: 80%
      documentation: standard
      sla: 99.5% availability, < 4h freshness
      backup: daily snapshots

  - tier: tier_3_supporting
    description: |
      Supporting assets, staging models, intermediate tables.
    examples:
      - staging models
      - intermediate CTEs
      - enrichment tables
    governance:
      owner_required: true
      review_cycle: annual
      approval_for_changes: [any_team_member]
      test_coverage: 50%
      documentation: minimal
      sla: best_effort
      backup: weekly snapshots

  - tier: tier_4_experimental
    description: |
      Research, prototypes, ad-hoc analyses. Not guaranteed.
    examples:
      - ml experiments
      - exploratory datasets
      - prototype models
    governance:
      owner_required: true
      review_cycle: monthly
      approval_for_changes: [self]
      test_coverage: optional
      documentation: optional
      sla: none
      retention: 30_days_auto_delete
```

### Deprecation Workflow

```yaml
# governance/processes/deprecation.yml
deprecation_workflow:
  trigger: owner_requests_deprecation OR no_usage_90_days

  steps:
    - step: announce
      actions:
        - post_to_data_community_slack
        - update_catalog_status
        - add_deprecation_banner_to_dashboards
      duration: immediate

    - step: notice_period
      duration: 90_days
      actions:
        - weekly_reminder_to_consumers
        - track_migration_progress
        - provide_migration_guide

    - step: soft_deletion
      actions:
        - move_to_archive_schema
        - remove_from_semantic_layer
        - disable_dashboard_queries
      duration: immediate_after_notice

    - step: hard_deletion
      actions:
        - drop_table
        - remove_from_catalog
        - archive_documentation
      duration: 30_days_after_soft_deletion

    - step: audit
      actions:
        - log_deletion_in_governance_registry
        - notify_compliance_if_regulated
        - update_data_lineage
      duration: immediate
```

---

## 10. Lineage Design & Impact Analysis

### Lineage Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA LINEAGE GRAPH                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SOURCE SYSTEMS                                             │
│  ├─ Salesforce (raw_accounts)                             │
│  ├─ Shopify (raw_orders)                                  │
│  └─ Segment (raw_events)                                    │
│         ↓                                                   │
│  STAGING LAYER                                              │
│  ├─ stg_accounts ← raw_accounts                            │
│  ├─ stg_orders   ← raw_orders                              │
│  └─ stg_events   ← raw_events                              │
│         ↓                                                   │
│  WAREHOUSE LAYER                                            │
│  ├─ dim_customers ← stg_accounts                           │
│  ├─ fct_orders    ← stg_orders + dim_customers             │
│  └─ fct_sessions  ← stg_events + dim_customers             │
│         ↓                                                   │
│  SEMANTIC LAYER                                             │
│  ├─ revenue_metric ← fct_orders                             │
│  ├─ active_users_metric ← dim_customers                     │
│  └─ conversion_rate_metric ← fct_orders + fct_sessions      │
│         ↓                                                   │
│  CONSUMPTION                                                │
│  ├─ Tableau: Executive Dashboard ← revenue_metric           │
│  ├─ Power BI: Finance Report ← revenue_metric               │
│  ├─ API: Revenue Endpoint ← revenue_metric                │
│  └─ ML: LTV Model ← revenue_metric + active_users_metric    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Impact Analysis: Schema Change Scenario

**Scenario:** Data Engineer wants to rename `fct_orders.order_total` to `fct_orders.total_amount`.

```yaml
# Auto-generated impact analysis
impact_analysis:
  change:
    type: breaking
    action: column_rename
    from: fct_orders.order_total
    to: fct_orders.total_amount

  affected_assets:
    semantic_layer:
      - metric: revenue
        file: models/semantic_layer/_metrics.yml
        fix: update measure expression
      - metric: aov
        file: models/semantic_layer/_metrics.yml
        fix: update measure expression

    downstream_models:
      - model: mart_monthly_revenue
        file: models/marts/mart_monthly_revenue.sql
        fix: update column reference
      - model: customer_ltv
        file: models/marts/customer_ltv.sql
        fix: update column reference

    dashboards:
      - dashboard: executive_overview
        tool: tableau
        owner: exec_team
        fix: update data source field mapping
      - dashboard: finance_monthly
        tool: powerbi
        owner: finance_team
        fix: update measure reference

    apis:
      - endpoint: /api/v1/revenue
        owner: platform_team
        fix: update response schema

    ml_pipelines:
      - pipeline: ltv_prediction
        owner: ml_team
        fix: update feature store schema

  total_consumers_affected: 12
  estimated_migration_effort: 8_hours
  risk_level: high

  recommended_action: |
    Instead of renaming, create a new column total_amount 
    and maintain order_total as an alias with deprecation notice.
    This reduces risk from HIGH to LOW.
```

---

## 11. Modern Governance Technology Stacks

### Enterprise Governance Suites

| Tool | Category | Best For | Pricing | Key Strength | Key Weakness |
|------|----------|----------|---------|-------------|--------------|
| **Collibra** | Enterprise Catalog | Large enterprises, regulated industries | $$$$ | Mature, comprehensive, strong governance workflows | Expensive, complex, slow implementation |
| **Alation** | Enterprise Catalog | Data-driven enterprises | $$$ | Best-in-class ML-assisted cataloging | Expensive, less flexible for modern stacks |
| **Informatica** | Enterprise MDM/Governance | Legacy enterprises, MDM-heavy | $$$$ | Deep data integration + governance | Legacy feel, expensive |

### Modern Data Governance (2026)

| Tool | Category | Best For | Pricing | Key Strength | Key Weakness |
|------|----------|----------|---------|-------------|--------------|
| **Atlan** | Active Metadata Platform | Modern data stacks, dbt-native | $$ | Beautiful UI, dbt integration, collaborative | Less mature enterprise features |
| **DataHub** | Open-Source Catalog | Tech companies, custom needs | Free / $ | Open-source, extensible, strong lineage | Requires engineering investment |
| **Monte Carlo** | Data Observability | Data quality-focused orgs | $$ | Best-in-class incident detection | Narrow scope (quality only) |
| **Soda** | Data Contract Quality | Contract-driven governance | $ | Native data contract support | Smaller ecosystem |
| **Metaplane** | Data Observability | Small-to-mid modern stacks | $ | Easy setup, dbt integration | Less enterprise depth |
| **Secoda** | AI-Native Catalog | AI-forward teams | $ | AI-powered documentation | Newer, smaller install base |

### The Modern Governance Stack (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│  MODERN GOVERNANCE STACK (2026)                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CATALOG & DISCOVERY                                        │
│  ├─ DataHub (open-source) OR Atlan (managed)              │
│  └─ Purpose: Unified search, lineage, ownership             │
│                                                             │
│  QUALITY & CONTRACTS                                        │
│  ├─ dbt tests (schema, data quality)                        │
│  ├─ Great Expectations (advanced validations)               │
│  ├─ Soda (data contract validation)                         │
│  └─ Purpose: Automated quality enforcement                 │
│                                                             │
│  OBSERVABILITY                                              │
│  ├─ Monte Carlo OR Metaplane                                │
│  └─ Purpose: Incident detection, anomaly alerting           │
│                                                             │
│  STANDARD ENFORCEMENT                                       │
│  ├─ sqlfluff (naming standards)                             │
│  ├─ dbt contracts (schema enforcement)                      │
│  ├─ CI/CD gates (approval workflows)                        │
│  └─ Purpose: Prevent bad code from reaching production      │
│                                                             │
│  DOCUMENTATION                                              │
│  ├─ dbt docs (auto-generated)                               │
│  ├─ GitBook / Notion (runbooks, policies)                 │
│  └─ Purpose: Living documentation                           │
│                                                             │
│  ACCESS CONTROL                                             │
│  ├─ Snowflake / BigQuery native RBAC                        │
│  ├─ Immuta / Privacera (advanced policy)                    │
│  └─ Purpose: Least-privilege access                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 12. Anti-Patterns & Common Failures

### Anti-Pattern 1: The "Governance Theater"

❌ **Bad:** Governance exists on paper but not in practice.
```
- Policy: "All models must have owners"
- Reality: 60% of production models have no owner
- Policy: "All schema changes require approval"
- Reality: Changes deployed directly to production
- Policy: "PII must be classified"
- Reality: Classification spreadsheet last updated 2023
```

✅ **Good:** Governance is automated and enforced in CI/CD.
```
- CI/CD fails if model lacks owner
- Production deployment blocked without approval
- PII auto-detected and tagged via regex + ML
```

### Anti-Pattern 2: The "Catalog Graveyard"

❌ **Bad:** Catalog is built as a one-time project, then abandoned.
```
- Q1 2025: "Let's implement Alation!"
- Q2 2025: Catalog populated with 500 tables
- Q3 2025: 200 new tables added, catalog not updated
- Q4 2025: Analysts stop using catalog because it is outdated
- Q1 2026: "We need a new catalog tool!"
```

✅ **Good:** Catalog is auto-synced from code.
```
- Every dbt model auto-pushes metadata to catalog
- Every schema change auto-updates catalog
- Catalog freshness = pipeline freshness
```

### Anti-Pattern 3: The "Over-Engineered Policy"

❌ **Bad:** Policies so complex no one can follow them.
```yaml
policy:
  name: data_access_policy
  pages: 47
  sections: 23
  approval_chain: 6_levels
  exception_process: 12_steps
  # Result: Everyone finds workarounds
```

✅ **Good:** Policies are simple, automated, and pragmatic.
```yaml
policy:
  name: data_access_policy
  rules:
    - "PII: restricted role only"
    - "Financial: finance role + approval"
    - "Public: all employees"
  # Automated via RBAC, no manual process for 90% of cases
```

### Anti-Pattern 4: The "Shadow Governance"

❌ **Bad:** Official governance is slow, so teams create their own.
```
- Official catalog: Collibra (IT-managed, 2-week update lag)
- Team A: Google Sheet with "our tables"
- Team B: Notion page with "data dictionary"
- Team C: Slack channel #data-questions
- Result: 4 sources of truth, all partially wrong
```

✅ **Good:** One catalog, auto-synced, with domain team edit access.
```
- DataHub auto-ingests from dbt, Snowflake, Airflow
- Domain teams can edit their own descriptions
- Central team manages taxonomy and cross-domain lineage
```

### Anti-Pattern 5: The "Breaking Change Surprise"

❌ **Bad:** Schema change breaks production dashboards with no warning.
```
Friday 4pm: Engineer renames column
Friday 5pm: Executive dashboard shows blank charts
Monday 9am: CEO asks "Why is revenue zero?"
```

✅ **Good:** Impact analysis runs before deployment.
```
- PR triggers lineage analysis
- All affected consumers identified
- Breaking changes require 30-day notice
- Soft deprecation with aliases before hard removal
```

### Anti-Pattern 6: The "Compliance Checkbox"

❌ **Bad:** Compliance treated as annual audit exercise.
```
- December: "We need to pass SOC 2 audit"
- December: Rush to document everything
- January: Audit passes
- February: Documentation abandoned until next December
```

✅ **Good:** Compliance is continuous.
```
- Every PR is an audit trail
- Every access is logged automatically
- Quarterly access reviews are automated reports
- Auditors get read-only access to live governance registry
```

---

## 13. Practical Examples & Templates

### Example A: Complete Governance Package for a New Data Product

```yaml
# data_product: customer_360.yml
data_product:
  name: customer_360
  domain: marketing
  owner: sarah.chen@company.com
  steward: marketing_data_team
  tier: tier_2_important

  description: |
    Unified view of customer behavior across touchpoints:
    web, mobile, support, and purchase history.

  contracts:
    - name: customer_360_v1.0
      format: opendatacontract
      file: contracts/customer_360_v1.0.yml
      status: active

  models:
    - ref: dim_customers
      tier: tier_2
    - ref: fct_web_sessions
      tier: tier_2
    - ref: fct_support_tickets
      tier: tier_2
    - ref: mart_customer_360
      tier: tier_2

  semantic_layer:
    - metric: active_customers
    - metric: customer_ltv
    - metric: support_ticket_rate

  consumers:
    - tableau: marketing_dashboard
    - api: customer_segmentation_api
    - ml: churn_prediction_model

  policies:
    - pii_classification: confidential
      fields: [email, phone, address]
    - retention: 3_years
    - access: marketing_team + data_team

  quality:
    - freshness: < 4_hours
    - completeness: > 99%
    - accuracy: match_to_crm_within_1%

  lineage:
    sources:
      - salesforce_accounts
      - segment_web_events
      - zendesk_tickets
    transformations:
      - staging_models
      - warehouse_models
      - customer_360_mart
    consumers:
      - marketing_dashboard
      - segmentation_api
      - churn_model
```

### Example B: Regulatory Compliance Mapping (HIPAA)

```yaml
# governance/compliance/hipaa_mapping.yml
hipaa_compliance:
  safeguard: administrative
  requirement: minimum_necessary

  data_assets:
    - model: fct_patient_visits
      phi_fields:
        - name: patient_name
          classification: restricted
          access: [attending_physician, compliance_officer]
          masking: full

        - name: patient_dob
          classification: restricted
          access: [clinical_staff, billing_staff]
          masking: year_only

        - name: diagnosis_code
          classification: confidential
          access: [clinical_staff]
          masking: none
          audit: all_access

        - name: visit_date
          classification: internal
          access: [all_staff]
          masking: none

  audit_requirements:
    - log_all_phi_access: true
    - log_all_queries: true
    - retention: 6_years
    - review_cycle: quarterly

  breach_detection:
    - alert_on_unauthorized_phi_access: true
    - alert_on_bulk_export: true
    - alert_on_after_hours_access: true
```

### Example C: Change Management Runbook

```markdown
# Change Management Runbook: Schema Changes

## Classification

### Breaking Change
Any change that could cause a downstream consumer to fail:
- Column rename
- Column removal
- Data type change (narrowing)
- Grain change
- Nullability change (adding NOT NULL to existing column)

### Non-Breaking Change
Changes that add capability without breaking existing consumers:
- New column
- New table
- Data type widening (INT → BIGINT)
- Adding nullable column
- New metric or dimension

## Process

### Breaking Changes
1. **Design** (Day 0)
   - Document rationale
   - Identify all affected consumers via lineage
   - Propose migration path

2. **Announce** (Day 0)
   - Post to #data-changes Slack
   - Update catalog with deprecation notice
   - Email affected team leads

3. **Soft Period** (Day 0–30)
   - Maintain old and new schema simultaneously
   - Old schema marked deprecated
   - Monitor consumer migration

4. **Approval** (Day 30)
   - Confirm >90% of consumers migrated
   - Get architect approval
   - Schedule hard cutover

5. **Hard Cutover** (Day 30+)
   - Remove old schema
   - Update documentation
   - Archive old contract version

### Non-Breaking Changes
1. **PR** → Automated checks pass → Team lead approval → Deploy
2. **Notification** → Auto-post to #data-changes
3. **Catalog** → Auto-updated
```

---

## 14. ModelBox AI Integration Opportunities

### Feature 1: Auto-Generate Governance Metadata from Models

**Input:** ModelBox AI generates a schema.

**Auto-Output:**
```yaml
# Auto-generated from ModelBox schema
governance_metadata:
  model: fct_orders

  auto_detected:
    primary_key: order_id
    foreign_keys:
      - customer_id → dim_customers.customer_id
      - product_id → dim_products.product_id

    pii_candidates:
      - customer_email (pattern: *email*)
      - customer_phone (pattern: *phone*)

    naming_compliance:
      - table_name: PASS (finance_revenue_fact)
      - column_names: PASS (order_total_amount)
      - pk_name: PASS (order_id)

    suggested_tier: tier_2_important
    suggested_owner: "Assign owner in ModelBox UI"

  auto_generated_contract:
    format: opendatacontract
    file: contracts/auto_fct_orders.yml

  auto_generated_documentation:
    business_glossary_entry: |
      "Orders Fact Table: Contains all customer orders with 
       line-item detail. Grain: order_id. Updated hourly."
```

### Feature 2: Schema Diff → Governance Impact Report

**Input:** User modifies a model in ModelBox.

**Auto-Output:**
```yaml
impact_report:
  change: "Added column: payment_method"
  type: non_breaking

  governance_actions_required:
    - action: classify_column
      column: payment_method
      options: [public, internal, confidential]
      recommendation: internal

    - action: update_contract
      contract: fct_orders_v2.1.0
      change: minor_version_bump (2.1.0 → 2.2.0)

    - action: notify_consumers
      affected: [revenue_dashboard, payment_api]
      message: "New column available: payment_method"

    - action: update_lineage
      add: payment_method → downstream_models

  auto_generated_artifacts:
    - opendatacontract_update
    - dbt_model_yml_update
    - business_glossary_entry
    - stakeholder_notification_draft
```

### Feature 3: Naming Standard Validator

**Real-time feedback as user designs in ModelBox:**
```
User types: "orders_fact_table"
ModelBox suggests: "finance_orders_fact" (per naming standard: {domain}_{entity}_{type})

User types: "total"
ModelBox suggests: "order_total_amount" (per naming standard: {attribute}_{modifier})

User types: "id"
ModelBox suggests: "order_id" (per naming standard: {entity}_id for PK)
```

### Feature 4: PII Auto-Classification

**During model design:**
```
ModelBox detects column: "customer_email_address"
→ Auto-tags: classification: confidential
→ Auto-suggests: masking: partial (show domain only)
→ Auto-adds: access_policy: restricted_to_support_and_marketing
→ Auto-generates: GDPR compliance note
```

### Feature 5: "Spot the Flaw" — Governance Edition

**Challenge:** Given a model and its governance metadata, identify issues.

```yaml
# Flawed governance package (presented to student)
model: fct_orders
metadata:
  owner: null                    # ❌ MISSING: No owner
  tier: null                     # ❌ MISSING: No tier assigned
  description: "Orders table"    # ❌ WEAK: Not descriptive

columns:
  - name: customer_email
    # ❌ MISSING: No PII classification
    # ❌ MISSING: No access control

  - name: order_total
    # ❌ MISSING: No quality rules (could be negative?)

contracts:
  - version: 1.0.0
    # ❌ ISSUE: Version 1.0.0 for 3 years, no review date
    # ❌ ISSUE: No SLA defined
    # ❌ ISSUE: No deprecation policy
```

**AI Tutor Response:**
```
"I see several governance issues in this package:

1. No owner assigned. If this model breaks on a weekend, who is paged?
   Every production model must have an owner and a steward.

2. No tier assigned. Is this a critical financial metric or an 
   experimental table? Without a tier, we can not apply appropriate 
   governance controls.

3. customer_email lacks PII classification. This is a regulatory 
   risk. It should be tagged 'confidential' with partial masking 
   and restricted access.

4. order_total has no quality rules. Can it be negative? Null? 
   Every financial measure should have non-negative and non-null checks.

5. The contract has no review date. Governance is not 'set and forget.'
   Contracts should be reviewed at least annually, or quarterly for 
   Tier 1 assets.

6. No SLA means no accountability. Consumers need to know freshness 
   expectations and who to contact if data is stale."
```

### Feature 6: Multi-Format Governance Export

**From one ModelBox schema, export governance artifacts:**
```
ModelBox Schema ──┬──→ OpenDataContract YAML
                  ├──→ dbt Model YAML (with tests + contracts)
                  ├──→ Collibra Business Asset JSON
                  ├──→ DataHub Metadata Event (MCP)
                  ├──→ Business Glossary Markdown
                  ├──→ Access Control Policy (RBAC SQL)
                  └──→ Compliance Mapping (GDPR/HIPAA/SOC2)
```

---

## 15. Course Module: Governance & Contract Mastery

### Module Outline (8-Week Course)

#### Week 1: Governance Foundations
- What is data governance and why it fails
- The governance maturity model (ad-hoc → defined → managed → optimized)
- Governance vs. agility: finding the balance
- **Lab:** Assess a real organization's governance maturity

#### Week 2: Policies, Standards & Processes
- Writing effective policies (specific, enforceable, automatable)
- Naming standards, modeling standards, documentation standards
- Change management workflows
- **Lab:** Design a naming standard and implement it in sqlfluff

#### Week 3: Data Contracts (OpenDataContract, Avro, Protobuf)
- Contract architecture: schema, quality, SLA, ownership
- Writing OpenDataContract YAML
- Converting contracts to dbt contracts, Avro, Protobuf
- Contract lifecycle: draft → active → deprecated → sunset
- **Lab:** Write a complete data contract for a fact table

#### Week 4: Metadata Management & Business Glossaries
- The metadata hierarchy (business, technical, operational, governance)
- Building a business glossary
- Auto-generating documentation from code
- Catalog integration (DataHub, Atlan)
- **Lab:** Build a business glossary with lineage mapping

#### Week 5: PII, Compliance & Security
- PII classification frameworks
- Regulatory mapping: GDPR, HIPAA, SOC 2, BCBS 239
- Column-level security and masking
- Audit trails and evidence collection
- **Lab:** Classify a schema for HIPAA compliance

#### Week 6: Lineage & Impact Analysis
- Designing lineage systems
- Column-level vs table-level lineage
- Impact analysis for schema changes
- Automated consumer notification
- **Lab:** Perform impact analysis on a breaking change

#### Week 7: Governance Operating Models
- Centralized vs federated vs data mesh
- The hybrid model (recommended)
- Role definitions: owner, steward, custodian, consumer
- Governance councils and decision rights
- **Lab:** Design a governance operating model for a 500-person company

#### Week 8: Capstone Project
- **Scenario:** A fintech company is preparing for a SOC 2 Type II audit. They have 200+ dbt models, 5 BI tools, and no formal governance. Revenue numbers conflict across dashboards. PII is scattered and unclassified.
- **Task:** Design and implement a complete governance framework.
- **Deliverables:**
  - Governance policy document
  - Naming and modeling standards
  - Data contracts for Tier 1 assets
  - PII classification and access control plan
  - Business glossary
  - Change management runbook
  - Audit evidence package

### Assessment Rubric

| Criteria | Weight | Excellent (A) | Good (B) | Needs Work (C) |
|----------|--------|--------------|----------|----------------|
| Policy Design | 15% | Policies are specific, automatable, and pragmatic | Mostly good, minor gaps | Vague or unenforceable |
| Contract Quality | 20% | Complete contracts with schema, quality, SLA, ownership | Good contracts, minor omissions | Incomplete or incorrect |
| Compliance Mapping | 15% | Accurate regulatory mapping with controls | Mostly accurate, minor gaps | Incorrect or missing controls |
| Lineage & Impact | 15% | Complete lineage, accurate impact analysis | Good lineage, minor gaps | Incomplete or inaccurate |
| Operating Model | 15% | Realistic, scalable governance model | Good model, minor feasibility issues | Unrealistic or incomplete |
| Documentation | 10% | Clear, professional, stakeholder-ready | Good, minor clarity issues | Unclear or unprofessional |
| Automation | 10% | CI/CD integration, automated checks | Some automation, manual gaps | Fully manual |

---

## Appendix: Quick Reference Card

### Governance Checklist for New Models

**Before promoting a model to production:**
- [ ] Owner and steward assigned
- [ ] Tier assigned (Tier 1/2/3/4)
- [ ] Description written (business + technical)
- [ ] All columns documented
- [ ] Naming standard compliance verified
- [ ] PII classification complete
- [ ] Data contract published
- [ ] Quality tests implemented
- [ ] Lineage documented
- [ ] Downstream consumers identified
- [ ] Access control configured
- [ ] Review cycle scheduled
- [ ] Catalog entry created

### The 5 Governance Questions Every Model Must Answer

1. **Who owns it?** (Owner + steward + backup)
2. **How important is it?** (Tier + SLA + business impact)
3. **What does it mean?** (Business glossary + semantic definitions)
4. **How is it protected?** (PII classification + access control + retention)
5. **What happens when it changes?** (Contract + lineage + change management)

### Governance Maturity Model

| Level | Name | Characteristics |
|-------|------|----------------|
| 1 | **Ad-hoc** | No governance, reactive, tribal knowledge |
| 2 | **Defined** | Policies exist on paper, manual enforcement |
| 3 | **Managed** | Automated checks in CI/CD, catalog in use |
| 4 | **Optimized** | Self-service governance, domain ownership, continuous improvement |
| 5 | **Intelligent** | AI-assisted classification, predictive quality, autonomous remediation |

---

*Document compiled for ModelBox AI product strategy and educational course development. Based on 2026 market research of 43+ data modeling job postings and governance implementations.*
