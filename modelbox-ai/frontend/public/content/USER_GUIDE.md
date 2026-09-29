# ModelBox AI — User Guide

ModelBox AI is an LLM-agnostic **data modelling appliance**: generate a first-draft
model from plain language for a modeller to review and edit, reverse-engineer
live warehouses, lint for governance, diff & migrate schemas, and export
artifacts — dbt, data contracts, semantic layers, dictionaries, and seed data.

This guide walks data teams through the seven core workflows. All actions are
available in the web UI; every one is also scriptable via the API (see
[API_REFERENCE.md](API_REFERENCE.md)).

**Getting in:** open the appliance (e.g. `http://localhost:13000`), sign in, and
you land on the home studio. The top nav links to Canvas, Trainer, Connectors,
and API keys.

---

## Workflow 1 — Greenfield AI synthesis & interactive canvas

1. On the home page, describe your domain in plain language (or paste a PRD /
   raw DDL). Example: *"Track customers, subscriptions, and monthly recurring
   revenue with tier changes over time."*
2. Choose a **paradigm** (3NF, Kimball, Data Vault, OBT) and a **dialect**.
3. Click **Synthesize model**. Synthesis runs as an async job and streams to
   completion, then opens the **Canvas**.
4. On the canvas: drag entities, edit columns, add relationships, and use
   **Auto-layout**. **Save** persists the graph and re-validates; **Rename** and
   **Delete** manage the model.
   - **Relationships name their columns.** Drag from one entity to another and
     a picker asks which columns the relationship joins: the target's primary
     key is proposed, with source columns of the same name. Pairs can be
     changed, added or removed, so a composite foreign key is one
     relationship. Click a relationship to change its columns. A relationship
     saved before columns could be chosen is drawn dashed until they are.
   - **Leaving with unsaved changes asks first,** whether by a link in the app
     or by closing or reloading the page.
5. Every saved model has its own address, `/canvas/<id>`, and **Models**
   (`/models`) lists them all. A model reopens exactly as it was saved.

> New to the tool? Click **📚 Explore Requirements Library** for 6 gold-standard
> starter scenarios — load one onto the canvas instantly (no LLM call) or use it
> as a prompt.

**API:** `POST /api/v1/jobs/synthesize` → poll `GET /api/v1/jobs/{id}` →
`GET /api/v1/model/{id}`.

## Workflow 2 — Brownfield database introspection

Reverse-engineer an existing schema onto the canvas.

1. Go to **Connectors** (`/settings/connectors`).
2. **Add connection**: name, engine, and a connection URI. Supported engines:
   **PostgreSQL, Snowflake, BigQuery, MySQL**. URIs are stored **AES-256-GCM
   encrypted** and never shown again.
   - PostgreSQL / MySQL: `postgresql://user:pass@host:5432/db`, `mysql://user:pass@host:3306/db`
   - Snowflake: `snowflake://user:pass@account/DB/SCHEMA?warehouse=WH`
   - BigQuery: paste the service-account JSON key as the URI.
3. Click **Introspect →**, enter the schema/dataset, and ModelBox builds a model:
   entities, columns, PK/FK, and inferred FACT/DIMENSION/TABLE types — then opens
   it on the canvas.

**API:** `POST /api/v1/connectors` then `POST /api/v1/connectors/introspect`.

### Workflow 2b — Import an exported DDL file

Build a model from a schema file, with no connection to the database it came
from: the file is read on the appliance.

1. Go to **Import** (`/import`).
2. Choose the workspace, the file's dialect and the file. The dialect list says
   what each import has been tested against: Oracle (`DBMS_METADATA.GET_DDL`
   output), PostgreSQL (`pg_dump --schema-only`) and SQL Server (SSMS or SMO
   scripting, split at `GO`) against genuine exports; Snowflake only against a
   fixture written from its documentation. Files may be UTF-8 or UTF-16 (as
   SSMS saves them), with or without a byte-order mark.
