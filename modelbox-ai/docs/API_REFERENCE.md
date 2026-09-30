# ModelBox AI — API Reference

_Auto-generated from the live OpenAPI schema (ModelBox AI)._

**Base URL:** `http://<host>:<UI_PORT>/api/v1` — the appliance serves the API
through the UI's own origin and publishes no other port (`UI_PORT` defaults to
3000). The liveness probe is `GET /api/health` on the same port.

## Authentication

Every endpoint except registration/login and `/health` requires authentication. Two schemes are accepted:

- **Session JWT** — `Authorization: Bearer <token>` (from `POST /auth/token`).
- **API key** — `X-API-Key: mb_live_...` (from `POST /auth/api-keys`), for
  CI/CD pipelines and agents. A key acts as its creating user within its own
  workspace only, at the lower of its `role_cap` (default `VIEWER`; set at
  creation, never above the creator's role) and the creator's current role,
  re-read on every request. A key cannot create keys.

```bash
# Session token
TOKEN=$(curl -s -X POST http://localhost:3000/api/v1/auth/token \
  -d "username=you@example.com&password=secret" | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:3000/api/v1/model

# API key (CI/CD)
curl -H "X-API-Key: mb_live_xxx" http://localhost:3000/api/v1/model
```

```python
import requests
BASE = "http://localhost:3000/api/v1"
h = {"X-API-Key": "mb_live_xxx"}
models = requests.get(f"{BASE}/model", headers=h).json()
```

---

## Authentication & API Keys

### `GET /api/v1/auth/api-keys`

List API keys in the caller's workspaces (no secrets)

**Responses:** `200` Successful Response

### `POST /api/v1/auth/api-keys`

Create an API key (ADMIN+); returns the secret ONCE

**Request body:** `ApiKeyCreateRequest`

**Responses:** `201` Successful Response, `422` Validation Error

### `DELETE /api/v1/auth/api-keys/{key_id}`

Revoke an API key (ADMIN+)

| Param | In | Type | Required |
|---|---|---|---|
| `key_id` | path | string | yes |

**Responses:** `204` Successful Response, `422` Validation Error

### `GET /api/v1/auth/me`

Current authenticated user

**Responses:** `200` Successful Response

### `POST /api/v1/auth/register`

Register a local account and personal workspace

**Request body:** `RegisterRequest`

**Responses:** `201` Successful Response, `422` Validation Error

### `POST /api/v1/auth/token`

Obtain an access token

**Responses:** `200` Successful Response, `422` Validation Error

---

## Workspaces

### `GET /api/v1/workspaces`

List the caller's workspaces and their role in each

**Responses:** `200` Successful Response

### `GET /api/v1/workspaces/{workspace_id}/members`

The workspace's members, with their roles (VIEWER).

**Responses:** `200` Successful Response, `403` Not a member, `404` No such workspace

### `POST /api/v1/workspaces/{workspace_id}/members`

Add an existing appliance user to the workspace (OWNER or ADMIN). **Request
body:** `{"email": ..., "role": ...}`. Users are created by OIDC, SCIM or
`create-owner`; an email with no user is refused.

**Responses:** `201` Created (the member list), `403` A role above your own, or an ADMIN making an OWNER, `404` No such user, `409` Already a member

### `PATCH /api/v1/workspaces/{workspace_id}/members/{user_id}`

Change a member's role (OWNER or ADMIN). **Request body:** `{"role": ...}`.
Refused for a role above the caller's own, for a member whose role is above
the caller's own, and for the last OWNER. The role acted with is the
effective one: an API key's is the lower of its cap and its creator's role.

**Responses:** `200` The member list, `403` Above your own role, `404` No such member, `409` The last OWNER

### `DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}`

Remove a member (OWNER or ADMIN). Refused for a member whose role is above
the caller's own and for the last OWNER. The member's API keys lose this
workspace at once.

**Responses:** `204` Removed, `403` Above your own role, `404` No such member, `409` The last OWNER

### `GET /api/v1/workspaces/{workspace_id}/classification`

The workspace's classification scale (VIEWER): its levels, least to most
sensitive, each with `columns_using`. Every workspace starts with Public,
Internal, Confidential and Restricted.

**Responses:** `200` Successful Response, `403` Not a member, `404` No such workspace

### `POST /api/v1/workspaces/{workspace_id}/classification/levels`

Add a level at the top of the scale (ADMIN). **Request body:** `{"name": ...}`.

**Responses:** `201` Created, `409` A level has that name, `422` Validation Error

### `PATCH /api/v1/workspaces/{workspace_id}/classification/levels/{level_id}`

Rename or move a level (ADMIN). **Request body:** `{"name": ...}` and/or
`{"rank": ...}`. Columns hold a level by id, so a rename changes every use.

**Responses:** `200` Successful Response, `404` No such level, `409` A level has that name

### `DELETE /api/v1/workspaces/{workspace_id}/classification/levels/{level_id}`

Delete a level (ADMIN). Refused while any column uses it.

**Responses:** `204` Deleted, `404` No such level, `409` In use

---

## Models, Diff & Exports

### `GET /api/v1/model`

List models in the caller's workspaces

| Param | In | Type | Required |
|---|---|---|---|
| `workspace_id` | query | object | no |

**Responses:** `200` Successful Response, `422` Validation Error

### `POST /api/v1/model/diff`

Diff two models into migration DDL + breaking changes

**Request body:** `DiffRequest`

Columns of two separately saved models are paired by name: a rename between
them is a removal plus an addition, never guessed. Every statement that drops
a column or table is headed by a `-- DATA LOSS:` comment, and `data_loss`
lists the same text.

**Responses:** `200` Successful Response, `422` Validation Error

### `POST /api/v1/model/synthesize`

Synthesize a data model from natural language or documents

**Request body:** `SynthesizeRequest`

**Responses:** `201` Successful Response, `422` Validation Error

### `DELETE /api/v1/model/{model_id}`

Delete a model (ADMIN or OWNER only)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Responses:** `204` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}`

Retrieve a persisted data model

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

Entities and relationships come back in the order they were saved. Keys and
constraints have one source: each entity's `primary_key` (columns in key
order), `unique_constraints` and `check_constraints` (each with an optional
`name`; a CHECK lists the columns its `expression` reads), and each
relationship's `from_columns` and `to_columns`, paired by position, so a
composite foreign key is one relationship. `from` and `to` name entities. The
column flags `is_primary_key`, `is_unique`, `check_expression`,
`is_foreign_key` and `references` are derived from those lists. A
relationship with no complete column pairing is *unresolved*: kept, and
reported by the linter as `UNRESOLVED_RELATIONSHIP`. `conversion_findings`
lists what the keys-and-constraints migration (0025) kept but could not
convert exactly for this model.

**Responses:** `200` Successful Response, `422` Validation Error

### `PATCH /api/v1/model/{model_id}`

Update model metadata (title / dialect)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Request body:** `ModelUpdateRequest`

**Responses:** `200` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}/export`

