# Data Quality Engineering: A Comprehensive Breakdown

> **Status: research input — NOT IMPLEMENTED.**
>
> This document is an input to planning, not a description of shipped
> behaviour, and nothing in it should be read as a specification or a
> commitment. Promoting any part of it to the roadmap requires an ADR.
>
> Quarantined here on 2026-08-11 (Sprint 1, finding M10). Four unimplemented
> research documents sitting alongside the PRD is how the claim drift catalogued
> in `../PROJECT_STATE_REPORT.md` §2 arose. `README.md`, `PRD_TRD_v2.md` and the
> release notes are reserved for promises the code keeps.

## Including Modern Best Practices for ModelBox AI Product Strategy & Course Development

**Research Context:** Based on deep analysis of 43+ data modeling job postings (July–August 2026), data quality engineering appeared as a secondary responsibility in **~55% of roles** and is described as **inseparable from modern data modeling**. It is the implementation layer beneath governance — where policies become automated tests and contracts become enforceable guarantees.

---

## Table of Contents
1. What Is Data Quality Engineering in the Modeling Context?
2. Why Data Quality Is the #1 Trust Problem in 2026
3. The Data Quality Framework: Dimensions, Metrics & Tests
4. Modern Testing Stacks (2026)
5. Data Contracts as Quality Enforcement
6. Anomaly Detection & Observability
7. Quality in CI/CD Pipelines
8. Root Cause Analysis & Incident Response
9. Synthetic Data for Quality Testing
10. Anti-Patterns & Common Failures
11. Practical Examples & Templates
12. ModelBox AI Integration Opportunities
13. Course Module: Data Quality Engineering Mastery

---

## 1. What Is Data Quality Engineering in the Modeling Context?

**Data Quality Engineering** is the discipline of designing, implementing, and maintaining automated systems that verify data conforms to expected standards of accuracy, completeness, consistency, timeliness, validity, and uniqueness — **at the point of modeling**.

It is not a separate phase. It is not "testing after the fact." In modern data stacks, **quality is co-designed with the model**.

### The Quality-Modeling Stack

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
│  QUALITY LAYER  ←── YOU ARE HERE                            │
│  Tests, Assertions, Anomaly Detection, Observability        │
├─────────────────────────────────────────────────────────────┤
│  MODELING LAYER                                             │
│  Conceptual, Logical, Physical, Dimensional Models          │
├─────────────────────────────────────────────────────────────┤
│  ENGINEERING LAYER                                          │
│  dbt, Pipelines, ETL/ELT, Storage                           │
└─────────────────────────────────────────────────────────────┘
```

### Quality vs. Testing vs. Validation: The Distinction

| Concept | Definition | When It Happens | Example |
|---------|-----------|-----------------|---------|
| **Data Quality** | The degree to which data meets business requirements | Continuous, measured over time | "Our customer data is 99.7% complete" |
| **Data Testing** | Automated assertions that verify specific conditions | At build time, on schedule, or on-demand | "PRIMARY KEY is unique and non-null" |
| **Data Validation** | Checking that data conforms to schema/rules | At ingestion, transformation, or consumption | "Email field matches regex pattern" |
| **Data Observability** | Monitoring data health in production | Continuous, real-time | "Alert: revenue table hasn't updated in 3 hours" |
| **Anomaly Detection** | Identifying statistically unusual patterns | Continuous, ML-based | "Alert: order count dropped 40% vs. yesterday" |

**The modern approach:** All five are integrated into a single quality engineering practice.

---

## 2. Why Data Quality Is the #1 Trust Problem in 2026

### The Cost of Bad Data

| Impact Area | Cost Without Quality Engineering | Cost With Quality Engineering |
|-------------|---------------------------------|------------------------------|
| **Executive decisions** | $10M+ from wrong revenue numbers in board deck | Zero (caught before dashboard) |
| **Regulatory fines** | GDPR: up to 4% global revenue; HIPAA: up to $1.5M/year | Zero (PII classified and monitored) |
| **Customer trust** | Churn from incorrect billing, recommendations, or support | Zero (data validated at source) |
| **Engineering time** | 40% of data team time spent firefighting data issues | <10% (proactive detection) |
| **AI/ML failures** | Models trained on dirty data produce harmful predictions | Models validated against quality gates |

### The 2026 Quality Crisis

Modern data stacks have made it **easier than ever to produce bad data at scale**:

```
2020: 10 sources, manual QA, 3 analysts → "We know our data"
2023: 50 sources, dbt tests on 20% of models, 20 analysts → "We think our data is okay"
2026: 200+ sources, dbt tests on 60% of models, 100+ consumers, AI agents consuming data → "We have no idea what is broken"
```

**The new failure modes:**
- **Silent schema drift:** Upstream API changes column names; downstream models break without error
- **Cross-system inconsistency:** CRM says 100K customers; warehouse says 98K; no one knows which is right
- **Temporal anomalies:** Black Friday traffic looks like a DDoS attack to naive anomaly detectors
- **AI context poisoning:** AI agents consume stale or incorrect semantic definitions
- **Contract violation:** Producer promises freshness < 1h; consumer receives 6h-old data; no one is alerted

### Research Finding: Quality Is Now a Modeling Responsibility

From the 43 job postings analyzed:
- **72%** of Data Engineer roles mention "data quality" or "testing"
- **68%** of Analytics Engineer roles require dbt tests or Great Expectations
- **55%** of BI Engineer roles include "data validation" or "reconciliation"
- **45%** of Data Architect roles mention "quality frameworks" or "SLAs"

**The shift:** Quality is no longer a "data steward" or "QA team" responsibility. **The modeler writes the tests. The pipeline runs the tests. The catalog displays the results.**

---

## 3. The Data Quality Framework: Dimensions, Metrics & Tests

### The 6 Dimensions of Data Quality (DAMA-DMBOK)

```
┌─────────────────────────────────────────────────────────────┐
│              DATA QUALITY DIMENSIONS                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  ACCURACY   │  │ COMPLETENESS│  │ CONSISTENCY │        │
│  │             │  │             │  │             │        │
│  │ Data        │  │ Data is     │  │ Data is     │        │
│  │ correctly   │  │ not missing │  │ uniform     │        │
│  │ represents  │  │ values      │  │ across      │        │
│  │ reality     │  │             │  │ systems     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  VALIDITY   │  │ TIMELINESS  │  │  UNIQUENESS │        │
│  │             │  │             │  │             │        │
│  │ Data        │  │ Data is     │  │ No          │        │
│  │ conforms    │  │ up-to-date  │  │ duplicate   │        │
│  │ to format/  │  │ when needed │  │ records     │        │
│  │ type rules  │  │             │  │             │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Dimension Deep-Dive with Tests

#### A. Accuracy
**Definition:** Data correctly represents the real-world entity or event it describes.

```yaml
# Accuracy tests
tests:
  - name: revenue_matches_general_ledger
    type: reconciliation
    source: fct_orders.revenue
    target: finance_gl.revenue
    tolerance: 0.005  # 0.5% variance allowed

  - name: customer_count_matches_crm
    type: reconciliation
    source: dim_customers.active_count
    target: salesforce.contact_count
    tolerance: 0.02  # 2% variance allowed

  - name: order_total_sanity_check
    type: statistical
    column: order_total
    expected_distribution: normal
    mean_range: [45, 150]  # USD
    std_dev_range: [20, 100]
```

