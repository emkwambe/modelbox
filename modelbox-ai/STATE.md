# ModelBox AI — state

*Regenerated 2026-09-30 on `sprint-9/step-3-mapping`, branched from
`main` at `4afdccb`. This file is rewritten at every stop, merge, deploy and
tag; a figure here is the output of a command run for it, not a copy from
another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `4afdccb` | T-SQL `LIKE` character classes kept in PostgreSQL (#31), on the dbt export on imported schemas and seed data under every constraint (#30), on computed columns as PostgreSQL generated columns (#29), on type, identity and sequence mappings to PostgreSQL (#28), on STATE.md and OUTSTANDING_ISSUES.md for the released v1.12.0 (#27), on the v1.12.0 release preparation (#26), on claims, a tested rollback to v1.11.1 and the records for v1.12.0 (#25), the engagement journey, the Verify control and the drift panel (#24), two silent-loss fixes and workspace members (#23), the drift report (#22), dictionary fields, a classification scale and per-field verification (#21), exported DDL applied to PostgreSQL and the data dictionary rebuilt (#20), keys, constraints and the saved-model journey (#19), SQL Server import and original type text (#18), the offline DDL import for Oracle, PostgreSQL and Snowflake (#17), the PostgreSQL and Snowflake fixtures (#16), the Oracle and SQL Server fixtures (#15) and records and CI hygiene (#14) |
| `v1.12.0` | `d38d6ec` | tagged 2026-09-29 22:28 -04:00; published by the gated release workflow (run 36659993511: gate, backend and frontend images all green); verified on the published images (run 36660321337, below) |
| `v1.11.1` | `e8d9ac1` | tagged 2026-09-29 (UTC), published by run 36516574170; superseded by v1.12.0, tag and images kept |
| `v1.11.0` | `d5822f1` | tagged 2026-09-29 (UTC), published by run 36511971512; superseded by v1.11.1, tag and images kept |
| `sprint-9/step-3-mapping` | this branch | source-to-target mapping with proposals, and the collation gap (below) |
| `sprint-9/step-2c-like-patterns`, `sprint-9/step-2b-dbt-export`, `sprint-9/step-1b-computed-columns`, `sprint-9/step-1a-type-mappings`, `sprint-9/step-0-state`, `release/v1.12.0`, `sprint-8/step-8a-claims-and-records`, `sprint-8/step-7-engagement-journey`, `sprint-8/step-6-members-and-fixes`, `sprint-8/step-5-drift-report`, `sprint-8/step-4b-dictionary-verification`, `sprint-8/step-4a-dictionary-export`, `sprint-8/step-3-journey`, `sprint-8/step-2b-sqlserver`, `sprint-8/step-2a-import-core`, `sprint-8/step-1-5-pg-snowflake-fixtures`, `sprint-8/step-1-export-fixtures`, `sprint-8/engagement-toolkit`, `sprint-7/secure-by-default`, `sprint-7/records`, `release/v1.11.0`, `fix/v1.11.1`, `sprint-7/close` | kept | the records cite their commits and runs |

## In progress on this branch: source-to-target mapping, with proposals

A mapping document maps a source model's columns to a target model's. Every
target column is one of:

- **mapped**, one-to-one or many-to-one, with the transformation stated;
- **explicitly unmapped**: a constant, derived, or not yet mapped;
- **pending**: only proposals, no decision;
- **silent**: nothing;
- **in drift**: its source or target column is gone. The entry is flagged and
  kept, never dropped.

The document states "N of M target columns mapped, K explicitly unmapped, S
silent", with accepted and pending counted separately. It is complete only
when nothing is pending, silent or in drift.

**Proposals.** ModelBox proposes candidates with a name-similarity score, a
type-compatibility score and a confidence. A proposal counts as nothing until
a person accepts, edits or rejects it. Every decision records who made it,
when, and the evidence shown, in an append-only record. API keys cannot
decide. There is a canvas panel with an editor, exports (CSV, Markdown, HTML,
JSON) and a lineage view per target column.

**Migration 0030** (additive, owner-approved) adds four mapping tables and
the `mapping_decisions` ledger. Columns are referenced by name and stable id,
not by foreign key, so drift is computed on read. A downgrade loses every
mapping and keeps the decisions record, which a re-upgrade adopts. Tests:

- `test_mapping` and `test_mapping_api`, where the Oracle HR import is mapped
  to a target derived from it with every column accounted for, plus the four
  negative controls;
- `test_ledger_roles_postgres`;
- `test_0030_…` in `test_migration_0015_to_head_populated`.

The first commit on this branch names a `collation` export gap for a SQL
Server model exported to PostgreSQL, on each table with text keys, a UNIQUE on
text or a pattern CHECK (16 of AdventureWorks' 71 tables).

## T-SQL LIKE character classes (on `main`, #31)

A SQL Server CHECK whose `LIKE` pattern has a character class (`[A-Za-z]`,
`[0-9]`, ranges and sets, with `%` and `_`) is written for PostgreSQL as
`SIMILAR TO`, which reads the brackets the same way. PostgreSQL's `LIKE`
reads them as literal text, so the CHECK copied verbatim was stricter than
the source's. A pattern outside that subset is a named export gap quoting
it, and other targets name such a CHECK as a gap. The seed generator draws
from the `LIKE` branch again.

On PostgreSQL 16.15, in the Artifact Fidelity Harness job
(`test_dbt_on_postgres`), AdventureWorks' `CK_ProductInventory_Shelf`
accepts one letter and `'N/A'` and refuses two letters. The seed's one-letter
shelves load, and the same CHECK without the translation refuses `'B'` (the
negative control). On `73c5680`, run 36715872452: 32 passed, 1 skipped.

## dbt on imported schemas, and seed data (on `main`, #30)

A dbt project exported from an imported schema did not build on
PostgreSQL. Its staging models cast to the source's own types (Oracle's
`NUMBER(4,0)`) and left mixed-case names unquoted. The execution evidence
behind the dbt claims covered only the reference models, in DuckDB. Now, with
a dialect, each staging model casts to the type the DDL export writes for it,
and every name that is not lower snake case is quoted in the SQL and in
`schema.yml`. The export panel shows the dialect picker for dbt.

The seed generator's rows satisfy every primary key, UNIQUE, foreign key and
CHECK constraint the model declares. Each column is generated for its target
type, and computed columns are not written. A row no values can satisfy is
left out and counted in the response's `rows_skipped`.

`test_dbt_on_postgres` runs in the Artifact Fidelity Harness job against the
appliance's PostgreSQL 16.15, for Oracle HR, Oracle CO, Pagila and
AdventureWorks. The product's seed rows load with none refused and every
table full. `dbt build` passes, and a duplicate grain key and an orphan
foreign key each fail the test that guards them. There are three controls: a
duplicate refused by the database, the seed unquoted refused, and the project
cast to the source's types failing to build. On `a3dad48`, run 36711138855:
29 passed, 1 skipped (Pagila's unquoted control: every name there is lower
case). PL-007 and PL-014 state the new evidence and its limit.

## Computed columns as generated columns (on `main`, #29)

A SQL Server computed column is exported to PostgreSQL as
`GENERATED ALWAYS AS (...) STORED` where every part of its expression is on
the export's allowlist: column references, numeric and string literals,
arithmetic, `ISNULL` written as `COALESCE`, and `CONVERT` written as `CAST`. A
`+` with a string on either side is written `||`. Any other call is a named
export gap quoting the expression as the file declared it. Each generated
column is labelled "virtual in source, stored in target", or "stored in
source" for a `PERSISTED` one, with its type and how it was chosen.
AdventureWorks exports 7 generated columns and names 3 gaps, both counts
derived in the tests from the file's own text. Migration 0029 (additive,
nullable) stores each expression and its `PERSISTED` flag. The Backend
Pytest (Postgres) job applies the export and checks the computed values
against values computed from the same inputs
(`test_generated_columns_on_postgres`).