Export a model as SQL DDL, dbt, or Cube.js artifacts

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `format` | query | ExportFormat | no |
| `dialect` | query | string | no |
| `target_has_ltree` | query | boolean | no |
| `target_has_postgis` | query | boolean | no |

`target_has_ltree` and `target_has_postgis` (default `false`, DDL to
PostgreSQL only) state that the target has, or may create, that extension.
With one set, `hierarchyid` or `geography` is written as `LTREE` or PostGIS
`GEOGRAPHY`, and the file starts with `CREATE EXTENSION IF NOT EXISTS`. Unset,
the column is an export gap: no extension is assumed. Set for another format
or dialect, the request is refused with `400`.

DDL states each table's columns, primary key, UNIQUE and CHECK constraints,
foreign keys (composite ones included) and, where the dialect has
`COMMENT ON` (PostgreSQL, DuckDB, Snowflake, Redshift), table and column
descriptions. Anything the model holds that the dialect cannot express, or
that the model does not state completely, is returned in `gaps` (each with a
`kind`, `entity` and `detail`) and listed as comments at the top of the SQL
file; nothing is left out without a gap. A model imported from a DDL file is
exported from the dialect it was imported from.

For `format=dbt`, `dialect` is the warehouse the project will run on: each
staging model casts its columns to the types the DDL export writes for that
dialect, and every name that is not lower snake case is quoted, in the SQL and
in `schema.yml`. A computed column the DDL export cannot create is left out.

**Responses:** `200` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}/export/contract`

Export a governance data contract (ODCS / Avro / Protobuf)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `format` | query | ContractFormat | no |

**Responses:** `200` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}/export/dictionary`

Export a data dictionary (Markdown/HTML/JSON/CSV)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `format` | query | DictionaryFormat | no |