#### B. Completeness
**Definition:** All required data is present; no unexpected nulls or missing values.

```yaml
# Completeness tests
tests:
  - name: no_null_primary_keys
    type: not_null
    columns: [order_id, customer_id]

  - name: customer_email_present
    type: not_null
    column: email
    condition: "lifecycle_stage != 'prospect'"

  - name: order_total_not_null_for_completed
    type: not_null
    column: order_total
    condition: "status = 'completed'"

  - name: completeness_threshold
    type: completeness_rate
    column: phone_number
    threshold: 0.85  # At least 85% of records have phone
```

#### C. Consistency
**Definition:** Data is uniform across systems, tables, and time periods.

```yaml
# Consistency tests
tests:
  - name: customer_segment_consistent
    type: cross_table
    source: dim_customers.segment
    target: fct_orders.customer_segment
    match_rate: 1.0  # Must match 100%

  - name: revenue_consistent_across_marts
    type: cross_table
    source: mart_monthly_revenue.total
    target: mart_daily_revenue.monthly_total
    tolerance: 0.001

  - name: currency_consistent
    type: custom
    expression: |
      CASE 
        WHEN country = 'US' AND currency != 'USD' THEN FALSE
        WHEN country = 'UK' AND currency != 'GBP' THEN FALSE
        WHEN country = 'DE' AND currency != 'EUR' THEN FALSE
        ELSE TRUE
      END
```

#### D. Validity
**Definition:** Data conforms to defined formats, types, and business rules.

```yaml
# Validity tests
tests:
  - name: email_format_valid
    type: regex
    column: email
    pattern: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

  - name: order_status_valid
    type: accepted_values
    column: order_status
    values: ['pending', 'completed', 'cancelled', 'refunded']

  - name: order_total_positive
    type: range
    column: order_total
    min: 0

  - name: order_date_in_past
    type: range
    column: order_date
    max: CURRENT_DATE

  - name: zip_code_valid_us
    type: regex
    column: zip_code
    condition: "country = 'US'"
    pattern: '^[0-9]{5}(-[0-9]{4})?$'
```

#### E. Timeliness
**Definition:** Data is available when needed and reflects the current state.

```yaml
# Timeliness tests
tests:
  - name: orders_freshness
    type: recency
    column: ordered_at
    max_age: 1 hour

  - name: daily_snapshot_on_time
    type: schedule
    expected_cron: '0 6 * * *'  # 6 AM daily
    max_delay: 30 minutes

  - name: no_stale_partitions
    type: partition_freshness
    table: fct_orders
    partition_column: order_date
    max_stale_partitions: 2

  - name: pipeline_duration_sla
    type: duration
    pipeline: daily_etl
    max_duration: 2 hours
```

#### F. Uniqueness
**Definition:** No duplicate records exist where uniqueness is required.

```yaml
# Uniqueness tests
tests:
  - name: order_id_unique
    type: unique
    column: order_id

  - name: customer_email_unique
    type: unique
    column: email
    condition: "status != 'deleted'"

  - name: no_duplicate_orders_same_minute
    type: composite_unique
    columns: [customer_id, order_total, ordered_at]
    granularity: minute

  - name: slowly_changing_dimension_integrity
    type: scd_validity
    table: dim_customers
    key_column: customer_id
    valid_from: valid_from_date
    valid_to: valid_to_date
    check_gaps: false
    check_overlaps: true
```

### Quality Scorecard

```yaml
# quality_scorecard.yml
scorecard:
  model: fct_orders

  dimensions:
    - name: accuracy
      weight: 0.25
      tests:
        - revenue_matches_gl: PASS
        - customer_count_matches_crm: PASS
      score: 100

    - name: completeness
      weight: 0.20
      tests:
        - no_null_primary_keys: PASS
        - customer_email_present: PASS (98.5%)
      score: 98.5

    - name: consistency
      weight: 0.15
      tests:
        - customer_segment_consistent: PASS
        - revenue_consistent_across_marts: PASS
      score: 100

    - name: validity
      weight: 0.15
      tests:
        - email_format_valid: PASS (99.2%)
        - order_status_valid: PASS
      score: 99.2

    - name: timeliness
      weight: 0.15
      tests:
        - orders_freshness: PASS
        - daily_snapshot_on_time: FAIL (35 min delay)
      score: 85

    - name: uniqueness
      weight: 0.10
      tests:
        - order_id_unique: PASS
        - no_duplicate_orders: PASS
      score: 100

  overall_score: 97.2
  grade: A
  status: certified
  last_evaluated: 2026-08-10T08:00:00Z
```

---

## 4. Modern Testing Stacks (2026)

### The Testing Tool Landscape

| Tool | Category | Best For | When to Use |
|------|----------|----------|-------------|
| **dbt Tests** | Schema & Row-Level | dbt-native teams, standard assertions | Primary testing framework for dbt projects |
| **dbt-expectations** | Advanced Row-Level | Complex validations on dbt models | When dbt built-ins are insufficient |
| **Great Expectations (GX)** | Enterprise Validation | Cross-platform, comprehensive suites | Large orgs, multi-tool environments |
| **Soda** | Data Contract Quality | Contract-driven, self-serve | Teams adopting data contracts |
| **Monte Carlo** | Observability | Production monitoring, anomaly detection | When you need 24/7 automated monitoring |
| **Metaplane** | Observability | Small-to-mid modern stacks | Easy setup, dbt integration |
| **Deequ (Apache Spark)** | Big Data Quality | Spark-based pipelines, large scale | AWS/GCP environments with Spark |
| **Pandera** | DataFrame Validation | Python data pipelines, Pandas/Polars | Python-heavy analytics workflows |

### Stack A: The dbt-Native Stack (Most Common)

```yaml
# dbt built-in tests (schema.yml)
models:
  - name: fct_orders
    columns:
      - name: order_id
        tests:
          - unique
          - not_null

      - name: customer_id
        tests:
          - not_null
          - relationships:
              to: ref('dim_customers')
              field: customer_id

      - name: order_total
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0

      - name: order_status
        tests:
          - accepted_values:
              values: ['pending', 'completed', 'cancelled', 'refunded']

      - name: ordered_at
        tests:
          - not_null
          - dbt_utils.recency:
              datepart: hour
              field: ordered_at
              interval: 1
```

```yaml
# dbt-expectations (advanced tests)
models:
  - name: fct_orders
    tests:
      - dbt_expectations.expect_table_row_count_to_equal_other_table:
          compare_model: ref('stg_orders')

      - dbt_expectations.expect_column_values_to_be_between:
          column: order_total
          min_value: 0
          max_value: 100000

      - dbt_expectations.expect_column_values_to_match_regex:
          column: email
          regex: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

      - dbt_expectations.expect_column_pair_values_to_be_equal:
          column_A: order_total
          column_B: calculated_total

      - dbt_expectations.expect_column_values_to_not_be_null:
          column: customer_id
          row_condition: "order_status != 'guest_checkout'"
```

### Stack B: Great Expectations (Enterprise)

