# ModelBox AI — state

*Regenerated 2026-09-29 on `sprint-8/step-5-drift-report`, branched from
`main` at `3dde631`. This file is rewritten at every stop, merge, deploy and
tag; a figure here is the output of a command run for it, not a copy from
another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `3dde631` | dictionary fields, a classification scale and per-field verification (#21), on exported DDL applied to PostgreSQL and the data dictionary rebuilt (#20), keys, constraints and the saved-model journey (#19), SQL Server import and original type text (#18), the offline DDL import for Oracle, PostgreSQL and Snowflake (#17), the PostgreSQL and Snowflake fixtures (#16), the Oracle and SQL Server fixtures (#15) and records and CI hygiene (#14) |
| `v1.11.1` | `e8d9ac1` | tagged 2026-09-29 (UTC); published by the gated release workflow (run 36516574170: gate, backend and frontend images all green) |
| `v1.11.0` | `d5822f1` | tagged 2026-09-29 (UTC), published by run 36511971512; superseded by v1.11.1, tag and images kept |
| `sprint-8/step-5-drift-report` | this branch | the drift report and drifted fixtures (below) |
| `sprint-8/step-4b-dictionary-verification`, `sprint-8/step-4a-dictionary-export`, `sprint-8/step-3-journey`, `sprint-8/step-2b-sqlserver`, `sprint-8/step-2a-import-core`, `sprint-8/step-1-5-pg-snowflake-fixtures`, `sprint-8/step-1-export-fixtures`, `sprint-8/engagement-toolkit`, `sprint-7/secure-by-default`, `sprint-7/records`, `release/v1.11.0`, `fix/v1.11.1`, `sprint-7/close` | kept | the records cite their commits and runs |

## Offline DDL import (on `main`)

An exported DDL file (Oracle, PostgreSQL, or Snowflake as documentation-derived)
is uploaded at `/import` and becomes a model, with nothing connected to. Every
import is reconciled against counts taken from the file by a counter that shares
no code with the parser; the model is saved `reconciled` or `unreconciled`
(migration 0023) with its report, served as Markdown or JSON. A statement the
parser returns as an opaque `Command` is a named failure. Partitions are
metadata of their parent. The genuine Pagila, Oracle HR and Oracle CO fixtures
import with zero gaps against their catalog manifests (Pagila as 15 tables and
55 partitions); the Snowflake fixture fails by name on its HYBRID TABLE and is
saved unreconciled.

## In progress on this branch: the drift report

A drift report compares a saved model (the documented design) with a fresh,
unsaved import of a DDL export of the deployed schema, through the schema-diff
engine's one comparison core, pairing columns by name: a rename is a removal
and an addition, with a "possible rename" hint only where type and position
match. Each drift is classified by nineteen written rules (D1-D19) listed in
the user guide; the header names both sources, the model's version, the
import's time and both reconciliation statuses; a drift on a verified
dictionary field is flagged. Markdown, HTML and JSON from
`POST /model/{id}/drift`. The DDL Fixtures workflow applies committed ALTER
scripts to the real Oracle, SQL Server and PostgreSQL databases and exports
them again (`backend/tests/fixtures/ddl_drift/`); the report finds exactly the
drifts each script's hand-written manifest expects. The first drifted Oracle
export found an importer gap (a key declared inside CREATE TABLE), now fixed.

## Dictionary fields and per-field verification (on `main`)

Migration 0026 adds, additively, the dictionary fields a person supplies
(on columns: business name, permissible values, unit, critical data element,
authoritative source, a classification level; on tables: business name,
business owner, IT steward, authoritative source), a classification scale
per workspace (Public, Internal, Confidential, Restricted by default,
editable by its admins; a level in use cannot be deleted), and
`field_attestations`, each field's status and provenance. Existing PII values
are mapped across as "recorded". A field is verified only when an APPROVER
asks and the model is a reconciled import, its definition passes the
machine-checkable ISO/IEC 11179-4 rules, and its provenance is recorded and
is not an AI draft; a verified value that changes returns to pending, and
every status change is an audit event. Synthesis never fills these fields.
The dictionary shows each field's status and "N of M fields verified, K
pending review". The canvas edits the new fields; `/settings/classification`
edits the scale.

## DDL applied to PostgreSQL, and the dictionary (on `main`)

Each certified fixture's exported PostgreSQL DDL (HR, CO, Pagila,
AdventureWorks) is applied to the appliance's own PostgreSQL 16.15 in CI
(`test_ddl_on_postgres`), and tables, columns, keys, checks and descriptions
are counted from that database's catalog and compared with the manifest; the
shortfall must equal the one the export's named gaps predict. Doing so found
statements PostgreSQL refuses: a foreign-key cycle (HR), now closed with
`ALTER TABLE` after every table exists; serial defaults naming sequences and
user-defined types the model does not hold (Pagila); and SQL Server `money`,
`smallmoney`, `bit` and `geography` (AdventureWorks), now written as types
PostgreSQL accepts. Each is a named export gap.

The data dictionary is built once and rendered as Markdown, HTML, JSON and
CSV, with every column field the model holds in a fixed order, relationships with their column pairs
(unresolved ones shown as such), and the source model's reconciliation stated
at the top. HR's and AdventureWorks' dictionaries match their catalog
manifests table by table (`test_dictionary_evidence`).