Also in #29: comments and docs that cited documents kept outside this
repository now state their reasons themselves.

## Type, identity and sequence mappings (on `main`, #28)

What changes in a PostgreSQL export of a SQL Server or Oracle model:
- **Plain mappings.** SQL Server `money`, `smallmoney` and `bit` are written
  as `NUMERIC(19, 4)`, `NUMERIC(10, 4)` and `BOOLEAN`. A `bit` column's 0
  and 1 in defaults and CHECK constraints are written `FALSE` and `TRUE`.
  These are exact, so none is a gap.
- **Extension options.** `hierarchyid` is written as `LTREE`, and
  `geography` as PostGIS `GEOGRAPHY`, only when the export says the target
  has the extension (`target_has_ltree`, `target_has_postgis`, off by
  default, in the API and the export panel). The file then starts with
  `CREATE EXTENSION IF NOT EXISTS`; otherwise the column is a named gap.
- **Identity columns** keep their seed and increment:
  - on an integer type, as `GENERATED BY DEFAULT AS IDENTITY`;
  - on Oracle's `NUMBER(*,0)`, which PostgreSQL cannot make an identity
    column, as a sequence default with the same start and increment, named
    as a gap.

  A column an Oracle trigger fills from a sequence is a named gap.
- **Sequences.** A PostgreSQL model's sequences are created, and its
  `nextval` defaults kept.