```json
{
  "expectation_suite_name": "fct_orders_suite",
  "expectations": [
    {
      "expectation_type": "expect_column_values_to_be_unique",
      "kwargs": { "column": "order_id" }
    },
    {
      "expectation_type": "expect_column_values_to_not_be_null",
      "kwargs": { "column": "order_id" }
    },
    {
      "expectation_type": "expect_column_values_to_be_between",
      "kwargs": {
        "column": "order_total",
        "min_value": 0,
        "max_value": 100000
      }
    },
    {
      "expectation_type": "expect_column_values_to_be_in_set",
      "kwargs": {
        "column": "order_status",
        "value_set": ["pending", "completed", "cancelled", "refunded"]
      }
    },
    {
      "expectation_type": "expect_column_pair_values_to_be_equal",
      "kwargs": {
        "column_A": "order_total",
        "column_B": "calculated_total",
        "ignore_row_if": "either_value_is_missing"
      }
    },
    {
      "expectation_type": "expect_table_row_count_to_be_between",
      "kwargs": {
        "min_value": 1000,
        "max_value": 10000000
      }
    },
    {
      "expectation_type": "expect_column_values_to_match_regex",
      "kwargs": {
        "column": "email",
        "regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
      }
    }
  ],
  "meta": {
    "version": "1.0.0",
    "owner": "analytics_engineering",
    "tier": "tier_1_critical"
  }
}
```

### Stack C: Soda (Data Contract Quality)

```yaml
# checks/fct_orders.yml
checks for fct_orders:
  # Schema checks
  - schema:
      fail:
        when required column missing:
          [order_id, customer_id, order_total, order_status, ordered_at]
        when wrong column type:
          order_id: uuid
          order_total: decimal
          ordered_at: timestamp

  # Row-level checks
  - missing_count(order_id) = 0
  - missing_count(customer_id) = 0
  - duplicate_count(order_id) = 0
  - invalid_count(order_status) = 0:
      valid values: [pending, completed, cancelled, refunded]
  - min(order_total) >= 0
  - max(order_total) < 100000

  # Freshness
  - freshness(ordered_at) < 1h

  # Reconciliation
  - row_count same as stg_orders
  - sum(order_total) diff with finance_gl.revenue < 0.5%

  # Anomaly detection
  - anomaly score for row_count < 3
  - anomaly score for sum(order_total) < 3
```

### Stack D: The Complete Modern Stack (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│  COMPLETE MODERN QUALITY STACK                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  LAYER 1: BUILD-TIME TESTS (Prevent bad code)               │
│  ├─ dbt built-in tests (unique, not_null, relationships)    │
│  ├─ dbt-expectations (advanced row-level)                   │
│  ├─ Soda checks (contract validation)                       │
│  └─ sqlfluff (SQL quality, naming standards)                │
│                                                             │
│  LAYER 2: RUNTIME VALIDATION (Catch production issues)      │
│  ├─ dbt tests run on every pipeline execution               │
│  ├─ Great Expectations (comprehensive suites)               │
│  ├─ Soda (scheduled scans)                                  │
│  └─ Custom reconciliation jobs (cross-system)               │
│                                                             │
│  LAYER 3: OBSERVABILITY (Monitor continuously)              │
│  ├─ Monte Carlo (anomaly detection, lineage-aware)          │
│  ├─ Metaplane (easy setup, dbt integration)                 │
│  ├─ Custom dashboards (freshness, volume, schema drift)     │
│  └─ PagerDuty/Opsgenie (alerting)                           │
│                                                             │
│  LAYER 4: SYNTHETIC TESTING (Validate before production)    │
│  ├─ Synthetic seed data (ModelBox AI)                       │
│  ├─ dbt unit tests (test business logic)                    │
│  └─ Integration tests (end-to-end pipeline validation)      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Data Contracts as Quality Enforcement

### The Contract-Quality Bridge

Data contracts are not just schema definitions — they are **executable quality specifications**.

```yaml
# OpenDataContract with embedded quality rules
apiVersion: opendatacontract/v1.0
kind: DataContract
id: orders-fact-v2.1.0

schema:
  - name: order_id
    type: uuid
    required: true
    primaryKey: true

  - name: order_total
    type: decimal(18,2)
    required: true
    quality:
      - rule: non_negative
        type: range
        min: 0

      - rule: reasonable_max
        type: range
        max: 100000

      - rule: matches_line_items
        type: cross_column
        expression: "order_total = SUM(line_item_total)"

  - name: order_status
    type: string
    required: true
    quality:
      - rule: valid_status
        type: enum
        values: [pending, completed, cancelled, refunded]

  - name: ordered_at
    type: timestamp
    required: true
    quality:
      - rule: not_future
        type: range
        max: CURRENT_TIMESTAMP

      - rule: recent
        type: recency
        max_age: 1 hour

# Contract-level quality
quality:
  freshness:
    - table: fct_orders
      threshold: 1h

  volume:
    - table: fct_orders
      min_rows: 1000
      max_rows: 10000000
      anomaly_detection: true

  schema:
    - drift_detection: true
      allowed_changes: [add_column, widen_type]
      blocked_changes: [drop_column, rename_column, narrow_type]

  reconciliation:
    - source: raw_orders
      target: fct_orders
      tolerance: 0.001

  lineage:
    - upstream: [raw_orders, raw_customers]
    - downstream: [mart_monthly_revenue, revenue_metric]
```

### Contract Validation in CI/CD

```yaml
# .github/workflows/contract_validation.yml
name: Data Contract Validation

on:
  pull_request:
    paths:
      - 'models/**'
      - 'contracts/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate OpenDataContract Schema
        run: soda validate-contract contracts/*.yml

      - name: Run dbt Tests
        run: |
          dbt deps
          dbt compile
          dbt test --select state:modified+

      - name: Run Great Expectations
        run: great_expectations checkpoint run fct_orders_checkpoint

      - name: Reconciliation Tests
        run: python tests/reconciliation/revenue_reconciliation.py

      - name: Schema Drift Detection
        run: soda scan -c checks/schema_drift.yml

      - name: Post Results to PR
        uses: actions/github-script@v7
        with:
          script: |
            const results = require('./quality_results.json');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `Quality Results: ${results.overall_score}/100`
            });
```

---

## 6. Anomaly Detection & Observability

### Types of Anomalies in Data

| Anomaly Type | Description | Example | Detection Method |
|-------------|-------------|---------|-----------------|
| **Volume** | Unexpected row count | Orders dropped 50% vs. yesterday | Statistical threshold, z-score |
| **Freshness** | Data not updated on schedule | Revenue table 6 hours stale | Schedule monitoring, recency tests |
| **Schema** | Unexpected structural changes | Column renamed, type changed | Schema diff, contract validation |
| **Distribution** | Unusual value distributions | Average order value spiked 300% | Statistical tests, ML models |
| **Null Rate** | Sudden increase in nulls | Customer email null rate jumped from 2% to 40% | Rate monitoring, threshold alerts |
| **Cardinality** | Unexpected unique value counts | New product category appeared | Reference data monitoring |
| **Cross-System** | Inconsistency between systems | CRM shows 100K customers; warehouse shows 95K | Reconciliation jobs |

### Anomaly Detection Implementation