## Keys, constraints and the saved-model journey (on `main`)

Keys and constraints have one representation: each entity's primary key (in
key order), UNIQUE and CHECK constraints, and each relationship's column
pairs, so composite keys, composite foreign keys and multi-column constraints
are in the model; the column flags are derived from them. Migration 0025
moves stored models to that representation, keeps what it cannot convert
exactly (a relationship saved without columns stays, unresolved) and lists it
per model; it also adds each imported column's DEFAULT as declared. The DDL
importer, the linter (`UNRESOLVED_RELATIONSHIP`), and every exporter read it;
DDL export states composite keys and foreign keys, UNIQUE, CHECK and
`COMMENT ON`, and names each gap. Saved models have an address,
`/canvas/<id>`, and a list at `/models`; a relationship's columns are chosen
when it is drawn; leaving unsaved changes asks first. The round trip (import,
save, reopen, export PostgreSQL DDL, re-import) matches the catalog manifests
of HR, CO and Pagila exactly, and AdventureWorks except for its ten computed
columns, each a named gap.

## SQL Server import (on `main`)

SQL Server joins the import. A script is split at `GO`; `SET` and `USE` are
listed, procedures are listed, and a batch a skip rule matches cannot carry a
table statement with it. A normalizer removes the physical clauses SSMS writes
(ROWGUIDCOL, NOT FOR REPLICATION, index options, filegroups, TEXTIMAGE_ON,
clustering, key order, XML schema collections), keeps a partition scheme as
metadata, and records `WITH NOCHECK`; each rule has a case and a negative
control, and a clustered primary key with options on `[PRIMARY]` is a named
regression test. Constraints added by `ALTER TABLE`, defaults added by
`ADD … DEFAULT … FOR`, `MS_Description` properties and `CREATE TYPE … FROM`
aliases are in the model; other extended properties are listed. Every imported
column in every dialect keeps its declared type text in `source_data_type`
(migration 0024), carried through save and reload. AdventureWorks imports with
zero gaps against its catalog manifest (71 tables, 486 columns, 90 foreign keys,
89 checks, 556 descriptions) in UTF-8 and UTF-16, each with and without a BOM.

## DDL fixtures (on `main`)

`backend/tests/fixtures/ddl/` holds the importer's evidence base. Oracle
(`DBMS_METADATA`, HR and CO, populated), SQL Server (SMO, AdventureWorks2022)
and PostgreSQL (`pg_dump` from the appliance's own 16.15
image, Pagila) are genuine tool output: the DDL Fixtures workflow regenerates
them in fresh containers and fails unless the committed copies match. Each
has a manifest counted from its catalog views. Snowflake is the exception:
one fixture hand-written from Snowflake's `GET_DDL` documentation, labelled
documentation-derived in its header and manifest, with a test that fails if
the label goes or if anything calls Snowflake import certified while it
stands.

Migration head: `0026_dictionary_fields`, on `main` and this branch (no schema change on this branch).

## Versions

- Latest tag on the remote: **`v1.11.1`**, at `e8d9ac1`.
- Version stamp in the code: **1.11.1** (`scripts/check_versions.py`: all
  stamps agree).
- Published images: `ghcr.io/emkwambe/modelbox-backend` and
  `ghcr.io/emkwambe/modelbox-frontend`, `1.11.1` (also `1.11` and `latest`).
  `1.11.0` remains published and is superseded.

## Status

Not for deployment on a shared network before v1.11.0 (README, Status).
v1.11.1 is the release to use.

## Repository contents

Sprint prompts, sprint plans and research documents moved out of this
repository on 2026-09-28. Git history is unchanged.

## What v1.11.1 ships

Secure by default, proven against the running appliance: secrets required at
start-up, the first account from `create-owner`, no self-registration in
production, one published port, a declared minimum role on every route with API
keys scoped to their workspace, an audit trail with an appliance owner and
failed writes reported on `/health`, append-only ledgers under a
least-privilege database role, and a gateway that records every provider
request and records failures as fields (v1.11.0). Every API request that writes
commits, or fails, before its response is sent, and the frontend image runs
package install scripts after every package is installed (v1.11.1).

The black-box acceptance suite (`tests/blackbox/`) proves these against the
containers in CI, including a read-your-writes check fifty times over, and
redacts every credential from its reports. The Security FAQ, the Proof Log and
the acceptance register state what those tests prove.

Notes: `docs/RELEASE_NOTES_v1.11.1.md`, `docs/RELEASE_NOTES_v1.11.0.md`
(superseded). Index: `CHANGELOG.md`.

## Published-image verification

`.github/workflows/verify-release.yml` runs the black-box suite against the
images a release published, pulled on a runner that never built them, after
every successful release and on demand.

For v1.11.1 it ran on `main` at `627686d` (run 36518642808, success). The
compose file matched the tag's. It pulled the backend and frontend images by the
digests release run 36516574170 pushed and built none. Configuration A passed
(1 test), B passed (13), the upgrade passed (1), the insecure profile had 8
passed and 5 expected failures, and C passed (4).
