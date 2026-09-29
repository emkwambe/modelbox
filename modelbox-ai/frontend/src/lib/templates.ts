/**
 * Business Requirements Library — curated starter templates.
 *
 * Each template ships a natural-language `rawPrompt` ("Synthesize Live" mode)
 * and a pre-built, verified `entities`/`relationships` graph ("Inspect
 * Gold-Standard" mode, loaded onto the canvas with no LLM call). Pure static
 * data — no backend dependency.
 */

import type { Column, Entity, Paradigm, PIIType, Relationship } from '@/types/schema';

export interface Template {
  id: string;
  title: string;
  emoji: string;
  domain: string;
  paradigm: Paradigm;
  description: string;
  highlights: string[];
  rawPrompt: string;
  /** Why entities were classified/keyed as they were (Trainer anchor). */
  rationale: string;
  entities: Entity[];
  relationships: Relationship[];
}

// --- compact builders (fill schema defaults) -------------------------------
type ColOpts = Partial<
  Pick<
    Column,
    | 'is_primary_key'
    | 'is_foreign_key'
    | 'is_pii'
    | 'pii_type'
    | 'is_metric'
    | 'aggregation'
    | 'references'
    | 'description'
  >
>;

function col(name: string, dataType: string, opts: ColOpts = {}): Column {
  return {
    name,
    data_type: dataType,
    is_primary_key: false,
    is_foreign_key: false,
    is_pii: false,
    is_metric: false,
    ...opts,
  };
}

// Each takes an optional description. Keys, foreign keys, classified columns
// and measures are exactly as much a part of a reference model's documentation
// as its plain attributes — the linter's MISSING_DESCRIPTION rule makes no
// exception for them, and neither should a template that is held up as an
// example.
const pk = (name: string, dt = 'INTEGER', description?: string): Column =>
  col(name, dt, { is_primary_key: true, ...(description ? { description } : {}) });
const fk = (name: string, dt = 'INTEGER', description?: string): Column =>
  col(name, dt, { is_foreign_key: true, ...(description ? { description } : {}) });
const pii = (
  name: string,
  dt: string,
  t: PIIType,
  description?: string,
): Column =>
  col(name, dt, {
    is_pii: true,
    pii_type: t,
    ...(description ? { description } : {}),
  });
const metric = (
  name: string,
  dt = 'NUMERIC(18,2)',
  agg = 'sum',
  description?: string,
): Column =>
  col(name, dt, {
    is_metric: true,
    aggregation: agg,
    ...(description ? { description } : {}),
  });

function ent(
  entity_name: string,
  entity_type: Entity['entity_type'],
  columns: Column[],
  extra: Partial<
    Pick<
      Entity,
      'description' | 'grain' | 'agg_time_column' | 'tier' | 'freshness_sla'
    >
  > = {},
): Entity {
  return {
    entity_name,
    entity_type,
    canvas_position_x: 0,
    canvas_position_y: 0,
    columns,
    description: extra.description ?? null,
    grain: extra.grain ?? null,
    // Governance fields. Declared only where the requirements state them — a
    // tier claims a criticality the business must stand behind, and claiming
    // one obliges an SLA nobody agreed to (the MISSING_SLA lint catches that
    // pairing). The AML template states both in its prompt, so it declares
    // both; the other templates state neither and declare neither.
    tier: extra.tier ?? null,
    freshness_sla: extra.freshness_sla ?? null,
    // The entity's default time axis for measures. Null where the entity has
    // no temporal column at all — six of the fifteen entities here — in which
    // case it gets no measures rather than an invented time dimension.
    agg_time_column: extra.agg_time_column ?? null,
  };
}

const rel = (
  from: string,
  to: string,
  cardinality: Relationship['cardinality'] = 'N:1',
): Relationship => ({ from, to, cardinality });

/** Lay entities out in a 3-column grid so Mode B looks tidy immediately. */
function grid(entities: Entity[]): Entity[] {
  const COLS = 3;
  return entities.map((e, i) => ({
    ...e,
    canvas_position_x: (i % COLS) * 320,
    canvas_position_y: Math.floor(i / COLS) * 240,
  }));
}