```python
# anomaly_detection/orders_volume.py
import pandas as pd
from scipy import stats
import numpy as np

def detect_volume_anomaly(current_count, historical_counts,
                          threshold_z_score=3.0,
                          threshold_iqr_multiplier=1.5):
    # Method 1: Z-Score
    mean = historical_counts.mean()
    std = historical_counts.std()
    z_score = abs((current_count - mean) / std) if std > 0 else 0

    # Method 2: IQR
    q1 = historical_counts.quantile(0.25)
    q3 = historical_counts.quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - threshold_iqr_multiplier * iqr
    upper_bound = q3 + threshold_iqr_multiplier * iqr

    is_anomaly = (
        z_score > threshold_z_score or
        current_count < lower_bound or
        current_count > upper_bound
    )

    severity = "high" if z_score > 5 else "medium" if z_score > 3 else "low"

    return {
        "is_anomaly": is_anomaly,
        "current_count": current_count,
        "historical_mean": mean,
        "z_score": z_score,
        "iqr_lower": lower_bound,
        "iqr_upper": upper_bound,
        "severity": severity,
        "recommended_action": "investigate" if is_anomaly else "none"
    }

# Usage
historical = pd.Series([1200, 1150, 1300, 1250, 1180, 1220, 1280, 1190, 1210, 1240])
current = 600  # 50% drop
result = detect_volume_anomaly(current, historical)
# Result: is_anomaly=True, severity="high"
```

### Seasonality-Aware Anomaly Detection

```python
def detect_seasonal_anomaly(current_value, historical_df,
                            seasonality_columns=['day_of_week', 'is_holiday']):
    from datetime import datetime

    current_date = datetime.now()
    current_dow = current_date.strftime('%A')
    current_is_holiday = is_holiday(current_date)

    # Filter historical to same seasonality context
    comparable = historical_df[
        (historical_df['day_of_week'] == current_dow) &
        (historical_df['is_holiday'] == current_is_holiday)
    ]

    if len(comparable) < 5:
        comparable = historical_df  # Fallback

    return detect_volume_anomaly(current_value, comparable['value'])

# Example: Black Friday
# Unadjusted: 10x normal volume → anomaly!
# Seasonality-adjusted: Compare to last 3 Black Fridays → normal
```

### Observability Dashboard Metrics

```yaml
# observability/dashboard.yml
dashboard:
  name: data_health_overview
  refresh: 5_minutes

  panels:
    - title: "Overall Data Quality Score"
      type: gauge
      query: |
        SELECT AVG(quality_score) 
        FROM quality_scorecard 
        WHERE date = CURRENT_DATE
      thresholds:
        - min: 95, color: green
        - min: 85, color: yellow
        - min: 0, color: red

    - title: "Failed Tests (Last 24h)"
      type: table
      query: |
        SELECT model, test_name, failed_at, severity
        FROM test_results
        WHERE status = 'failed'
        AND failed_at > CURRENT_DATE - 1
        ORDER BY failed_at DESC

    - title: "Freshness Heatmap"
      type: heatmap
      query: |
        SELECT table_name, 
               EXTRACT(HOUR FROM CURRENT_TIMESTAMP - last_updated) as hours_stale
        FROM table_metadata
        WHERE tier IN ('tier_1', 'tier_2')

    - title: "Volume Anomalies (Last 7 Days)"
      type: line_chart
      query: |
        SELECT date, table_name, row_count, expected_range_min, expected_range_max
        FROM volume_anomalies
        WHERE date > CURRENT_DATE - 7

    - title: "Schema Drift Alerts"
      type: alert_list
      query: |
        SELECT table_name, change_type, detected_at, approved
        FROM schema_changes
        WHERE approved = false
        AND detected_at > CURRENT_DATE - 7
```

---

## 7. Quality in CI/CD Pipelines

### The Quality Gates Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  DEVELOPER OPENS PR                                         │
├─────────────────────────────────────────────────────────────┤
│  GATE 1: CODE QUALITY                                       │
│  ├─ sqlfluff lint (naming standards, SQL quality)           │
│  ├─ dbt compile (syntax validation)                         │
│  └─ yaml lint (contract/schema validation)                  │
│  [FAIL = block PR]                                          │
├─────────────────────────────────────────────────────────────┤
│  GATE 2: UNIT TESTS                                         │
│  ├─ dbt tests on modified models                            │
│  ├─ dbt-expectations on critical columns                    │
│  ├─ Soda checks on contract rules                           │
│  └─ Custom business logic tests                             │
│  [FAIL = block PR]                                          │
├─────────────────────────────────────────────────────────────┤
│  GATE 3: INTEGRATION TESTS                                  │
│  ├─ Run full pipeline in staging                            │
│  ├─ Reconciliation tests (source vs. target)                │
│  ├─ Cross-model consistency checks                          │
│  └─ Performance tests (query runtime < SLA)                 │
│  [FAIL = block PR]                                          │
├─────────────────────────────────────────────────────────────┤
│  GATE 4: IMPACT ANALYSIS                                    │
│  ├─ Identify downstream consumers                           │
│  ├─ Assess breaking vs. non-breaking                        │
│  ├─ Notify affected teams                                   │
│  └─ Require approval for breaking changes                   │
│  [BREAKING = require architect approval]                    │
├─────────────────────────────────────────────────────────────┤
│  GATE 5: DOCUMENTATION                                      │
│  ├─ dbt docs generated and reviewed                         │
│  ├─ Business glossary updated                               │
│  └─ Catalog sync verified                                   │
│  [INCOMPLETE = block PR]                                    │
├─────────────────────────────────────────────────────────────┤
│  APPROVED → MERGE TO MAIN → DEPLOY TO PRODUCTION            │
└─────────────────────────────────────────────────────────────┘
```

### GitHub Actions Workflow

```yaml
# .github/workflows/data_quality.yml
name: Data Quality Pipeline

on:
  pull_request:
    branches: [main]
    paths:
      - 'models/**'
      - 'tests/**'
      - 'contracts/**'
      - 'seeds/**'

jobs:
  code-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SQL Lint
        run: sqlfluff lint models/ --format github-annotation
      - name: YAML Validation
        run: yamllint .
      - name: dbt Compile
        run: |
          dbt deps
          dbt compile

  unit-tests:
    needs: code-quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run dbt Tests
        run: |
          dbt deps
          dbt test --select state:modified+
      - name: Run dbt-expectations
        run: dbt test --select package:dbt_expectations
      - name: Run Soda Checks
        run: soda scan -d warehouse -c soda_configuration.yml checks/
      - name: Upload Test Results
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: target/test-results/

  integration-tests:
    needs: unit-tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Full Pipeline (Staging)
        run: |
          dbt deps
          dbt build --target staging --full-refresh
      - name: Reconciliation Tests
        run: python tests/reconciliation/run_all.py --target staging
      - name: Performance Tests
        run: python tests/performance/run_all.py --target staging

  impact-analysis:
    needs: integration-tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate Impact Report
        run: python scripts/impact_analysis.py --pr ${{ github.event.pull_request.number }}
      - name: Post Impact Report to PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('impact_report.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: report
            });

  documentation:
    needs: impact-analysis
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate dbt Docs
        run: |
          dbt deps
          dbt docs generate
      - name: Deploy Docs
        run: aws s3 sync target/ s3://data-docs-bucket/