3. Click **Import**. The result says whether the import **reconciled**: the
   file's own counts of tables, columns, keys, constraints and descriptions
   beside what was imported, with partitions counted apart from tables. A
   difference, or a statement the parser did not understand, is listed with
   its statement number and line, and the model is saved **unreconciled**.
4. **Open on the canvas**, or download the report as Markdown or JSON. A
   DDL file holds no diagram positions, so the canvas lays the tables out
   when the model first opens; **Save** keeps that layout.

Not imported, and listed in the report: indexes, sequences, views, procedures,
functions, triggers, ownership, privileges, session settings and `USE`. A
partition is kept as metadata of its parent table. Composite primary and
foreign keys, and UNIQUE and CHECK constraints over several columns, are in
the model; a computed column is kept in the report because the model holds no
expression for it.

Each column keeps its type and its DEFAULT exactly as the file declared them,
beside their normalized forms, which exports and comparisons use. From SQL
Server: constraints added by `ALTER TABLE`, with `WITH CHECK` or
`WITH NOCHECK`, are in the model (a `NOCHECK` constraint is listed as not
validated against existing rows); `MS_Description` properties on tables and
columns become descriptions, and other extended properties are listed; a
user-defined type resolves to the base type its `CREATE TYPE … FROM` names.

**API:** `POST /api/v1/import/ddl`, then `GET /api/v1/model/{id}/import-report`.

## Workflow 3 — Governance linting & PII classification

Every validation run includes the **governance lint pack** (advisory warnings —
they never block a model). On the canvas, affected nodes show an amber badge +
tooltip, and unclassified-PII columns get a `🔓` highlight.