The importer keeps what it dropped before: identity seeds and increments,
`CREATE SEQUENCE` with its options, and which Oracle trigger fills a column
from which sequence. Migration 0028 (additive, nullable) stores them in
`entity_columns.identity` and `data_models.sequences`.

The Backend Pytest (Postgres) job applies each mapping case to the
appliance's PostgreSQL 16.15, and the geography case to a PostGIS image
pinned by digest. It reads the result back from the catalog
(`test_type_mappings_on_postgres`). On `3907f36`, run 36678387171, every
one of those tests passed in that job, as did 0028's upgrade and downgrade
tests. Negative controls remove each mapping,
and simulate an importer that loses identity columns or sequences
(`test_type_mappings`).

## Offline DDL import (v1.12.0)

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

## Claims, rollback and records (v1.12.0)

The Proof Log gains PL-018 to PL-025, one per claim of the release (DDL import
per dialect, reconciliation, DDL applied to PostgreSQL, what "verified" means,
the drift report, the migration diff's data-loss labelling, member management,
the engagement journey), each citing tests read as passed on `main` at
`4ea57f7` (run 36644605175); PL-016's "no API or UI to manage members" is
struck. A claims-guard test keeps barred wording off every public surface.
The Black-box Acceptance job downgrades the database to v1.11.1's migration
head and runs v1.11.1's published images on it (`test_rollback.py`); what a
downgrade loses is stated in `docs/RELEASE_NOTES_v1.12.0.md`.

## The engagement journey (v1.12.0)

The canvas gains two panels. **Dictionary** lists every field holding a value
with its status and the verified count; an APPROVER, ADMIN or OWNER verifies
one field or a selection and sees each of the three conditions as the server
found it, and why a field stayed pending; a MEMBER or VIEWER sees no control.
**Drift report** uploads a deployed schema's DDL and lists each drift with its
class, rule and verified-field flag, an unreconciled import warned about first.
Two defects the journey found are fixed: an imported model stored no
positions and opened with every table stacked at one point (it is now laid
out on open, an unsaved change that Save keeps), and the column editor grew
past the top of the canvas once it held the dictionary fields, leaving its
close button out of reach (both editors now scroll within the canvas).

`e2e/` is a Playwright spec, run in CI by the Engagement Journey job
against the appliance in configuration B: import the genuine Oracle HR export
(zero gaps), edit a column's business name and a table's owner and see them
survive a reload, verify a field and see the counts change, edit it back to
pending, compare the drifted HR export against its expected manifest, and
export PostgreSQL DDL (no gaps header for HR; AdventureWorks names its
computed-column gaps). The same spec imports the documentation-derived
Snowflake fixture and asserts the unreconciled warning comes first and that
its fields cannot be verified. The black-box suite adds B10 (HR and
AdventureWorks import over HTTP with zero gaps) and C4 (HR imports air-gapped).

