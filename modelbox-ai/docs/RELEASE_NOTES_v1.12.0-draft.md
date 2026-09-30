# ModelBox AI — v1.12.0 Release Notes (draft)

> **Draft.** Written before the release; the version stamps still read 1.11.1.
> The release-preparation change renames this file to `RELEASE_NOTES_v1.12.0.md`,
> fills in the tag and the release run, and bumps every stamp.

**Tag:** `v1.12.0` (not yet tagged)  ·  **Carries:** Sprint 8, merged to `main`
in pull requests #14 to #24 and the release-preparation change  ·
**Supersedes:** v1.11.1.

**This is the release for the consultant's engagement.** A client's exported
DDL file becomes a model on the canvas, reconciled against the file itself,
with nothing connected to the client's systems. The model's data dictionary
carries definitions, owners, sources and a status per field; a field is marked
verified only under stated conditions. A drift report compares the documented
design with a later export of the deployed schema, and migrations say which
statements drop data. CI now walks this engagement in a real browser on every
change.

---

## Upgrading an existing install

1. **Check out `v1.12.0` and start the appliance as before** (`up --build -d`,
   README "Quick start"), or run the published v1.12.0 images (README
   "Releases"). No `.env` change is
   needed: v1.12.0 adds no setting and no secret.
2. **The migrate service upgrades the database on start.** It runs migrations
   0023 to 0027 in order, then exits; the backend starts after it. Nothing is
   run by hand.

   | Migration | What it does |
   | :-- | :-- |
   | 0023 | Adds each model's reconciliation status and import report. |
   | 0024 | Adds each imported column's type exactly as the file declared it. |
   | 0025 | Moves keys and constraints to their own tables, so composite keys and multi-column constraints can be stored; keeps each imported column's DEFAULT as declared; converts every stored model and lists, per model, anything it could not convert exactly; repairs the enum values described below. |
   | 0026 | Adds the dictionary fields, a classification scale per workspace (Public, Internal, Confidential, Restricted), and each field's status and provenance. Existing PII flags are kept, with the status "recorded". |
   | 0027 | Adds the audit actions for changing a member's role and removing a member. |

3. **Check the conversion findings.** Migration 0025 converts every saved
   model's keys and relationships. What it could not convert exactly (a
   relationship saved without columns stays, unresolved; a reference to a
   table outside the model is listed with its text) is recorded per model and
   returned with it by `GET /api/v1/model/{id}` as `conversion_findings`.

---

## A defect fixed on upgrade: models that could not be reopened

**v1.11.x shipped this defect.** A model synthesized from a provider response
that left out an entity's type was stored with that type written as the
enumeration's name (`EntityType.TABLE`) instead of its value (`TABLE`), and
such a model could not be reopened. v1.12.0 stores values, and migration 0025
repairs every row stored that way (entity types, asset tiers and PII types).
Each repaired model lists the repair in its `conversion_findings`, with kind
`enum_name_repaired`. To list every affected model after the upgrade:

```bash
docker compose --env-file .env -f docker/docker-compose.appliance.yml exec postgres-db \
  psql -U modelbox -d modelbox_metadata -c "SELECT model_id, entity_name, detail FROM model_conversion_findings WHERE kind = 'enum_name_repaired';"
```

---

## What's new

### Import an exported DDL file (`/import`)

- Upload a schema exported from a client's database; it is read on the
  appliance and becomes a model. **Oracle** (`DBMS_METADATA`) and **SQL
  Server** (SSMS / SMO scripts, split at `GO`) are certified on genuine
  exports, and **PostgreSQL** on a genuine `pg_dump`. **Snowflake** is tested
  only against a fixture written from its documentation, and is **not
  certified**.
- **Every import is reconciled** against counts taken from the file by a
  counter that shares no code with the parser. The model is saved
  *reconciled* or *unreconciled*, and the report, as Markdown or JSON, names
  each gap by statement and line. What is not imported (indexes, sequences,
  views, procedures) is listed, not dropped.
- Each column keeps its type and its DEFAULT exactly as the file declared
  them, beside the normalized form.
- UTF-8 and UTF-16 files, with or without a BOM.

### Keys, constraints and saved models

- **Composite primary keys, composite foreign keys, and UNIQUE and CHECK
  constraints over several columns** are held in the model. A relationship's
  columns are chosen when it is drawn; one without columns is kept, and the
  linter reports it as `UNRESOLVED_RELATIONSHIP`.
- **DDL export states them**, with `COMMENT ON` descriptions where the dialect
  has it. Whatever a dialect cannot express is listed as a named **export
  gap** at the top of the file. For PostgreSQL, a foreign-key cycle is closed
  with `ALTER TABLE` after every table exists, and SQL Server `money`,
  `smallmoney`, `bit` and `geography` are written as types PostgreSQL accepts;
  each substitution is a named gap. Exported PostgreSQL DDL is applied to a
  real PostgreSQL 16 in CI.
- **The semantic export names what it cannot state.** A MetricFlow entity is
  one column, so a composite primary key is declared as a `primary_entity`, and
  composite foreign keys, composite primary keys and a key column that is also
  a foreign key are listed as export gaps.