```

---

## 8. Root Cause Analysis & Incident Response

### The Data Incident Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│  1. DETECTION                                               │
│  ├─ Automated alert (Monte Carlo, Metaplane, custom)        │
│  ├─ Consumer complaint ("Dashboard looks wrong")            │
│  └─ Scheduled test failure                                  │
├─────────────────────────────────────────────────────────────┤
│  2. TRIAGE                                                  │
│  ├─ Assess severity (P0 = revenue-impacting, P1 = degraded) │
│  ├─ Identify owner (from catalog/governance registry)       │
│  └─ Create incident channel (Slack, PagerDuty)              │
├─────────────────────────────────────────────────────────────┤
│  3. INVESTIGATION                                           │
│  ├─ Check lineage (what changed upstream?)                  │
│  ├─ Check recent deployments (what code changed?)           │
│  ├─ Check source systems (is the raw data wrong?)           │
│  └─ Check pipeline logs (did a job fail silently?)          │
├─────────────────────────────────────────────────────────────┤
│  4. CONTAINMENT                                             │
│  ├─ Stop the bleeding (pause pipeline, revert bad data)     │
│  ├─ Communicate to consumers ("Data is stale, ETA fix")     │
│  └─ Document findings in incident log                       │
├─────────────────────────────────────────────────────────────┤
│  5. RESOLUTION                                              │
│  ├─ Fix root cause (code fix, source system fix, etc.)      │
│  ├─ Backfill/correct data if needed                         │
│  ├─ Re-run tests to verify fix                              │
│  └─ Update catalog and notify consumers                     │
├─────────────────────────────────────────────────────────────┤
│  6. POST-MORTEM                                             │
│  ├─ Document timeline, root cause, impact                   │
│  ├─ Identify preventive measures (new tests, alerts)        │
│  ├─ Update runbooks                                         │
│  └─ Schedule follow-up review                               │
└─────────────────────────────────────────────────────────────┘
```

### Root Cause Analysis Template

```markdown
# Data Incident Post-Mortem

## Metadata
- **Incident ID:** INC-2026-0842
- **Severity:** P1 (Degraded, non-revenue-impacting)
- **Detection:** Automated alert (Monte Carlo freshness anomaly)
- **Start Time:** 2026-08-10 03:15 UTC
- **End Time:** 2026-08-10 07:30 UTC
- **Duration:** 4h 15m
- **Owner:** Analytics Engineering Team
- **Reporter:** Monte Carlo Alert Bot

## Summary
The fct_orders table stopped updating at 03:15 UTC due to a silent failure 
in the Fivetran connector to Shopify. The connector status showed "Syncing" 
but no new records were being ingested. This caused downstream dashboards 
to display stale data from August 9.

## Timeline
- 03:15 UTC: Fivetran connector begins silent failure
- 03:45 UTC: dbt pipeline runs successfully (on stale data)
- 04:00 UTC: Monte Carlo detects freshness anomaly (orders table > 1h stale)
- 04:05 UTC: Alert fired to #data-alerts Slack channel
- 04:15 UTC: On-call engineer acknowledges alert
- 04:30 UTC: Engineer identifies Fivetran connector as root cause
- 05:00 UTC: Fivetran support ticket opened
- 06:00 UTC: Fivetran resolves connector issue
- 06:30 UTC: Manual sync triggered, backfill begins
- 07:30 UTC: Backfill complete, data freshness restored

## Impact
- **Dashboards Affected:** 3 (Executive Overview, Sales Daily, Marketing Funnel)
- **Users Affected:** ~50 (executives, sales managers, marketing analysts)
- **Data Staleness:** 4 hours
- **Incorrect Decisions:** None identified (caught before morning standup)
- **Financial Impact:** $0 (no revenue-impacting decisions made on stale data)

## Root Cause
**Primary:** Fivetran connector silent failure (status "Syncing" but no data flow)
**Contributing:** 
- No volume anomaly alert configured for raw_orders
- dbt pipeline succeeded on stale data (no freshness check on source)
- Weekend low-traffic period masked the issue longer

## Resolution
1. Fivetran connector reset and resynced
2. Backfill completed for missing 4-hour window
3. Downstream models refreshed

## Preventive Measures
- [ ] Add volume anomaly detection on raw_orders (Owner: Data Eng, Due: Aug 17)
- [ ] Add source-level freshness check in dbt (Owner: Analytics Eng, Due: Aug 17)
- [ ] Configure Fivetran health check webhook (Owner: Data Eng, Due: Aug 24)
- [ ] Update runbook: "Fivetran Silent Failure" (Owner: Data Eng, Due: Aug 17)
- [ ] Add weekend on-call rotation for data alerts (Owner: Manager, Due: Aug 31)

## Lessons Learned
1. "Syncing" status does not mean "syncing successfully" — always validate volume
2. Source-level freshness checks are as important as model-level freshness checks
3. Weekend low-traffic periods are higher risk for silent failures
```

---

## 9. Synthetic Data for Quality Testing

### Why Synthetic Data Matters for Quality Engineering

Testing data quality requires **data that exercises edge cases**:
- Null values in unexpected places
- Extreme outliers (negative revenue, 99-year-old customers)
- Boundary conditions (exactly at min/max thresholds)
- Invalid formats (malformed emails, future dates)
- Cross-system inconsistencies (CRM says A, warehouse says B)

**Production data often lacks these edge cases** (or they are rare). Synthetic data **guarantees** them.

### Synthetic Test Data Strategy

```yaml
# synthetic_test_data/orders_test_cases.yml
test_scenarios:
  - name: "normal_orders"
    description: "Baseline valid data"
    row_count: 1000
    generators:
      order_id: uuid()
      customer_id: uuid()
      order_total: random_decimal(10, 500, 2)
      order_status: weighted_choice([completed: 0.7, pending: 0.2, cancelled: 0.1])
      ordered_at: random_timestamp(last_30_days)
    expected_test_results:
      - all_validity_tests: PASS
      - all_completeness_tests: PASS

  - name: "edge_case_nulls"
    description: "Test null handling in optional fields"
    row_count: 100
    generators:
      order_id: uuid()
      customer_id: uuid()
      order_total: random_decimal(10, 500, 2)
      order_status: "completed"
      ordered_at: random_timestamp(last_30_days)
      promo_code: null(0.5)
      notes: null(0.8)
    expected_test_results:
      - promo_code_null_rate: ~50% (should not fail not_null test)
      - notes_null_rate: ~80% (should not fail not_null test)

  - name: "boundary_conditions"
    description: "Test min/max thresholds"
    row_count: 50
    generators:
      order_id: uuid()
      customer_id: uuid()
      order_total: choice([0, 0.01, 99999.99, 100000])
      order_status: "completed"
      ordered_at: choice([exactly_1_hour_ago, exactly_now, exactly_30_days_ago])
    expected_test_results:
      - min_order_total: PASS (>= 0)
      - max_order_total: PASS (< 100000)
      - freshness: PASS (within 1h)

  - name: "invalid_data"
    description: "Test that invalid data is caught by tests"
    row_count: 50
    generators:
      order_id: choice([null, "", "duplicate_id"])
      customer_id: uuid()
      order_total: choice([-100, null, 999999])
      order_status: choice(["shipped", "", null, "COMPLETED"])
      ordered_at: choice([null, "2027-01-01", "not-a-date"])
    expected_test_results:
      - unique_order_id: FAIL (duplicates + nulls)
      - not_null_order_id: FAIL (nulls)
      - positive_order_total: FAIL (negative + null)
      - valid_status: FAIL (invalid values)
      - not_future_ordered_at: FAIL (future date)

  - name: "cross_system_inconsistency"
    description: "Test reconciliation catches mismatches"
    row_count: 100
    generators:
      order_id: uuid()
      customer_id: uuid()
      order_total: 100
      order_status: "completed"
      ordered_at: random_timestamp(last_30_days)
    reconciliation_setup:
      source_system:
        table: crm_orders
        order_total: 105  # Intentionally different
    expected_test_results:
      - revenue_reconciliation: FAIL (5% variance > 0.5% tolerance)
```