**Responses:** `200` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}/export/semantic`

Export a semantic layer (Cube.js / LookML / MetricFlow)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `engine` | query | SemanticEngine | no |

**Responses:** `200` Successful Response, `422` Validation Error

### `POST /api/v1/model/{model_id}/export/synthetic-data`

Generate referentially-intact synthetic seed data (FR-2.4)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Request body:** `SyntheticSeedRequest`

Rows satisfy every primary key, UNIQUE, foreign key and CHECK constraint the
model declares, and each column is generated for its type in `dialect`. A
generated (computed) column is not written. A row that no values can make
satisfy its constraints is left out, and `rows_skipped` gives the count per
entity; it is empty when every entity has `row_count_per_entity` rows.

**Responses:** `200` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}/export/zip`

Download a multi-file artifact bundle as a .zip

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `format` | query | ExportFormat | no |
| `dialect` | query | string | no |

**Responses:** `200` Successful Response, `422` Validation Error

### `PUT /api/v1/model/{model_id}/graph`

Persist canvas edits (replace the model graph)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Request body:** `GraphUpdateRequest`

Send the keys and constraints as lists (see `GET /api/v1/model/{model_id}`).
A payload that also sends a column flag contradicting its lists is refused
with `422`. The older form, with keys only as column flags and relationships
as `"entity.column"` strings, is still accepted and read from its flags.

Dictionary fields ride in the same payload: on a column `business_name`,
`permissible_values` (a JSON list), `unit`, `critical_data_element`
(`null` means not assessed), `authoritative_source` and
`classification_level_id` (a level of the model's workspace scale, else
`422`); on an entity `business_name`, `business_owner`, `it_steward` and
`authoritative_source`. Each value this save changes records the caller as
its provenance and is pending review; a verified field whose value changes
returns to pending. A field's status is never part of the graph: an entity
or column carrying `field_status`, `verification_status`, `attestation` or
`attestations` is refused with `422`.

**Responses:** `200` Successful Response, `422` Validation Error

### `GET /api/v1/model/{model_id}/attestations`

Each dictionary field's status and provenance (VIEWER)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

Every field that holds a value, with `status` (`verified`, `pending`, or
`recorded` when no provenance is recorded), its `provenance` (`ddl`,
`source_comment`, `person`, `ai_draft`), who supplied it and when, and who
verified it and when. `summary.statement` reads "N of M fields verified,
K pending review".

**Responses:** `200` Successful Response, `422` Validation Error

### `POST /api/v1/model/{model_id}/attestations/verify`

Verify fields whose three conditions hold (APPROVER or higher)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Request body:** `{"fields": [{"entity": ..., "column": ... or null, "field": ...}]}`;
omit `fields` to ask for every field that holds a value.

A field becomes `verified` only when all three hold: the model is a reconciled
import; the field's definition (its column's or table's description) passes
the machine-checkable ISO/IEC 11179-4 rules (present, a phrase or sentence,
not only negative, not the name restated); and its provenance is recorded and
is not an AI draft. Each result carries `conditions` as found, so a field that
stays pending shows why. The request cannot state a status: any other key is
refused with `422`.

**Responses:** `200` Successful Response, `403` Below APPROVER, `422` Validation Error

### `POST /api/v1/model/{model_id}/validate`

Re-run topological/structural validation on a model

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Responses:** `200` Successful Response, `422` Validation Error

---

## Async Synthesis Jobs

### `POST /api/v1/jobs/synthesize`

Enqueue an async synthesis job

**Request body:** `SynthesizeRequest`

**Responses:** `202` Successful Response, `422` Validation Error

### `GET /api/v1/jobs/{job_id}`

Poll an async synthesis job

| Param | In | Type | Required |
|---|---|---|---|
| `job_id` | path | string | yes |

**Responses:** `200` Successful Response, `422` Validation Error

---

## Paradigm Transformation

### `POST /api/v1/model/{model_id}/transform-paradigm`

Transform a model into another modeling paradigm

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |

**Request body:** `TransformParadigmRequest`

**Responses:** `200` Successful Response, `422` Validation Error

---

## Connectors & Introspection

### `GET /api/v1/connectors`

List database connections (URIs masked)

**Responses:** `200` Successful Response

### `POST /api/v1/connectors`

Register an external database connection (ADMIN+)

**Request body:** `ConnectionCreateRequest`

**Responses:** `201` Successful Response, `422` Validation Error

### `POST /api/v1/connectors/introspect`

Introspect a saved connection into a data model

**Request body:** `IntrospectRequest`

**Responses:** `201` Successful Response, `422` Validation Error

### `DELETE /api/v1/connectors/{connection_id}`

Delete a database connection (ADMIN+)

| Param | In | Type | Required |
|---|---|---|---|
| `connection_id` | path | string | yes |

