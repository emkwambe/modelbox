# Drift fixtures

The deployed-schema side of the drift report's evidence (Sprint 8 Step 5).
Every `.sql` and `.manifest.json` here is genuine tool output, written by the
same exporters as the fixtures in `../ddl/`, against the same databases, after
one more step: `.github/workflows/ddl-fixtures.yml` applies the committed
ALTER script in `<dialect>/changes/` to the database, then exports it again.
Each fixture's provenance header names the script and its SHA-256. The
workflow regenerates these on every run and fails unless the committed copies
are what the tools produce. To change one, change its ALTER script and commit
what the workflow uploads.

| Fixture | Baseline | ALTER script |
| :-- | :-- | :-- |
| `oracle/hr.sql` | `../ddl/oracle/hr.sql` (Oracle HR, DBMS_METADATA) | `oracle/changes/hr.alter.sql` |
| `postgres/pagila.sql` | `../ddl/postgres/pagila.sql` (Pagila, pg_dump) | `postgres/changes/pagila.alter.sql` |
| `tsql/adventureworks.sql` | `../ddl/tsql/adventureworks.sql` (AdventureWorks2022, SMO) | `tsql/changes/adventureworks.alter.sql` |

## The expected drifts

Each ALTER script numbers its statements, and `<stem>.expected.json` beside it
names the drift each statement makes and the class the written rules give it
(the user guide's drift report section). The manifests were written from the
scripts, before any drift fixture was exported or any drift code existed, and
never from ModelBox's output. `test_drift_fixtures.py` holds the report to
them: every expected drift reported, none invented, each classified as the
manifest says, and every numbered statement accounted for.

## Licences

The drifted schemas are the sample schemas of `../ddl/`, altered; their
licences are the ones given in `../ddl/README.md` (Oracle sample schemas and
Microsoft SQL Server samples under the MIT licence; Pagila, a port of MySQL's
Sakila, under the licences quoted there). The ALTER scripts and expected-drift
manifests are our own text.