### ModelBox AI Synthetic Data Integration

```python
# modelbox_synthetic_integration.py
"""
ModelBox AI generates synthetic seed data that exercises 
all quality test cases for a given schema.
"""

from modelbox import Schema, SyntheticDataGenerator

def generate_quality_test_dataset(schema: Schema) -> dict:
    generator = SyntheticDataGenerator(schema)

    datasets = {
        "valid_baseline": generator.generate(
            row_count=1000,
            strategy="realistic",
            distributions="match_production"
        ),
        "edge_cases": generator.generate(
            row_count=100,
            strategy="boundary",
            include_nulls=True,
            null_rate=0.3,
            extreme_values=True
        ),
        "invalid_data": generator.generate(
            row_count=50,
            strategy="invalid",
            violate_constraints=True,
            violate_types=True,
            violate_referential_integrity=True
        ),
        "reconciliation_mismatch": generator.generate(
            row_count=100,
            strategy="reconciliation_test",
            source_system_variance=0.05
        )
    }

    return datasets

# Usage
schema = Schema.from_modelbox("fct_orders")
test_datasets = generate_quality_test_dataset(schema)

for name, dataset in test_datasets.items():
    dataset.load_to_table(f"test_seed_{name}")
```

---

## 10. Anti-Patterns & Common Failures

### Anti-Pattern 1: The "Test Everything" Trap

**Bad:** Testing every column for everything.
```
# 500 tests on a 50-column table
# CI/CD takes 45 minutes
# Engineers skip tests to save time
# Tests become noise, not signal
```

**Good:** Risk-based testing.
```
# Tier 1 models: 100% PK/FK, 80% business-critical columns
# Tier 2 models: 100% PK, 50% business-critical columns
# Tier 3 models: 100% PK only
# Focus tests on:
#   - Financial calculations
#   - Customer-facing metrics
#   - Regulatory-reporting fields
#   - Join keys
```

### Anti-Pattern 2: The "Silent Failure"

**Bad:** Tests exist but no one is alerted when they fail.
```
# dbt test runs nightly
# Results logged to target/test-results/
# No one checks the logs
# Failed tests accumulate for weeks
# Dashboard has been wrong for 3 weeks
```

**Good:** Failed tests = alerts.
```
# dbt test results → PagerDuty/Slack
# P0 failures page on-call engineer
# P1 failures post to #data-alerts
# Daily digest of all failures
# Weekly quality score review
```

### Anti-Pattern 3: The "Brittle Test"

**Bad:** Tests that fail on legitimate business changes.
```
# Test: "row_count must be between 1000 and 10000"
# Black Friday: row_count = 50000 → TEST FAILS
# Engineer disables test
# Test is never re-enabled
```

**Good:** Dynamic, context-aware tests.
```
# Test: "row_count within 3 standard deviations of 30-day mean"
# Black Friday: mean adjusts, anomaly detector accounts for seasonality
# Test passes because 50000 is expected
# Test only fails on truly unexpected volume
```

### Anti-Pattern 4: The "Test in Production"

**Bad:** No tests in CI/CD; quality checks only in production.
```
Developer: "I will add tests after we deploy"
# Deploys to production
# Tests reveal critical data quality issue
# Production data is bad for 2 hours
# Rollback required
```

**Good:** Quality gates in CI/CD.
```
PR → Code quality → Unit tests → Integration tests → Deploy
# Bad data never reaches production
# Production tests are for monitoring, not discovery
```

### Anti-Pattern 5: The "One-Size-Fits-All" Threshold

**Bad:** Same completeness threshold for all columns.
```
# All columns: completeness >= 95%
# customer_id: 95% (should be 100%)
# promo_code: 95% (should be 20%, it is optional)
# phone_number: 95% (should be 85%, not everyone provides it)
```

**Good:** Context-aware thresholds.
```
# Primary keys: 100%
# Required business fields: 99%
# Optional fields: context-dependent
# Deprecated fields: 0% (expected to be null)
```

### Anti-Pattern 6: The "No Baseline" Anomaly Detection

**Bad:** Anomaly detection without historical baseline.
```
# New model deployed
# Anomaly detector: "No historical data, cannot detect anomalies"
# 3 weeks later: bad data in production, no alerts
```

**Good:** Baseline establishment as part of deployment.
```
# New model deployment checklist:
# [ ] Collect 14 days of baseline metrics
# [ ] Configure anomaly thresholds
# [ ] Verify alert routing
# [ ] Document expected patterns
```

---

## 11. Practical Examples & Templates

### Example A: Complete Quality Suite for E-Commerce

```yaml
# models/fct_orders.yml
version: 2

models:
  - name: fct_orders
    description: |
      Fact table containing all customer orders. 
      Grain: one row per order.
      Tier: 1 (Critical - feeds executive dashboard and revenue reporting)

    config:
      contract:
        enforced: true
      tags: ['tier_1', 'finance', 'revenue']

    columns:
      - name: order_id
        description: Unique identifier for the order (UUID v4)
        data_type: uuid
        tests:
          - unique:
              severity: error
          - not_null:
              severity: error

      - name: customer_id
        description: Foreign key to dim_customers
        data_type: uuid
        tests:
          - not_null:
              severity: error
          - relationships:
              to: ref('dim_customers')
              field: customer_id
              severity: error

      - name: order_total
        description: Total order value in USD (net of discounts, before tax)
        data_type: decimal(18,2)
        tests:
          - not_null:
              severity: error
              config:
                where: "order_status = 'completed'"
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 100000
              severity: error
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 0
              max_value: 100000

      - name: order_status
        description: Current status in the order lifecycle
        data_type: varchar(20)
        tests:
          - not_null
          - accepted_values:
              values: ['pending', 'completed', 'cancelled', 'refunded']
              severity: error

      - name: ordered_at
        description: Timestamp when the order was placed
        data_type: timestamp
        tests:
          - not_null
          - dbt_utils.recency:
              datepart: hour
              field: ordered_at
              interval: 1
              severity: warn

      - name: email
        description: Customer email for order confirmation
        data_type: varchar(255)
        tests:
          - dbt_expectations.expect_column_values_to_match_regex:
              regex: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
              severity: warn
              config:
                where: "email IS NOT NULL"

    tests:
      - dbt_expectations.expect_table_row_count_to_be_between:
          min_value: 1000
          max_value: 10000000

      - dbt_expectations.expect_column_pair_values_to_be_equal:
          column_A: order_total
          column_B: calculated_total

      - name: revenue_matches_gl
        test_type: custom_sql
        sql: |
          SELECT 
            ABS(
              (SELECT SUM(order_total) FROM {{ ref('fct_orders') }} WHERE order_status = 'completed') -
              (SELECT SUM(amount) FROM {{ source('finance', 'general_ledger') }} WHERE account = 'revenue')
            ) / 
            NULLIF((SELECT SUM(amount) FROM {{ source('finance', 'general_ledger') }} WHERE account = 'revenue'), 0)
            AS variance_pct
          HAVING variance_pct > 0.005
        severity: error

      - name: no_duplicate_orders
        test_type: custom_sql
        sql: |
          SELECT customer_id, order_total, DATE_TRUNC('minute', ordered_at)
          FROM {{ ref('fct_orders') }}
          GROUP BY 1, 2, 3
          HAVING COUNT(*) > 1
        severity: warn
```

