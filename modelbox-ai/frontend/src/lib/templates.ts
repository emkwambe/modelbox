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

const pk = (name: string, dt = 'INTEGER'): Column =>
  col(name, dt, { is_primary_key: true });
const fk = (name: string, dt = 'INTEGER'): Column =>
  col(name, dt, { is_foreign_key: true });
const pii = (name: string, dt: string, t: PIIType): Column =>
  col(name, dt, { is_pii: true, pii_type: t });
const metric = (name: string, dt = 'NUMERIC(18,2)', agg = 'sum'): Column =>
  col(name, dt, { is_metric: true, aggregation: agg });

function ent(
  entity_name: string,
  entity_type: Entity['entity_type'],
  columns: Column[],
  extra: Partial<Pick<Entity, 'description' | 'grain' | 'agg_time_column'>> = {},
): Entity {
  return {
    entity_name,
    entity_type,
    canvas_position_x: 0,
    canvas_position_y: 0,
    columns,
    description: extra.description ?? null,
    grain: extra.grain ?? null,
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
];

export const TEMPLATE_DOMAINS = Array.from(
  new Set(TEMPLATES.map((t) => t.domain)),
);
export const TEMPLATE_PARADIGMS = Array.from(
  new Set(TEMPLATES.map((t) => t.paradigm)),
);