## Two silent-loss fixes, and workspace members (v1.12.0)

The migration diff pairs columns by internal id only between versions of the
same model, and by name between separately saved models; an uncertain rename
is a removal plus an addition, and every statement that drops data says so in
the DDL and in the diff panel. The MetricFlow export states a composite
primary key as a `primary_entity`, keeps its members' one-column foreign keys
as joins, and names every key it cannot state as an export gap (composite
foreign keys, composite primary keys, a key that is also a foreign key).

Workspace OWNERs and ADMINs add existing users, change roles and remove
members (API and `/settings/members`): no role above your own, an ADMIN
cannot make an OWNER, the last OWNER stays, and a removed member's keys stop
at once. MEMBER_ROLE_CHANGED and MEMBER_REMOVED are back in the audit
vocabulary (migration 0027). The black-box suite adds its VIEWER through the
API.

## The drift report (v1.12.0)

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

## Dictionary fields and per-field verification (v1.12.0)

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

## DDL applied to PostgreSQL, and the dictionary (v1.12.0)

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

## Keys, constraints and the saved-model journey (v1.12.0)

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

## SQL Server import (v1.12.0)

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

## DDL fixtures (v1.12.0)

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

Migration head: `0029_computed_columns` on `main`;
`0030_source_to_target_mapping` on this branch (`alembic heads`).

## Versions

- Latest tag on the remote: **`v1.12.0`**, at `d38d6ec`.
- Version stamp in the code: **1.12.0** on `main` and this branch
  (`scripts/check_versions.py`: all version stamps agree).
- Published images: `ghcr.io/emkwambe/modelbox-backend` and
  `ghcr.io/emkwambe/modelbox-frontend`, `1.12.0` (also `1.12` and `latest`).
  `1.11.1` and `1.11.0` remain published and are superseded.

## Status

Not for deployment on a shared network before v1.11.0 (README, Status).
v1.12.0 is the release to use.

## Repository contents

Sprint prompts, sprint plans and research documents moved out of this
repository on 2026-09-28. Git history is unchanged.

## What v1.12.0 ships

The sections above: offline DDL import for Oracle, SQL Server and PostgreSQL
(Snowflake documentation-derived and uncertified), each import reconciled;
one representation for keys and constraints, with saved models that reopen as
saved; DDL export applied to a real PostgreSQL, gaps named; a data dictionary
with per-field verification and a classification scale; a drift report;
workspace members and roles; and the engagement journey run in CI. Upgrading
runs migrations 0023–0027 through the migrate service. Notes:
`docs/RELEASE_NOTES_v1.12.0.md`. Index: `CHANGELOG.md`.

## What v1.11.x shipped

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
(superseded).

## Published-image verification

`.github/workflows/verify-release.yml` runs the black-box suite against the
images a release published, pulled on a runner that never built them, after
every successful release and on demand.

For v1.12.0 it ran on the release's completion (run 36660321337, on `main` at
`d38d6ec`, success). The compose file matched the tag's. It pulled the images
by the digests release run 36659993511 pushed and built none:
`modelbox-frontend@sha256:2a862f9f297ebdb4a643fbadc6b3cbadf1ba85863bf782e8b29d0d50f7ba9eaf`
and
`modelbox-backend@sha256:4bc5c3e28e34871c6e4b72942bddc40b948c052fd0ee222bce76a6ea92c96689`.
Configuration A passed (1 test), B passed (15), the upgrade passed (1), the
insecure profile had 10 passed and 5 expected failures, and C passed (5). The
rollback and journey checks are not part of this workflow; they ran on the
release commit in CI run 36659466821.

For v1.11.1 it ran on `main` at `627686d` (run 36518642808, success): A 1, B 13,
upgrade 1, insecure profile 8 passed and 5 expected failures, C 4.