### Example B: Quality Monitoring Dashboard SQL

```sql
-- Daily quality score tracking
WITH daily_tests AS (
  SELECT 
    DATE(test_completed_at) as test_date,
    model_name,
    test_name,
    CASE WHEN status = 'pass' THEN 1 ELSE 0 END as passed,
    CASE WHEN status = 'fail' THEN 1 ELSE 0 END as failed,
    CASE WHEN severity = 'error' AND status = 'fail' THEN 1 ELSE 0 END as critical_failure
  FROM test_results
  WHERE test_completed_at >= CURRENT_DATE - 30
),

daily_scores AS (
  SELECT
    test_date,
    model_name,
    COUNT(*) as total_tests,
    SUM(passed) as tests_passed,
    SUM(failed) as tests_failed,
    SUM(critical_failure) as critical_failures,
    ROUND(100.0 * SUM(passed) / COUNT(*), 2) as pass_rate,
    CASE 
      WHEN SUM(critical_failure) > 0 THEN 'FAIL'
      WHEN SUM(failed) > 0 THEN 'WARN'
      ELSE 'PASS'
    END as overall_status
  FROM daily_tests
  GROUP BY 1, 2
)

SELECT * FROM daily_scores
ORDER BY test_date DESC, model_name;
```

### Example C: Automated Quality Report

```markdown
# Daily Data Quality Report — 2026-08-10

## Executive Summary
- **Overall Quality Score:** 97.2/100 (A)
- **Tests Run:** 1,247
- **Tests Passed:** 1,211 (97.1%)
- **Tests Failed:** 36 (2.9%)
- **Critical Failures:** 2 (P1)
- **Models Affected:** 12

## Critical Issues (P1)
1. **fct_orders.freshness** — Table 3 hours stale
   - Owner: @jane.doe
   - Impact: Executive dashboard, Finance report
   - Status: Investigating

2. **dim_customers.completeness** — email null rate 15% (threshold: 5%)
   - Owner: @john.smith
   - Impact: Marketing segmentation, Email campaigns
   - Status: Root cause identified (source API change)

## Warnings (P2)
- 34 non-critical test failures across 10 models
- Most common: accepted_values (new status values from source)
- Recommended: Review and update value lists

## Trends (Last 7 Days)
- Quality score: 96.8 → 97.2 → 97.5 → 97.1 → 96.9 → 97.0 → 97.2
- Critical failures: 1 → 0 → 0 → 2 → 1 → 0 → 2
- Average resolution time: 2.3 hours

## Action Items
- [ ] Fix fct_orders freshness (Owner: @jane.doe, Due: EOD)
- [ ] Update dim_customers email handling (Owner: @john.smith, Due: Aug 11)
- [ ] Review accepted_values across all models (Owner: @data-team, Due: Aug 14)
```

---

## 12. ModelBox AI Integration Opportunities

### Feature 1: Auto-Generate Quality Tests from Schema

**Input:** ModelBox AI generates a schema.

**Auto-Output:**
```yaml
# Auto-generated from ModelBox schema
quality_tests:
  model: fct_orders

  auto_generated:
    # Primary key tests
    - test: unique
      column: order_id
      severity: error

    - test: not_null
      column: order_id
      severity: error

    # Foreign key tests
    - test: relationships
      column: customer_id
      to: dim_customers.customer_id
      severity: error

    # Data type validation
    - test: accepted_range
      column: order_total
      min: 0
      severity: error
      reason: "Auto-detected: DECIMAL column with business context 'revenue'"

    # Enum validation (from business requirements)
    - test: accepted_values
      column: order_status
      values: [pending, completed, cancelled, refunded]
      severity: error
      reason: "Auto-detected from business requirement: Order Lifecycle"

    # Freshness (from SLA in contract)
    - test: recency
      column: ordered_at
      interval: 1 hour
      severity: warn
      reason: "Auto-detected from contract SLA: freshness < 1h"

    # Format validation (from column name patterns)
    - test: regex_match
      column: email
      pattern: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
      severity: warn
      reason: "Auto-detected: column name contains 'email'"

    # Reconciliation suggestion
    - test: reconciliation
      column: order_total
      compare_to: source('finance', 'general_ledger')
      tolerance: 0.005
      severity: error
      reason: "Suggested: Financial column should reconcile with source of truth"
```

### Feature 2: Synthetic Seed Data for Quality Validation

**Input:** ModelBox schema + quality test definitions.

**Auto-Output:**
```python
# ModelBox generates synthetic data that exercises all test cases
synthetic_datasets = {
    "valid_baseline": generate_realistic_data(n=1000),
    "edge_cases": generate_boundary_data(n=100),
    "invalid_data": generate_invalid_data(n=50),  # Should trigger test failures
    "reconciliation_test": generate_mismatched_data(n=100)  # For reconciliation tests
}

# These datasets are loaded as dbt seeds
# CI/CD runs tests against all datasets
# "invalid_data" dataset should cause EXPECTED failures
# This validates that tests actually catch bad data
```

### Feature 3: Quality Scorecard Auto-Generation

**From model + test results:**
```yaml
quality_scorecard:
  model: fct_orders
  generated_by: ModelBox AI

  dimensions:
    accuracy:
      score: 99.8
      tests: 3
      passed: 3

    completeness:
      score: 98.5
      tests: 5
      passed: 4
      failed: 1  # email null rate 15%

    consistency:
      score: 100
      tests: 2
      passed: 2

    validity:
      score: 99.2
      tests: 8
      passed: 7
      failed: 1  # 8 malformed emails

    timeliness:
      score: 85
      tests: 2
      passed: 1
      failed: 1  # 3h stale

    uniqueness:
      score: 100
      tests: 2
      passed: 2

  overall_score: 97.2
  grade: A
  status: certified_with_warnings

  recommendations:
    - "Investigate email null rate increase (15% vs. 5% threshold)"
    - "Fix fct_orders freshness (3h stale vs. 1h SLA)"
```

### Feature 4: "Spot the Flaw" — Quality Edition