**Responses:** `204` Successful Response, `422` Validation Error

---

## Offline DDL Import

An exported DDL file becomes a model without the appliance connecting to
anything. Every import is reconciled against counts read from the file by a
counter that shares no code with the parser; the model is stored with
`reconciliation_status` `reconciled` or `unreconciled` and the full report.

### `GET /api/v1/import/dialects`

The dialects a file can be imported from, each with `evidence`: `genuine
export` (tested on fixtures written by the database's own export tool) or
`documentation-derived` (tested only on a fixture written from the vendor's
documentation). Signed-in callers.

**Responses:** `200` Successful Response

### `POST /api/v1/import/ddl`

Import an exported DDL file into a new model (MEMBER+). Multipart form.

| Param | In | Type | Required |
|---|---|---|---|
| `workspace_id` | query | string | yes |
| `file` | form | file (UTF-8 or UTF-16, with or without a BOM; at most 10 MB) | yes |
| `dialect` | form | `oracle`, `postgres`, `tsql` (SQL Server) or `snowflake` | yes |
| `title` | form | string | no |

The response carries `model_id`, `status` (`reconciled` or `unreconciled`), the
entity and relationship counts, and the report. A statement the parser does not
understand is a named failure in the report, never skipped. Each imported
column carries `source_data_type`, its type exactly as the file declared it
(`VARCHAR2(255 CHAR)`, `[dbo].[Name]`), beside the normalized `data_type`, and
`source_default_value`, its DEFAULT as declared (`now()`, `(getdate())`),
beside the normalized `default_value`, which exports and comparisons use; a
SQL Server user-defined type resolves to its base type from the file's
`CREATE TYPE … FROM`. Composite keys, composite foreign keys, and UNIQUE and
CHECK constraints over several columns are in the model.

**Responses:** `201` Model created (reconciled or not), `403` Below MEMBER,
`413` File too large, `422` Unknown dialect, or nothing in the file could be
imported (the report is in `detail`)

### `POST /api/v1/model/{model_id}/drift`

Compare a saved model with a freshly imported DDL file of the deployed schema (VIEWER+)

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `file` | form (multipart) | file | yes |
| `dialect` | form | string, as for `/import/ddl` | yes |
| `format` | form | `markdown`, `html` or `json` | no (default `markdown`) |

The file is imported in memory and never saved. The response carries
`summary` (breaking, non-breaking, informational, total, verified fields
affected) and `files` (`drift_report.md`, `.html` or `.json`). Columns are
matched by name, so a rename is a removal and an addition; each drift names
its classification rule (D1-D19, listed in the user guide).

**Responses:** `200` Successful Response, `403` Below VIEWER, `413` File too large, `422` Nothing importable or unknown dialect

### `GET /api/v1/model/{model_id}/import-report`

The import's reconciliation report (VIEWER+): counts from the file and counts
imported, for tables and partitions separately; every gap and failure by
statement; what was not imported and why; what the model cannot hold yet.

| Param | In | Type | Required |
|---|---|---|---|
| `model_id` | path | string | yes |
| `format` | query | `markdown` (default) or `json` | no |

**Responses:** `200` Successful Response, `404` The model was not imported from a file

---

## Source-to-Target Mapping

A mapping document maps a source model's columns to a target model's, both in
one workspace. Every response that returns a document gives every target
column with its status, completeness and drift:

- **Status:** `mapped`, explicitly unmapped (`constant`, `derived`,
  `not_yet_mapped`), `pending` (only proposals), `silent` (nothing), or
  `drift`.
- **Completeness:** "N of M target columns mapped, K explicitly unmapped, S
  silent", with pending proposals and accepted entries counted separately. A
  pending proposal never counts as mapped, and the document is complete only
  when nothing is pending, silent or in drift.
- **Drift:** an entry whose source or target column no longer exists is
  flagged and kept, never dropped.

Reading is VIEWER. Proposing and deciding is MEMBER. **Every decision** (accept,
reject, write, change, remove) takes the decider from the signed-in caller and
records who decided, when, and the evidence shown, in an append-only record. A
request with an API key is refused with `403`, because a decision needs a
person. No request body can name a decider (`422`).

### `GET /api/v1/model/{model_id}/mappings`

The mapping documents whose target is this model (VIEWER+).

### `POST /api/v1/model/{model_id}/mappings`

Start a mapping into this model (MEMBER+). Body: `source_model_id`, `title`,
and optionally `source_system` and `target_system`. A source model in another
workspace answers `404`. **Responses:** `201`, `403`, `404`.

### `GET /api/v1/mappings/{document_id}`

The document, as above (VIEWER+).

### `DELETE /api/v1/mappings/{document_id}`

Delete the document, with its entries and proposals. Its decisions stay in the
record (MEMBER+). **Responses:** `204`.

### `POST /api/v1/mappings/{document_id}/proposals`

Propose candidates for each target column that has no entry (MEMBER+). Each
proposal gives its source columns, a **name similarity** and a **type
compatibility** (each 0 to 1) and a **confidence** (0.7 × name + 0.3 × type),
with the method and its version. Proposals under 0.6 are not made, and each
column gets at most three. A proposal is `pending` and counts as nothing until
a person decides it.

### `POST /api/v1/mappings/{document_id}/proposals/{proposal_id}/accept`

Accept a pending proposal (MEMBER+, a person). An optional body, `sources` and
`fields`, edits it first, and is recorded as `edited`. **Responses:** `200`,
`403` (an API key), `404`, `422` (not pending, or refused by the rules).

### `POST /api/v1/mappings/{document_id}/proposals/{proposal_id}/reject`

Reject a pending proposal (MEMBER+, a person).

### `POST /api/v1/mappings/{document_id}/entries`

Write an entry for one target column (MEMBER+, a person). Body: `target`
(`entity`, `column`) and `kind` (`mapped`, `constant`, `derived`,
`not_yet_mapped`). A `mapped` entry also has `sources` (one for one-to-one,
several for many-to-one, which must state `rule_description` or `logic`). The
optional `fields` are the STTM fields:

- `transformation_type`, one of OpenLineage's `IDENTITY`, `TRANSFORMATION`,
  `AGGREGATION`, `JOIN`, `GROUP_BY`, `FILTER`, `SORT`, `WINDOW`,
  `CONDITIONAL`;
- `rule_description`, `logic`, `join_filter`, `lookup`,
  `default_null_handling`;
- `scd_type` (0–6) and `step_kind` (`manual` or `automated`);
- `control_rule`, and the three reconciliation fields;
- `masking`.

A person's entry is accepted by being written, recorded as `authored`, or
`declared_unmapped` for the three unmapped kinds. **Responses:** `201`, `403`,
`422` (with the reason).

### `PUT /api/v1/mappings/{document_id}/entries/{mapping_key}`

Change an entry (MEMBER+, a person): `kind`, `sources` and `fields`, as above.

### `DELETE /api/v1/mappings/{document_id}/entries/{mapping_key}`

Remove an entry (MEMBER+, a person). Its target column is reported silent.

### `GET /api/v1/mappings/{document_id}/export`

The document as `format` = `csv` (default), `markdown`, `html` or `json`
(VIEWER+). Each has one row per target column, with the completeness line at
the top. The columns are:

- the mapping's ID, version, status, approver, approval date and last
  decision;
- the target's system, table, column, type, nullable and key;
- the source's system, schema, table, column and type;
- the transformation type, rule, logic, join and filter, lookup, and default
  and null handling;
- SCD type, manual or automated, the control rule, and the three
  reconciliation fields;
- masking, and the classification and CDE carried from the source columns'
  dictionary fields;
- drift, and any pending proposals with their scores.

**Responses:** `200` (`{format, filename, content}`), `422` for another format.

### `GET /api/v1/mappings/{document_id}/lineage`

One target column's lineage (VIEWER+), with `entity` and `column` in the query:
its entry, its source columns as they stand now, its drift flags, and every
decision about it with its evidence.

---

## ModelBox Trainer

### `GET /api/v1/trainer/assignments`

List assignments in the caller's workspaces

**Responses:** `200` Successful Response

### `POST /api/v1/trainer/assignments`

Create a data-modeling assignment

**Request body:** `AssignmentCreateRequest`

**Responses:** `201` Successful Response, `422` Validation Error

### `GET /api/v1/trainer/assignments/{assignment_id}`

Fetch an assignment

| Param | In | Type | Required |
|---|---|---|---|
| `assignment_id` | path | string | yes |

**Responses:** `200` Successful Response, `422` Validation Error

### `POST /api/v1/trainer/grade`

Auto-grade a student ERD against expected invariants

**Request body:** `GradeRequest`

**Responses:** `200` Successful Response, `422` Validation Error

### `POST /api/v1/trainer/socratic/step`

Get the tutor's next guiding question

**Request body:** `SocraticStepRequest`

**Responses:** `200` Successful Response, `422` Validation Error

---

## System

### `GET /health`

Liveness & readiness probe

**Responses:** `200` Successful Response

---