// --- templates -------------------------------------------------------------
export const TEMPLATES: Template[] = [
  {
    id: 'saas-subscription',
    title: 'Subscription Analytics (SaaS)',
    emoji: '💳',
    domain: 'SaaS & Recurring Revenue',
    paradigm: 'KIMBALL',
    description:
      'MRR/ARR facts with SCD Type 2 customer tiers and churn tracking.',
    highlights: ['MRR tracking', 'SCD Type 2 histories', 'Churn'],
    rawPrompt:
      'Design a subscription analytics warehouse for a SaaS business. Track ' +
      'monthly recurring revenue (MRR) and ARR per subscription, customer tier ' +
      'changes over time using Slowly Changing Dimension Type 2, plan metadata, ' +
      'and churn. The grain of the fact table is one row per subscription per month.',
    rationale:
      'fact_subscription_monthly is a FACT at one-row-per-subscription-per-month ' +
      'grain; dim_customer uses SCD2 (valid_from/valid_to + is_current) so tier ' +
      'history is preserved. MRR is an additive measure; plan is a conformed dimension.',
    entities: grid([
      ent(
        'dim_customer',
        'DIMENSION',
        [
          pk('customer_sk'),
          col('customer_id', 'VARCHAR(64)', { description: 'Natural key' }),
          pii('email', 'VARCHAR(255)', 'EMAIL'),
          col('tier', 'VARCHAR(32)'),
          col('valid_from', 'DATE'),
          col('valid_to', 'DATE'),
          col('is_current', 'BOOLEAN'),
        ],
        {
          description: 'SCD Type 2 customer dimension.',
          agg_time_column: 'valid_from',
        },
      ),
      ent('dim_plan', 'DIMENSION', [
        pk('plan_sk'),
        col('plan_code', 'VARCHAR(32)'),
        col('plan_name', 'VARCHAR(120)'),
        metric('list_price', 'NUMERIC(10,2)', 'avg'),
      ]),
      ent(
        'fact_subscription_monthly',
        'FACT',
        [
          pk('subscription_month_sk'),
          fk('customer_sk'),
          fk('plan_sk'),
          col('month', 'DATE'),
          metric('mrr'),
          metric('seats', 'INTEGER'),
          col('is_churned', 'BOOLEAN'),
        ],
        {
          grain: 'One row per subscription per month.',
          agg_time_column: 'month',
        },
      ),
    ]),
    relationships: [
      rel('fact_subscription_monthly.customer_sk', 'dim_customer.customer_sk'),
      rel('fact_subscription_monthly.plan_sk', 'dim_plan.plan_sk'),
    ],
  },
  {
    id: 'ecommerce-orders',
    title: 'E-Commerce & Logistics',
    emoji: '📦',
    domain: 'E-Commerce & Logistics',
    paradigm: 'KIMBALL',
    description: 'Order-line grain star with product and customer dimensions.',
    highlights: ['Order-line grain', 'Basket analysis', 'Shipping dims'],
    rawPrompt:
      'Model an e-commerce analytics star schema. Capture orders and their line ' +
      'items, products, and customers. The fact grain is one row per order line. ' +
      'Support basket analysis and shipping/fulfilment reporting.',
    rationale:
      'fact_order_line is the FACT at order-line grain (quantity, extended price ' +
      'are additive). dim_product and dim_customer are conformed dimensions; the ' +
      'order header attributes hang off the line via the order_id degenerate key.',
    entities: grid([
      ent('dim_customer', 'DIMENSION', [
        pk('customer_sk'),
        pii('full_name', 'VARCHAR(200)', 'NAME'),
        pii('email', 'VARCHAR(255)', 'EMAIL'),
        col('country', 'VARCHAR(64)'),
      ]),
      ent('dim_product', 'DIMENSION', [
        pk('product_sk'),
        col('sku', 'VARCHAR(48)'),
        col('product_name', 'VARCHAR(200)'),
        col('category', 'VARCHAR(64)'),
      ]),
      ent(
        'fact_order_line',
        'FACT',
        [
          pk('order_line_sk'),
          col('order_id', 'VARCHAR(48)', { description: 'Degenerate dimension' }),
          fk('customer_sk'),
          fk('product_sk'),
          metric('quantity', 'INTEGER'),
          metric('extended_price'),
        ],
        { grain: 'One row per order line item.' },
      ),
    ]),
    relationships: [
      rel('fact_order_line.customer_sk', 'dim_customer.customer_sk'),
      rel('fact_order_line.product_sk', 'dim_product.product_sk'),
    ],
  },
  {
    id: 'banking-datavault',
    title: 'Retail Banking & Ledger',
    emoji: '🏦',
    domain: 'Financial Services & Banking',
    paradigm: 'DATA_VAULT',
    description: 'Hubs, links, and satellites for an auditable transaction ledger.',
    highlights: ['Hubs / Links / Satellites', 'Immutable audit', 'High throughput'],
    rawPrompt:
      'Design a Data Vault 2.0 model for a retail bank ledger. Model customers ' +
      'and accounts as hubs, transactions as a link between accounts, and ' +
      'descriptive attributes as satellites with load timestamps for an immutable ' +
      'audit trail.',
    rationale:
      'Hubs (hub_customer, hub_account) hold immutable business keys + hash keys. ' +
      'lnk_transaction is a LINK relating accounts. sat_account_details is a ' +
      'SATELLITE carrying descriptive, historised attributes keyed by the hub hash key.',
    entities: grid([
      ent('hub_customer', 'HUB', [
        pk('customer_hk', 'CHAR(32)'),
        col('customer_bk', 'VARCHAR(64)', { description: 'Business key' }),
        col('load_dts', 'TIMESTAMP'),
        col('record_source', 'VARCHAR(64)'),
      ], { agg_time_column: 'load_dts' }),
      ent('hub_account', 'HUB', [
        pk('account_hk', 'CHAR(32)'),
        col('account_bk', 'VARCHAR(64)'),
        col('load_dts', 'TIMESTAMP'),
        col('record_source', 'VARCHAR(64)'),
      ], { agg_time_column: 'load_dts' }),
      ent('lnk_transaction', 'LINK', [
        pk('transaction_hk', 'CHAR(32)'),
        fk('account_hk', 'CHAR(32)'),
        fk('customer_hk', 'CHAR(32)'),
        col('load_dts', 'TIMESTAMP'),
      ], { agg_time_column: 'load_dts' }),
      ent('sat_account_details', 'SATELLITE', [
        fk('account_hk', 'CHAR(32)'),
        col('load_dts', 'TIMESTAMP'),
        col('status', 'VARCHAR(32)'),
        metric('balance'),
      ], { agg_time_column: 'load_dts' }),
    ]),
    relationships: [
      rel('lnk_transaction.account_hk', 'hub_account.account_hk'),
      rel('lnk_transaction.customer_hk', 'hub_customer.customer_hk'),
      rel('sat_account_details.account_hk', 'hub_account.account_hk', '1:1'),
    ],
  },
  {
    id: 'healthcare-ehr',
    title: 'Healthcare Patient EHR',
    emoji: '🏥',
    domain: 'Healthcare & Patient EHR',
    paradigm: '3NF',
    description: 'Normalized patient encounters with PII/PHI tagging.',
    highlights: ['PII/PHI tags', 'N:1 constraints', 'Audit keys'],
    rawPrompt:
      'Design a normalized (3NF) operational schema for an electronic health ' +
      'record system. Model patients, providers, encounters, and diagnoses with ' +
      'explicit foreign-key constraints. Tag personally identifiable and protected ' +
      'health information columns for HIPAA compliance.',
    rationale:
      'Normalized 3NF: each entity holds a single-theme set of attributes with ' +
      'N:1 FKs (encounter → patient, encounter → provider, diagnosis → encounter). ' +
      'PII/PHI columns (name, SSN) are explicitly flagged for compliance masking.',
    entities: grid([
      ent('patient', 'TABLE', [
        pk('patient_id'),
        pii('full_name', 'VARCHAR(200)', 'NAME'),
        pii('ssn', 'CHAR(11)', 'SSN'),
        col('date_of_birth', 'DATE'),
        // No agg_time_column: date_of_birth is this entity's only temporal
        // column, but a birth date is not a default aggregation axis.
        // Cohort-by-birth-year is a legitimate query, not the default time
        // grain of a patient dimension — and a gold graph teaches whatever it
        // shows. patient is dimension-only.
      ]),
      ent('provider', 'TABLE', [
        pk('provider_id'),
        pii('full_name', 'VARCHAR(200)', 'NAME'),
        col('specialty', 'VARCHAR(96)'),
      ]),
      ent('encounter', 'TABLE', [
        pk('encounter_id'),
        fk('patient_id'),
        fk('provider_id'),
        col('encounter_ts', 'TIMESTAMP'),
      ], { agg_time_column: 'encounter_ts' }),
      ent('diagnosis', 'TABLE', [
        pk('diagnosis_id'),
        fk('encounter_id'),
        col('icd10_code', 'VARCHAR(10)'),
        col('description', 'VARCHAR(255)'),
      ]),
    ]),
    relationships: [
      rel('encounter.patient_id', 'patient.patient_id'),
      rel('encounter.provider_id', 'provider.provider_id'),
      rel('diagnosis.encounter_id', 'encounter.encounter_id'),
    ],
  },
  {
    id: 'marketing-attribution',
    title: 'Digital Marketing & Attribution',
    emoji: '📣',
    domain: 'Digital Marketing & Attribution',
    paradigm: 'OBT',
    description: 'One Big Table of touchpoints for fast BI aggregation.',
    highlights: ['Multi-touch attribution', 'Clickstream', 'OBT for BI'],
    rawPrompt:
      'Build a One Big Table (OBT) for multi-touch marketing attribution. Each ' +
      'row is a single touchpoint in a user session with campaign, channel, ' +
      'device, and conversion attributes, denormalized for fast analytical ' +
      'aggregation in BI tools.',
    rationale:
      'OBT deliberately denormalizes every attribution attribute into one wide ' +
      'table keyed at touchpoint grain, trading storage for query simplicity and ' +
      'BI performance — no joins required for attribution roll-ups.',
    entities: grid([
      ent(
        'obt_touchpoints',
        'TABLE',
        [
          pk('touchpoint_id', 'BIGINT'),
          pii('user_email', 'VARCHAR(255)', 'EMAIL'),
          col('session_id', 'VARCHAR(64)'),
          col('event_ts', 'TIMESTAMP'),
          col('campaign', 'VARCHAR(120)'),
          col('channel', 'VARCHAR(64)'),
          col('device', 'VARCHAR(48)'),
          metric('attributed_revenue'),
          col('is_conversion', 'BOOLEAN'),
        ],
        {
          grain: 'One row per user touchpoint (fully denormalized).',
          agg_time_column: 'event_ts',
        },
      ),
    ]),
    relationships: [],
  },
  {
    id: 'aml-financial-crime',
    title: 'AML & Financial Crime Analytics',
    emoji: '🛡️',
    domain: 'Financial Crime & Compliance',
    paradigm: 'KIMBALL',
    description:
      'Party, KYC, account, transaction, detection, alert and case — the analytical spine behind transaction monitoring.',
    highlights: ['KYC & beneficial ownership', 'Detection & alert lineage', 'Counterparty networks'],
    rawPrompt:
      'Design a Kimball analytical model for anti-money-laundering transaction ' +
      'monitoring at a retail bank. Model the customer (party) and their KYC/CDD ' +
      'profile, their accounts, and the counterparties and devices they transact ' +
      'with. Transactions are the measurable event. A detection rule fires against ' +
      'a transaction and produces a hit; hits are grouped into alerts, alerts are ' +
      'worked as investigations, and investigations end in a disposition. ' +
      'Transaction data is a critical asset and must be no more than one hour ' +
      'stale. Classify personal data.',
    rationale:
      'Two facts, nine conformed dimensions. fact_transaction is the monetary ' +
      'event at one row per transaction leg; fact_detection_hit is one row per ' +
      'rule firing against one transaction, which is a different grain and so a ' +
      'separate fact rather than a flag on the first. ' +
      'Alert, investigation and disposition are DIMENSIONS, not facts: the ' +
      'measurable event is the hit, and the alert and case are the descriptive ' +
      'context it is grouped into. Modelling them as facts would put fact-to-fact ' +
      'joins in the middle of the star — the chasm trap the FAN_OUT_RISK lint ' +
      'exists to catch. ' +
      'fact_detection_hit carries transaction_reference as a degenerate dimension ' +
      'rather than a foreign key to fact_transaction, for the same reason. ' +
      'dim_counterparty is separate from dim_party because a counterparty is ' +
      'usually not a customer of this bank; keeping them apart also avoids two ' +
      'foreign keys from one entity to the same parent, a role-playing shape the ' +
      'semantic-layer exporters do not yet serve correctly. ' +
      'dim_detection_rule carries the version, threshold and effective period as ' +
      'attributes, so a hit records which version of which rule fired.',
    entities: grid([
      ent('dim_date', 'DIMENSION', [
        pk('date_sk', 'INTEGER', 'Surrogate key for the calendar day.'),
        col('calendar_date', 'DATE', { description: 'The calendar day.' }),
        col('month_name', 'VARCHAR(16)', { description: 'Month name, for reporting.' }),
        col('is_weekend', 'BOOLEAN', { description: 'True for Saturday and Sunday.' }),
      ], {
        description: 'Conformed calendar dimension shared by both facts.',
        agg_time_column: 'calendar_date',
      }),
      ent('dim_party', 'DIMENSION', [
        pk('party_sk', 'INTEGER', 'Surrogate key for the party.'),
        col('party_reference', 'VARCHAR(32)', { description: 'The bank\'s customer reference.' }),
        col('party_type', 'VARCHAR(16)', { description: 'INDIVIDUAL or ORGANISATION.' }),
        pii('full_name', 'VARCHAR(160)', 'NAME', 'Legal name of the party. Personal data.'),
        pii('email_address', 'VARCHAR(255)', 'EMAIL', 'Contact email held for the party. Personal data.'),
        pii('residential_address', 'VARCHAR(255)', 'ADDRESS', 'Registered address of the party. Personal data, and a linkage signal when shared.'),
        col('date_of_birth', 'DATE', {
          is_pii: true,
          description: 'Date of birth for an individual party. Personal data.',
        }),
        col('is_beneficial_owner', 'BOOLEAN', {
          description: 'True where this party is a beneficial owner of another party.',
        }),
        col('valid_from', 'DATE', { description: 'Start of this version of the record.' }),
        col('valid_to', 'DATE', { description: 'End of this version; open for the current row.' }),
      ], {
        description:
          'A customer or related party — an individual or an organisation, including beneficial owners.',
        agg_time_column: 'valid_from',
      }),
      ent('dim_kyc_profile', 'DIMENSION', [
        pk('kyc_profile_sk', 'INTEGER', 'Surrogate key for the KYC profile.'),
        fk('party_sk', 'INTEGER', 'The party this profile describes.'),
        col('risk_rating', 'VARCHAR(16)', { description: 'Customer risk rating: LOW, MEDIUM or HIGH.' }),
        col('verification_status', 'VARCHAR(24)', { description: 'Outcome of identity verification.' }),
        col('due_diligence_level', 'VARCHAR(16)', { description: 'CDD or EDD.' }),
        col('source_of_funds', 'VARCHAR(120)', { description: 'Declared source of the funds transacted.' }),
        col('last_reviewed_on', 'DATE', { description: 'Date the profile was last reviewed.' }),
      ], {
        description:
          'The KYC/CDD profile held for a party: risk rating, verification outcome and review history.',
        agg_time_column: 'last_reviewed_on',
      }),
      ent('dim_account', 'DIMENSION', [
        pk('account_sk', 'INTEGER', 'Surrogate key for the account.'),
        fk('party_sk', 'INTEGER', 'The party who holds this account.'),
        col('account_reference', 'VARCHAR(32)', { description: 'The bank\'s account reference.' }),
        pii('iban', 'VARCHAR(34)', 'IBAN', 'International bank account number. Personal data.'),
        col('product_type', 'VARCHAR(24)', { description: 'Deposit, card, wallet or loan.' }),
        col('opened_on', 'DATE', { description: 'Date the account was opened.' }),
        col('status', 'VARCHAR(16)', { description: 'Account status, e.g. ACTIVE or DORMANT.' }),
      ], {
        description: 'An account held by a party, and the product it belongs to.',
        agg_time_column: 'opened_on',
      }),
      ent('dim_counterparty', 'DIMENSION', [
        pk('counterparty_sk', 'INTEGER', 'Surrogate key for the counterparty.'),
        col('counterparty_name', 'VARCHAR(160)', {
          is_pii: true,
          description: 'Name of the external party on the other side of the transaction. Personal data where an individual.',
        }),
        col('counterparty_country', 'VARCHAR(2)', { description: 'ISO-3166 alpha-2 country of the counterparty.' }),
        col('institution_name', 'VARCHAR(120)', { description: 'Financial institution holding the counterparty account.' }),
        col('is_high_risk_jurisdiction', 'BOOLEAN', {
          description: 'True where the counterparty country is on the institution\'s high-risk list.',
        }),
      ], {
        description:
          'The external party on the other side of a transaction. Separate from dim_party because a counterparty is usually not a customer of this bank.',
      }),
      ent('dim_device', 'DIMENSION', [
        pk('device_sk', 'INTEGER', 'Surrogate key for the device.'),
        col('device_fingerprint', 'VARCHAR(64)', { description: 'Stable identifier for the device used.' }),
        pii('ip_address', 'VARCHAR(45)', 'ADDRESS', 'Network address the transaction was initiated from. Personal data.'),
        col('device_type', 'VARCHAR(24)', { description: 'Mobile, web or branch terminal.' }),
        col('first_seen_on', 'DATE', { description: 'Date this device was first observed.' }),
      ], {
        description:
          'A device or network identifier used to initiate transactions. Shared identifiers across parties are a linkage signal.',
        agg_time_column: 'first_seen_on',
      }),
      ent('dim_detection_rule', 'DIMENSION', [
        pk('detection_rule_sk', 'INTEGER', 'Surrogate key for this version of the rule.'),
        col('rule_code', 'VARCHAR(32)', { description: 'Stable code for the rule, e.g. STRUCTURING_01.' }),
        col('rule_name', 'VARCHAR(120)', { description: 'Human-readable rule name.' }),
        col('rule_version', 'VARCHAR(16)', { description: 'Version of the rule that fired.' }),
        col('threshold_value', 'NUMERIC(18,2)', { description: 'The threshold this version was tuned to.' }),
        col('effective_from', 'DATE', { description: 'Date this version came into force.' }),
        col('effective_to', 'DATE', { description: 'Date this version was superseded; open for the current version.' }),
        col('rationale', 'VARCHAR(255)', { description: 'Why the rule exists and what it is intended to catch.' }),
      ], {
        description:
          'A transaction-monitoring rule at a specific version, with the threshold it was tuned to and the period it was in force.',
        agg_time_column: 'effective_from',
      }),
      ent('dim_alert', 'DIMENSION', [
        pk('alert_sk', 'INTEGER', 'Surrogate key for the alert.'),
        col('alert_reference', 'VARCHAR(32)', { description: 'Reference shown to the analyst.' }),
        col('priority', 'VARCHAR(16)', { description: 'Triage priority assigned to the alert.' }),
        col('status', 'VARCHAR(24)', { description: 'Open, in review, or closed.' }),
        col('raised_on', 'DATE', { description: 'Date the alert was raised from its hits.' }),
      ], {
        description:
          'The unit of analyst work created by grouping one or more detection hits. Descriptive context for the hit, not a measurable event in its own right.',
        agg_time_column: 'raised_on',
      }),
      ent('dim_investigation', 'DIMENSION', [
        pk('investigation_sk', 'INTEGER', 'Surrogate key for the investigation.'),
        fk('alert_sk', 'INTEGER', 'The alert this investigation was opened from.'),
        col('case_reference', 'VARCHAR(32)', { description: 'Case reference for the investigation.' }),
        col('assigned_team', 'VARCHAR(64)', { description: 'Team that worked the case.' }),
        col('opened_on', 'DATE', { description: 'Date the investigation was opened.' }),
        col('closed_on', 'DATE', { description: 'Date the investigation was closed; open while ongoing.' }),
      ], {
        description:
          'The analyst work carried out on an alert, from opening to closure.',
        agg_time_column: 'opened_on',
      }),
      ent('dim_disposition', 'DIMENSION', [
        pk('disposition_sk', 'INTEGER', 'Surrogate key for the disposition.'),
        fk('investigation_sk', 'INTEGER', 'The investigation this outcome closes.'),
        col('disposition_code', 'VARCHAR(32)', { description: 'Configurable outcome code for the investigation.' }),
        col('disposition_reason', 'VARCHAR(255)', { description: 'Analyst\'s stated reason for the outcome.' }),
        col('decided_on', 'DATE', { description: 'Date the outcome was recorded.' }),
      ], {
        description:
          'How an investigation ended — false positive, explained activity, escalation or closure. Codes are configurable per institution; this model records the decision, it does not make one.',
        agg_time_column: 'decided_on',
      }),
      ent('fact_transaction', 'FACT', [
        pk('transaction_sk', 'INTEGER', 'Surrogate key for the transaction leg.'),
        fk('date_sk', 'INTEGER', 'Day the transaction was executed.'),
        fk('account_sk', 'INTEGER', 'The account the money moved on.'),
        fk('counterparty_sk', 'INTEGER', 'The external party on the other side.'),
        fk('device_sk', 'INTEGER', 'Device used to initiate the transaction.'),
        col('transaction_reference', 'VARCHAR(32)', {
          description: 'The source system\'s transaction identifier. Degenerate dimension.',
        }),
        col('transaction_ts', 'TIMESTAMP', { description: 'When the transaction was executed.' }),
        col('direction', 'VARCHAR(8)', { description: 'INBOUND or OUTBOUND relative to the account.' }),
        col('channel', 'VARCHAR(24)', { description: 'Channel used, e.g. FASTER_PAYMENT or CARD.' }),
        col('currency_code', 'VARCHAR(3)', { description: 'ISO-4217 currency of the transacted amount.' }),
        metric('transaction_amount', 'NUMERIC(18,2)', 'sum', 'Value of the transaction in the stated currency.'),
      ], {
        description:
          'One monetary movement on an account. The measurable event this model is built around.',
        grain: 'One row per transaction leg, per account, per counterparty.',
        agg_time_column: 'transaction_ts',
        tier: 'TIER_1_CRITICAL',
        freshness_sla: '< 1h',
      }),
      ent('fact_detection_hit', 'FACT', [
        pk('detection_hit_sk', 'INTEGER', 'Surrogate key for the detection hit.'),
        fk('date_sk', 'INTEGER', 'Day the rule fired.'),
        fk('detection_rule_sk', 'INTEGER', 'The rule version that fired.'),
        fk('account_sk', 'INTEGER', 'The account the hit relates to.'),
        fk('alert_sk', 'INTEGER', 'The alert this hit was grouped into.'),
        col('transaction_reference', 'VARCHAR(32)', {
          description:
            'The transaction this hit fired against, carried as a degenerate dimension rather than a foreign key to fact_transaction — a fact-to-fact join is the chasm trap.',
        }),
        col('detected_at', 'TIMESTAMP', { description: 'When the rule evaluated and fired.' }),
        col('observed_value', 'NUMERIC(18,2)', {
          description: 'The value the rule observed, against which its threshold was compared.',
        }),
      ], {
        description:
          'One firing of one detection rule version against one transaction. Immutable: a hit records what was true when the rule ran.',
        grain: 'One row per detection rule firing, per transaction.',
        agg_time_column: 'detected_at',
        tier: 'TIER_1_CRITICAL',
        freshness_sla: '< 1h',
      }),
    ]),
    relationships: [
      rel('dim_kyc_profile.party_sk', 'dim_party.party_sk'),
      rel('dim_account.party_sk', 'dim_party.party_sk'),
      rel('dim_investigation.alert_sk', 'dim_alert.alert_sk'),
      rel('dim_disposition.investigation_sk', 'dim_investigation.investigation_sk'),
      rel('fact_transaction.date_sk', 'dim_date.date_sk'),
      rel('fact_transaction.account_sk', 'dim_account.account_sk'),
      rel('fact_transaction.counterparty_sk', 'dim_counterparty.counterparty_sk'),
      rel('fact_transaction.device_sk', 'dim_device.device_sk'),
      rel('fact_detection_hit.date_sk', 'dim_date.date_sk'),
      rel('fact_detection_hit.detection_rule_sk', 'dim_detection_rule.detection_rule_sk'),
      rel('fact_detection_hit.account_sk', 'dim_account.account_sk'),
      rel('fact_detection_hit.alert_sk', 'dim_alert.alert_sk'),
    ],
  },
];

export const TEMPLATE_DOMAINS = Array.from(
  new Set(TEMPLATES.map((t) => t.domain)),
);
export const TEMPLATE_PARADIGMS = Array.from(
  new Set(TEMPLATES.map((t) => t.paradigm)),
);