**Challenge:** Given a model and its tests, identify missing or weak quality coverage.

```yaml
# Flawed quality suite (presented to student)
model: fct_orders
tests:
  - unique: order_id        # Good
  - not_null: order_id      # Good
  - not_null: customer_id   # Good
  # MISSING: relationships test on customer_id
  # MISSING: range check on order_total
  # MISSING: accepted_values on order_status
  # MISSING: recency/freshness check
  # MISSING: reconciliation with source
  # MISSING: format validation on email
  # WEAK: No table-level row count sanity check
```

**AI Tutor Response:**
```
"This quality suite has significant gaps:

1. No foreign key validation. customer_id could reference 
   non-existent customers. Add a relationships test.

2. No range check on order_total. Negative orders or 
   million-dollar orders could slip through. Add accepted_range.

3. No status validation. A typo like 'completd' would go 
   unnoticed. Add accepted_values for order_status.

4. No freshness check. If the pipeline breaks silently, 
   you would serve stale data indefinitely. Add recency test.

5. No reconciliation. Your warehouse revenue might diverge 
   from the finance system. Add a custom reconciliation test.

6. No email format validation. Malformed emails break 
   downstream marketing campaigns. Add regex match.

7. No volume sanity check. If row count drops 90%, 
   something is wrong. Add expect_table_row_count_to_be_between."
```

### Feature 5: Breaking Change Detection via Quality Delta

**When schema changes:**
```
ModelBox detects: "order_status" enum changed
  Old values: [pending, completed, cancelled]
  New values: [pending, completed, cancelled, refunded, on_hold]

Auto-analysis:
  - accepted_values test: NEEDS UPDATE
  - Downstream filters: MAY BREAK (dashboards filtering by status)
  - Semantic layer: Metric "cancelled_orders" unaffected
  - Business glossary: NEEDS UPDATE (add 'on_hold' definition)

Auto-generated:
  - Updated test YAML
  - Migration guide for consumers
  - Updated business glossary entry
```

---

## 13. Course Module: Data Quality Engineering Mastery

### Module Outline (8-Week Course)

#### Week 1: Foundations of Data Quality
- The 6 dimensions of data quality (DAMA-DMBOK)
- Cost of bad data: real-world case studies
- Quality vs. testing vs. validation vs. observability
- The modern quality engineering mindset
- **Lab:** Assess quality maturity of a sample dataset

#### Week 2: dbt Testing (The Foundation)
- Built-in tests: unique, not_null, accepted_values, relationships
- dbt-expectations: advanced row-level validations
- Test configuration: severity, where clauses, error thresholds
- Testing strategy: risk-based, tier-based
- **Lab:** Build a complete test suite for a fact table

#### Week 3: Great Expectations & Soda
- GX expectation suites and checkpoints
- Soda checks and data contracts
- Cross-tool comparison and selection criteria
- **Lab:** Port dbt tests to GX and Soda; compare capabilities

#### Week 4: Data Contracts as Quality Enforcement
- OpenDataContract quality rules
- dbt contract enforcement
- Contract validation in CI/CD
- Breaking change detection
- **Lab:** Write and validate a data contract with embedded quality rules

#### Week 5: Anomaly Detection & Observability
- Statistical anomaly detection (z-score, IQR)
- Seasonality-aware detection
- Volume, freshness, schema drift monitoring
- Tooling: Monte Carlo, Metaplane, custom dashboards
- **Lab:** Build an anomaly detector for order volume

#### Week 6: Quality in CI/CD
- Quality gates: code quality → unit tests → integration tests → deploy
- GitHub Actions / GitLab CI for data pipelines
- Automated reconciliation testing
- Performance testing for data models
- **Lab:** Build a complete CI/CD pipeline with quality gates

#### Week 7: Incident Response & Root Cause Analysis
- The data incident lifecycle
- Investigation techniques (lineage, logs, source checks)
- Post-mortem writing and preventive measures
- Runbook development
- **Lab:** Conduct a simulated incident investigation

#### Week 8: Capstone Project
- **Scenario:** A retail company's "daily revenue" dashboard has been showing incorrect numbers for 2 weeks. The issue was only discovered when the CFO noticed the monthly total didn't match the GL. The root cause: a silent schema change in the Shopify API added a new order status "on_hold" that wasn't handled in the ETL, causing those orders to be excluded from revenue calculations.
- **Task:** Design a complete quality engineering solution to prevent this from happening again.
- **Deliverables:**
  - Updated test suite (dbt + GX + Soda)
  - Data contract with quality rules
  - CI/CD quality gates
  - Anomaly detection configuration
  - Incident response runbook
  - Post-mortem template
  - Preventive measures checklist

### Assessment Rubric

| Criteria | Weight | Excellent (A) | Good (B) | Needs Work (C) |
|----------|--------|--------------|----------|----------------|
| Test Coverage | 20% | Comprehensive, risk-based, tier-appropriate | Good coverage, minor gaps | Incomplete or unfocused |
| Contract Quality | 15% | Complete schema + quality + SLA + ownership | Good contract, minor omissions | Incomplete |
| Anomaly Detection | 15% | Robust, seasonality-aware, low false positives | Working detection, minor tuning issues | Brittle or ineffective |
| CI/CD Integration | 15% | Full pipeline with gates, alerts, documentation | Working pipeline, minor gaps | Manual or incomplete |
| Incident Response | 15% | Clear process, thorough investigation, preventive measures | Good process, minor gaps | Reactive, no prevention |
| Documentation | 10% | Clear runbooks, stakeholder-ready reports | Good docs, minor clarity issues | Unclear or missing |
| Innovation | 10% | Creative solutions, synthetic data, advanced techniques | Some innovation | Basic only |

---

## Appendix: Quick Reference Card

### Quality Checklist for New Models

**Before promoting a model to production:**
- [ ] Primary key: unique + not_null
- [ ] Foreign keys: relationships test
- [ ] Required business columns: not_null
- [ ] Numeric columns: range validation (min/max)
- [ ] Categorical columns: accepted_values
- [ ] Temporal columns: recency/freshness check
- [ ] Format columns: regex validation
- [ ] Financial columns: reconciliation with source
- [ ] Table-level: row count sanity check
- [ ] Cross-system: consistency validation
- [ ] Anomaly detection: baseline established
- [ ] Alert routing: configured and tested

### The 5 Quality Questions Every Model Must Answer

1. **Is it complete?** (No unexpected nulls, all required data present)
2. **Is it accurate?** (Matches source of truth, passes reconciliation)
3. **Is it valid?** (Conforms to type, format, and business rules)
4. **Is it timely?** (Freshness within SLA, pipeline on schedule)
5. **Is it consistent?** (Matches across systems, no contradictions)

### Test Severity Guidelines

| Severity | When to Use | Response |
|----------|-------------|----------|
| **ERROR** | Primary key violation, negative revenue, data contract breach | Block deployment, page on-call |
| **WARN** | Format issue, optional field null rate high, minor drift | Log alert, notify team, don't block |
| **INFO** | Documentation missing, non-critical threshold near limit | Log only, review in weekly standup |

---

*Document compiled for ModelBox AI product strategy and educational course development. Based on 2026 market research of 43+ data modeling job postings and modern data quality engineering practices.*
