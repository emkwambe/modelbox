# ModelBox AI — state

*Regenerated 2026-09-29 on `sprint-8/step-2b-sqlserver`, branched from
`main` at `930a07f`. This file is rewritten at every stop, merge, deploy and
tag; a figure here is the output of a command run for it, not a copy from
another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `930a07f` | offline DDL import for Oracle, PostgreSQL and Snowflake (#17), on the PostgreSQL and Snowflake fixtures (#16), the Oracle and SQL Server fixtures (#15) and records and CI hygiene (#14) |
| `v1.11.1` | `e8d9ac1` | tagged 2026-09-29 (UTC); published by the gated release workflow (run 36516574170: gate, backend and frontend images all green) |
| `v1.11.0` | `d5822f1` | tagged 2026-09-29 (UTC), published by run 36511971512; superseded by v1.11.1, tag and images kept |
| `sprint-8/step-2b-sqlserver` | this branch | SQL Server import and original type text (below) |
| `sprint-8/step-2a-import-core`, `sprint-8/step-1-5-pg-snowflake-fixtures`, `sprint-8/step-1-export-fixtures`, `sprint-8/engagement-toolkit`, `sprint-7/secure-by-default`, `sprint-7/records`, `release/v1.11.0`, `fix/v1.11.1`, `sprint-7/close` | kept | the records cite their commits and runs |

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

## In progress on this branch: SQL Server import

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

Migration head: `0024_column_source_type` on this branch (`0023_import_reconciliation` on `main`).

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
