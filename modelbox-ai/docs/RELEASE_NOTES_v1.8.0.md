# ModelBox AI — v1.8.0 Release Notes

**Tag:** `v1.8.0`  ·  **Cut from:** `main`  ·  **CI:** green, six required checks

**This is the release where the product's core claim becomes true.**

Every certified artifact now parses in the toolchain that consumes it, on all
five reference models. Not "we believe it does" — a test hands each artifact to
`dbt`, `protoc`, `fastavro`, `sqlfluff` or DuckDB on every push, and the build
fails if any of them refuses.

Three known defects remain. They are named below with their test identifiers.

---

## What changed

The audit behind this programme catalogued 76 defects across the exporters, each
recorded as a failing test rather than a paragraph. This release closes 74 of
them. One more was found during the work and is also closed; two more were
found and are scheduled.

| Emitter | Before | Now |
| :-- | :-- | :-- |
| **MetricFlow** | Rejected by `dbt parse` on 5/5 models | Parses on 5/5 |
| **dbt** | Could not parse without a hand-written sources file | Runs as exported |
| **ODCS** | A hybrid of two standards, conforming to neither | Valid ODCS v3.1.0 |
| **Protobuf** | Field tags shifted when a column was inserted | Tags are stable identities |
| **SQL DDL** | No `NOT NULL`; emitted in declaration order | Constraints emitted; dependency-ordered |
| **Cube** | `SUM()` over surrogate keys; `BOOLEAN` typed as string | Keys excluded; booleans typed |

### Semantic layers that compile

MetricFlow had seven distinct defects and none was visible alone, because
`dbt parse` failed on the first. Metrics now carry labels, model references
point at the models the dbt exporter actually emits, aggregations are mapped to
MetricFlow's vocabulary, and every semantic model declaring measures carries
`defaults.agg_time_dimension`.

An entity with no temporal column declares **no measures** and is
dimension-only. A measure needs a time axis; inventing one would be worse than
omitting it.

### Data contracts you can depend on

**Protobuf field tags are now stable identities**, not list positions. A tag is
a wire contract: a deployed consumer decodes field 3 as whatever field 3 meant
when its copy of the schema was generated. Inserting a column previously
renumbered every later field, silently breaking every consumer. Tags now come
from an identity allocated once per column and never reused, gaps included.

`NUMERIC` and `DECIMAL` carry as exact decimal strings rather than `double`. A
`NUMERIC(18,2)` ledger balance is exact by definition, proto3 has no
fixed-point scalar, and Avro already emitted a decimal logical type for the
same column — so the two contracts had disagreed about the same value.

**ODCS output is valid v3.1.0.** It previously stamped `v0.9.3` while using v3
vocabulary and carrying an `info:` block from a different standard entirely.
Foreign keys now travel as property-level `relationships`, `required` derives
from declared nullability rather than restating the primary-key flag, and
non-standard keys travel as `customProperties` rather than invented vocabulary.

### SQL that deploys

DDL is emitted in dependency order, so a model not authored parent-first no
longer produces a script that aborts on its first statement. `NOT NULL` is
emitted from the declared constraint.

**Certified dialects:** `postgres`, `snowflake`, `redshift`, `duckdb` — verified
by two independent grammars on every push, and for DuckDB by executing the
emitted DDL against the engine.

**Preview — not deployment-verified:** `bigquery`, `databricks`, `clickhouse`,
and the LookML emitter. These transpile, but we do not verify that the engine
accepts the result, and it currently does not without hand-editing. The
distinction now appears **in the export picker before you generate**, with a
standing warning while a preview dialect is selected.

Redshift was certified and previously unreachable from the export UI;
ClickHouse was preview and offered without qualification. Both are fixed, and a
test now asserts the UI's dialect list matches the backend's.

---

## Known open defects

Three, each an executing test. Run the burn-down with:

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 pytest tests/test_artifact_fidelity.py -m "not preview" -q
```

| ID | Defect | Test |
| :-- | :-- | :-- |
| **H1** | Generated seed data ignores declared column lengths | `test_seed_respects_declared_length[healthcare-ehr]` |
| **H1** | Generated seed data ignores declared quality rules, so it violates the contract the same model exports | `test_seed_respects_quality_rules` |
| **H10** | ODCS quality entries use a `rule` key that does not exist in v3.1.0; the correct shape is `{id, metric, mustBe*}` | `test_odcs_quality_entries_use_v3_vocabulary` |

All three are assigned to v1.9.0.

A further **18** expected failures are marked `@preview` — the three preview
dialects and LookML. They are labelled rather than scheduled and are not
counted as debt. Inspect them with `pytest -m preview`.

## Limits

- `dbt parse` proves a project resolves. It does not execute against a
  warehouse, so it does not prove the SQL returns what you expect. `dbt build`
  on generated seed data is v1.9.0, and it is blocked by H1.
- LookML has no offline parser, so its output is structurally asserted only and
  is unverifiable here by construction.
- No ODCS schema validator is installed. Conformance is asserted against the
  specification's documented constructs, read for what this emitter produces —
  a scoped check, not an audit of the standard.
- An administrator can still bypass the required CI checks; `enforce_admins`
  is deliberately off.

## Upgrade notes

- **Breaking (artifact shape).** Protobuf field tags now derive from column
  identity rather than position, so tags emitted before this release may differ
  from tags emitted after it for the same model. This is the fix, not a
  regression — but regenerate and re-publish any `.proto` you have distributed,
  and treat the change as a schema version bump for existing consumers.
- ODCS documents change shape substantially. Anything parsing the old hybrid
  output will need updating; anything expecting valid v3.1.0 will now work.
- dbt projects gain `_sources.yml` and, where quality rules are declared,
  `packages.yml`. If you were hand-writing a sources file, delete it — dbt
  rejects the duplicate.
- Container image tags move to `v1.8.0`. No database migration.