Rules: `NAMING_CONVENTION`, `MISSING_GRAIN`, `MISSING_DESCRIPTION`,
`PII_EXPOSURE` (columns that look like PII but aren't classified),
`ORPHAN_ENTITY`, and `UNRESOLVED_RELATIONSHIP` (a relationship that does not
say which columns it joins). Structural errors (`CYCLIC_FK`, `MISSING_PK`,
`DANGLING_REF`, which also covers a relationship naming a column that does not
exist) still invalidate a model.

Fix findings by adding descriptions, declaring FACT grains, renaming to
conventions (`dim_`/`fact_`/… prefixes, `_id`/`_sk` key suffixes), and tagging
PII columns. Re-validate to confirm.

**API:** `POST /api/v1/model/{id}/validate`.

## Workflow 4 — Schema diffing & breaking-change migration

Compare two model versions into migration DDL.

1. On the canvas, open **Diff & migrate**.
2. Pick a **target model** (V2) from the dropdown and a **dialect**.
3. **Compute diff** renders the `ALTER`/`CREATE`/`DROP` DDL and a color-coded
   list of **breaking changes** (dropped tables/columns, type alterations).
4. **Copy** the DDL into your migration tool.

**Renames are never guessed between two saved models.** Columns of two
separately saved models are matched by name, so a column renamed between them
appears as a removal and an addition. Every statement that drops a column or
a table is headed in the DDL by a `-- DATA LOSS:` comment naming what it
drops, and the panel lists the same statements above the DDL under **This
migration drops data**. If a dropped column was really renamed, replace its
`DROP` and the matching `ADD` with a `RENAME` before you run the migration.

**API:** `POST /api/v1/model/diff` with `{source_model_id, target_model_id, dialect}`;
the response's `data_loss` lists the statements that drop data.

### Drift report: the design against the deployed schema

A drift report compares a saved model, the documented design, with a DDL
export of the schema actually deployed, imported fresh and never saved. It
uses the same comparison as the migration diff and reports:

- tables and columns added and removed;
- for each column both sides hold: its type (the normalized type, with the
  type as declared on each side), nullability, and default (shown in its
  original text; a default respelled with the same meaning is not a drift);
- primary keys, UNIQUE, foreign-key and CHECK constraints added, removed or
  changed, composite ones included, and a primary key whose column order
  changed;
- table and column descriptions.

**No renames are guessed.** Columns are matched by name, so a renamed column
is reported as a removal and an addition. When a removed and an added column
of one table have the same type at the same position, the report adds a
**possible rename** hint naming them; it is only a hint, and both drifts stand.

The header names both sources: the saved model with its version, and the
imported file with the time it was imported. It states both reconciliation
statuses; a report built on an unreconciled import says so at the top. A drift
that touches a field the dictionary holds as **verified** is flagged **verified
field affected by drift**, with the fields named.

Every drift is classified by the first of these rules that applies:

| Rule | When | Class |
|---|---|---|
| D1 | A table is removed. | breaking |
| D2 | A table is added. | non-breaking |
| D3 | A column is removed (a renamed column is a removal and an addition). | breaking |
| D4 | A NOT NULL column with no default is added: existing inserts that omit it fail. | breaking |
| D5 | A nullable column, or a NOT NULL column with a default, is added. | non-breaking |
| D6 | A type is widened: every value of the old type fits the new one. | non-breaking |
| D7 | A type is narrowed, or changed to another kind of type. | breaking |
| D8 | The declared type's text changed and its normalized type did not. | informational |
| D9 | A nullable column becomes NOT NULL. | breaking |
| D10 | A NOT NULL column becomes nullable. | non-breaking |
| D11 | A default is added, changed or removed: only rows inserted later are affected. | non-breaking |
| D12 | The primary key is added, removed, or its columns or their order change. | breaking |
| D13 | A UNIQUE constraint is added: writes the design allows can be refused. | breaking |
| D14 | A UNIQUE constraint is removed: consumers relying on uniqueness lose it. | breaking |
| D15 | A foreign key is added: writes the design allows can be refused. | breaking |
| D16 | A foreign key is removed: consumers relying on the reference lose it. | breaking |
| D17 | A CHECK constraint is added: writes the design allows can be refused. | breaking |
| D18 | A CHECK constraint is removed: the deployed schema accepts more. | non-breaking |
| D19 | A table or column description is added, changed or removed. | informational |

**Breaking** means something that works against the design can fail against
the deployed schema; **non-breaking**, nothing that works today can fail;
**informational**, only text a person reads changed. A type counts as widened
(D6) only when every value provably fits: a larger integer, a decimal with at
least as many digits each side of the point, a longer or unbounded string of
the same kind (fixed to varying and ASCII to Unicode also widen), a larger
float, more fractional seconds. Any other type change, including one ModelBox
cannot read, is D7.

On the canvas, open **Drift report**, choose the deployed schema's DDL file
and its dialect, and **Compare**. The panel shows any unreconciled-import
warning first, then both sources, the counts by class, each drift with its
class, rule and flag, and the possible renames.

**API:** `POST /api/v1/model/{id}/drift`, multipart, with the file, its
`dialect` (as for import) and `format` (`markdown`, `html` or `json`).

## Workflow 5 — Exporting data contracts & dbt

Open **Export artifacts** on the canvas. Tabs:

- **Artifacts** — multi-dialect SQL DDL, a **dbt** project (staging models +
  `schema.yml` with `unique`/`not_null`/`relationships` and `accepted_values`
  tests), and Cube.js. Download individual files or the dbt/Cube project `.zip`.
  DDL states composite keys, composite foreign keys, UNIQUE and CHECK
  constraints and, where the dialect has `COMMENT ON`, descriptions. Whatever
  a dialect cannot express is listed as an **export gap** at the top of the
  file, by table and reason — for example a CHECK in Snowflake, which has no
  CHECK constraints, or a relationship whose columns were never chosen.
  When tables reference each other in a cycle, the foreign key that cannot be
  declared with its table is added by `ALTER TABLE` after every table exists
  (PostgreSQL, Snowflake, Redshift, Databricks); other dialects list it as an
  export gap. For PostgreSQL, a default that calls a sequence the model does
  not hold is left out, a schema-qualified user-defined type the model does
  not define is written as `TEXT` (without the default's cast to it), and SQL Server `money`, `smallmoney`, `bit` and
  `geography` are written as `NUMERIC(19, 4)`, `NUMERIC(10, 4)`, `BOOLEAN` and
  `TEXT`. Each of these is listed as an export gap.
- **Contracts** — **OpenDataContract** YAML, **Apache Avro**, **Protobuf**.
- **Semantic** — Cube.js, **LookML**, **dbt MetricFlow**. A MetricFlow entity
  is one column and has one type, so a table with a composite primary key
  declares a `primary_entity` instead (its key columns that are foreign keys
  still join). What MetricFlow cannot state is an **export gap**, listed at the
  head of `semantic_models.yml` and in `EXPORT_GAPS.md`: a composite foreign
  key (no join), a composite primary key (nothing joins to it by that key), a
  one-column key that is also a foreign key (its join is not stated), and a
  relationship whose columns were never chosen.

**API:** `GET /api/v1/model/{id}/export?format=…`,
`…/export/contract?format=…`, `…/export/semantic?engine=…`.

## Workflow 6 — Generating data dictionaries

Open **Export artifacts → Dictionary**. Choose a format:

- **Markdown** — per-entity column tables and a relationships table.
- **HTML** — a self-contained, styled documentation page.
- **JSON** — machine-readable metadata; feed it to AI agents or a catalog.
- **CSV** — two files: `data_dictionary.csv`, one row per column with its
  table's fields, and a `<field>_status` column beside each field; and
  `data_dictionary_relationships.csv`.

Every format shows the same fields, read from the model, in this order:
column name, position, type, the type as declared in the source DDL,
nullable, default (in its original text), primary-key position, UNIQUE
constraints (including composite ones), foreign-key target, CHECK
constraints, description, business name, permissible values, unit,
classification, PII, critical data element, authoritative source, and
validation rules (min, max, regex). Each table shows its business name,
description, grain, type, business owner, IT steward and authoritative
source.

**Every field that holds a value shows its status**, and the dictionary's
header counts them: "N of M fields verified, K pending review".

- **verified** — an approver asked, and all three conditions held (below).
- **pending review** — where the value came from is recorded (the DDL, a
  source comment, a named person on a date, or an AI draft), and nobody has
  verified it yet.
- **recorded** — the value is there, but nothing records where it came from
  (values saved before this release, including PII flags).

A field is marked verified only where its attestation says so; apart from
those fields, the word appears only in the header's count and the legend.

### Supplying and verifying dictionary fields

Select a column on the canvas to edit its definition, business name,
permissible values (one per line), unit, classification, critical data
element (not assessed, yes, or no) and authoritative source; select an entity
for its business name, owners and authoritative source. Save the model. A
value you change is recorded as supplied by you, on that date, and is
pending review. A model's synthesis never fills these fields: a business
name or an owner the model guessed would read as fact.

Open **Dictionary** on the canvas to review them: every field that holds a
value, with its status and the "N of M fields verified, K pending review"
count, filterable by table. An **APPROVER**, admin or owner sees a **Verify**
button on each field not yet verified, and a checkbox to verify a selection
with **Verify selected**; a member or viewer sees neither, and the server
refuses them. The API is `POST /api/v1/model/{id}/attestations/verify`. A
field becomes verified only when all three hold:

1. the model was imported from a DDL file and **reconciled**;
2. its **definition** (the column's or table's description) passes the
   ISO/IEC 11179-4 rules a tool can check: it is present, it is a phrase or
   sentence rather than one word, it does not state only what the concept is
   not, and it is not the name restated;
3. its **provenance** is recorded, and it is not an AI draft.

Each field is answered with the three conditions as found, so a field that
stays pending shows what it lacks; the Dictionary panel lists them under
**Verification results**, with the reason a field stayed pending. The rest of ISO/IEC 11179-4 is judgement,
and passing these rules does not claim it. **A verified field returns to
pending when its value changes**, as a model's approval lapses when the model
is edited. Every status change is written to the audit log, which is the
review history.

### The classification scale

Each workspace has one classification scale, least to most sensitive: Public,
Internal, Confidential and Restricted to begin with. A workspace owner or
admin changes it at **Classification** (`/settings/classification`): add,
rename, move and delete levels. Columns refer to a level, not its name, so a
rename changes it everywhere at once. A level any column uses cannot be
deleted; reclassify those columns first. PII type stays a separate field.

The dictionary starts by stating where the model came from. A model imported
from a DDL file that did not reconcile with its source says so at the top, in
every format (in the CSV, in the `source_reconciliation` column), so the
dictionary is not read as describing the source database exactly.

The relationships table lists each relationship's column pairs. A
relationship whose columns have not been chosen is shown as **unresolved**,
so you can see which still need them.

**API:** `GET /api/v1/model/{id}/export/dictionary?format=markdown|html|json|csv`.

## Workspace members and roles

A workspace OWNER or ADMIN manages its members at **Members**
(`/settings/members`): add a person who already has an account on this
appliance, by email; change a member's role; remove a member. Accounts are
created by OIDC sign-in, SCIM provisioning or `create-owner`, never here: an
email with no account is refused and the message says so.

The rules, which the server enforces whatever the page offers:

- **No one grants a role above their own.** An ADMIN can grant up to ADMIN and
  cannot make an OWNER.
- **No one changes or removes a member whose role is above their own.** An
  ADMIN cannot demote or remove an OWNER.
- **The last OWNER of a workspace can never be demoted or removed.** Make
  someone else an OWNER first.
- **A removed or demoted member's API keys lose that access at once**: a key
  acts at its creator's role as it is at the moment of each request.

Adding a member, changing a role and removing a member are each recorded in
the audit log (`MEMBER_ADDED`, `MEMBER_ROLE_CHANGED`, `MEMBER_REMOVED`).

**API:** `GET`/`POST /api/v1/workspaces/{id}/members`,
`PATCH`/`DELETE /api/v1/workspaces/{id}/members/{user_id}`.

## Workflow 7 — CI/CD integration via API keys

Automate ModelBox from pipelines and agents.

1. Go to **API keys** (`/settings/api-keys`).
2. **Generate key** with a name. Copy the `mb_live_...` secret shown **once**.
3. Store it as a CI secret. Send it as an `X-API-Key` header — no interactive
   login. The key acts as its creating user, but only in its own workspace and
   only up to its cap: VIEWER unless a higher cap was chosen at creation via the
   API (`role_cap`), never above the creator's own role, and never above the
   creator's role *today*. A key cannot create keys. Revoke anytime from the
   same page.

```bash
# Example: export a data contract in CI
curl -H "X-API-Key: $MODELBOX_KEY" \
  "http://modelbox.internal:3000/api/v1/model/$MODEL_ID/export/contract?format=avro"
```

**API:** `POST /api/v1/auth/api-keys`, `GET /api/v1/auth/api-keys`,
`DELETE /api/v1/auth/api-keys/{id}`.

---

## Roles & access

Workspaces are multi-tenant with `OWNER > ADMIN > MEMBER`. Members synthesize and
edit models; ADMIN+ manage connectors and API keys and delete models. See the
[API Reference](API_REFERENCE.md) for per-endpoint requirements.

## Learn by doing — ModelBox Trainer

The **Trainer** (`/trainer`) teaches modeling with a Socratic tutor,
"Spot the Flaw" challenges, and auto-graded rubrics — and can load Requirements
Library scenarios straight into the sandbox.