- **Saved models have an address,** `/canvas/<id>`, and a list at `/models`.
  Leaving the canvas with unsaved changes asks first. An imported model, which
  holds no diagram positions, is laid out when it first opens; Save keeps the
  layout.

### The data dictionary

- Rendered as **Markdown, HTML, JSON and CSV**, with every field the model
  holds in a fixed order, relationships with their column pairs (unresolved
  ones shown as such), and the model's reconciliation stated at the top.
- **Fields a person supplies:** for columns, a definition, business name,
  permissible values, unit, classification, critical data element and
  authoritative source; for tables, a business name, business owner, IT
  steward and authoritative source. Synthesis never fills them.
- **A classification scale per workspace** (`/settings/classification`),
  editable by its admins; a level in use cannot be deleted.
- **Every field that holds a value has a status**, counted as "N of M fields
  verified, K pending review". A field is **verified** only when an approver
  asks, the model is a reconciled import, the field's definition passes the
  machine-checkable rules of ISO/IEC 11179-4, and its provenance is recorded
  and is not an AI draft. A verified value that changes returns to pending
  review. Every status change is an audit event.
- **Dictionary review on the canvas:** each field with its status, filterable
  by table; an approver, admin or owner verifies one field or a selection and
  sees each condition as the server found it.

### Drift report

- Compare a saved model, the documented design, with a DDL export of the
  deployed schema: `POST /api/v1/model/{id}/drift`, or **Drift report** on the
  canvas. Each drift is classified breaking, non-breaking or informational by
  nineteen rules listed in the user guide. A drift touching a verified field is
  flagged, and an unreconciled import is warned about first. Renames are not
  guessed: a renamed column is a removal and an addition, with a "possible
  rename" hint.

### Migration diff

- Columns are paired by internal id only between versions of the same model,
  and by name between separately saved models. A rename that is not certain is
  shown as a removal and an addition.
- **Every statement that drops data says so**, in the generated SQL and in the
  diff panel, naming the columns whose data it removes.

### Workspace members

- Workspace OWNERs and ADMINs add existing users, change their roles and remove
  them, through the API (`/api/v1/workspaces/{id}/members`) and
  `/settings/members`. No one grants a role above their own, an ADMIN cannot
  make an OWNER, a workspace always keeps an OWNER, and a removed member's API
  keys stop at once. Role changes and removals are audit events.

### Verified in CI

- **Engagement Journey**, a required check: a browser walks one engagement on
  the appliance as installed, and shows a documentation-derived import warned
  about and refused verification.
- **The rollback below** is run on every change: the database is downgraded to
  v1.11.1's schema and v1.11.1's published images run on it.
- A **claims guard** test keeps wording the evidence does not support off every
  public surface.

---

## Rolling back to v1.11.1

Tested in CI on every change (`tests/blackbox/test_rollback.py`): this
release's database is downgraded to v1.11.1's schema, and v1.11.1's published
images start on it, report healthy and read the models.

1. Stop the application, keeping the database:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.appliance.yml stop modelbox-ui modelbox-backend modelbox-worker
   ```

2. Downgrade the schema **while still on v1.12.0**: its image holds the
   downgrade steps, and v1.11.1's does not. Take a backup first; the losses
   below cannot be undone by upgrading again.

   ```bash
   docker compose --env-file .env -f docker/docker-compose.appliance.yml run --rm --no-deps modelbox-migrate python -m alembic downgrade 0022_append_only_ledgers
   ```

3. Check out the `v1.11.1` tag, keeping the same `.env`, and start the
   appliance as its README describes. Its migrate service finds the database
   already at its head and changes nothing.

**What the downgrade loses.** v1.11.1's schema has no place for the following,
and they are deleted, not kept aside:

- every column pair of a composite foreign key after the first;
- UNIQUE and CHECK constraints over more than one column (one-column ones
  become column flags again);
- a composite primary key's own order (its columns keep their key flags, in
  table order);
- foreign-key names, and the order of tables and relationships within a
  model;
- each column's type and DEFAULT as declared in the imported file;
- each model's reconciliation status and import report;
- the conversion findings listed on upgrade;
- every dictionary field a person supplied, the classification scales and
  levels, and every field's status and provenance, including "verified".

**What it keeps:** models, tables, columns and their one-column keys and
constraints, relationships by their first column pair, PII flags, workspaces,
members **with their current roles**, API keys and the audit trail. Audit
events written by v1.12.0 (field status changes, classification changes, role
changes and removals) stay in the append-only audit log, and the database keeps
accepting their action names; v1.11.1 never writes them.

The test asserts the losses it can observe by SQL (this release's tables gone,
a composite foreign key reduced to its first pair, a composite key kept as
flags) and that a changed role survives; the rest of the list is read from the
migrations' downgrade steps.

---

## Known limits

- **Snowflake import is not certified.** Its fixture is written from
  documentation; a genuine `GET_DDL` export is needed.
- **Computed columns are not exported**; each is named as an export gap.
- **Conversion findings are returned by the API but not yet shown on the
  canvas.**
- **Only the machine-checkable rules of ISO/IEC 11179-4 are applied.**
  "Verified" does not claim a definition is right for the business.
