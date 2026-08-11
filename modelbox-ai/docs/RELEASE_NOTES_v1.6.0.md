# ModelBox AI — v1.6.0 Release Notes

**Tag:** `v1.6.0`  ·  **Cut from:** `main`  ·  **CI:** green, six required checks

Sprint 1 — *Credibility and Gates*. This release deliberately repairs almost no
product defects. It makes them **visible, permanent, and impossible to
reintroduce**, and it stops the documentation asserting things the code does not
do.

If you are evaluating ModelBox, the section that matters most to you is
[Known open defects](#known-open-defects). It is unusual for a release note to
enumerate its own bugs with test identifiers. That is the point: every defect
below is a named, executing test, and the next release is defined as those tests
turning green.

---

## Highlights

### The audit is now the test suite

`backend/tests/test_artifact_fidelity.py` generates every artifact from the five
Requirements Library gold graphs and hands each one to **its own consumer**:

| Artifact | Verified by |
| :-- | :-- |
| SQL DDL | `sqlglot` re-parse · `sqlfluff` per-dialect grammar · **executed on DuckDB** |
| dbt | `dbt parse` in a generated project |
| MetricFlow | `dbt parse` with semantic models present |
| Cube.js | executed in a JS sandbox with Cube's globals shimmed |
| Avro | `fastavro.parse_schema` |
| Protobuf | `protoc` compile, plus a field-tag stability probe |
| ODCS | Open Data Contract Standard v3.1.0 fundamentals |
| Seed data | rows validated against the contract the same model exports |

Nothing is asserted by substring. The previous suite checked strings like
`assert 'syntax = "proto3";' in proto`, every one of which passes on output that
`dbt parse` rejects outright.

**207 tests: 107 pass, 4 skip, 94 expected-failure.**

### Certified and Preview artifacts

Four SQL dialects are **certified** — `postgres`, `snowflake`, `redshift`,
`duckdb`. They re-parse under two independent grammars, and DuckDB additionally
*executes* the emitted DDL on all five gold graphs.

Three dialects — `bigquery`, `databricks`, `clickhouse` — and the **LookML**
emitter are labelled **Preview: not deployment-verified**. They still work as
before; they are no longer advertised as verified. Advertising four and
delivering four is the correct posture for a product selling contract
reliability.

### Build integrity

- CI extended from three gates to six: backend `pytest`, artifact-fidelity
  harness, `tsc --noEmit`, `next build`, `next lint`, alembic-head check, plus a
  version-consistency check. All required for merge to `main`.
- `requirements.lock`, generated inside `python:3.11-slim`, pins the full
  dependency set. Previously every dependency was floor-only (`>=`), so a
  rebuild resolved to whatever PyPI served that day — with `sqlglot` seven major
  versions past its declared floor and no test parsing DDL to catch a change.
- Version is stamped once in `backend/app/__version__.py` and enforced across
  `package.json`, `/health`, compose image tags and release notes. These
  previously disagreed four ways, so an appliance reported a version it was not.

### Governance: the masking claim is retired

`MASK_METADATA_IN_PROMPTS` was documented as obfuscating schema identifiers
before egress. It was an identity function. Rather than build it, the claim is
withdrawn — tokenising column names while the same request carries the source
requirements document verbatim leaks the same semantics, so the control would
not have held.

**The flag now fails startup** rather than silently doing nothing. The
governance story is air-gapped mode, per-task egress classification, and an
append-only egress ledger (v1.8.0).

Application logging is now configured at startup, so the gateway's routing log
line actually emits. It previously did not: the root logger sat at `WARNING` and
nothing called `dictConfig`, so there was no record that a prompt had left.

---

## Known open defects

Each is an executing test carrying its finding ID from
`docs/PROJECT_STATE_REPORT.md` §9. Run the burn-down with:

```bash
cd backend && MODELBOX_FIDELITY_STRICT=1 pytest tests/test_artifact_fidelity.py -m "not preview"
```

| ID | Defect | Test | Count |
| :-- | :-- | :-- | --: |
| **B1** | MetricFlow output does not parse in dbt — missing metric `label`; model ref targets `{name}` where dbt emits `stg_{name}`; `avg` is not a MetricFlow aggregation; no `defaults.agg_time_dimension`; a satellite with no PK gets no primary entity; `month` collides with a reserved granularity keyword | `test_metricflow_parses_in_dbt`, `test_metricflow_metrics_have_label`, `test_metricflow_ref_matches_dbt_model_name`, `test_metricflow_declares_agg_time_dimension`, `test_metricflow_agg_vocabulary_is_valid`, `test_metricflow_semantic_model_has_primary_entity`, `test_metricflow_names_avoid_reserved_granularity`, `test_metricflow_foreign_entity_names_parent_primary` | 24 |
| **H6** | Protobuf field tags are positional, so inserting a column renumbers every later field and breaks wire compatibility with deployed consumers; `NUMERIC` maps to `double`; the emitted filename is not sanitised | `test_protobuf_tags_stable_on_insert` (5), `test_protobuf_decimal_is_not_double` (4), `test_protobuf_filename_is_a_safe_identifier` (1) | 10 |
| **M3** | Cube emits `SUM()` over surrogate and foreign keys, and types `BOOLEAN` columns as `string` | `test_cube_no_measure_over_key` (4), `test_cube_boolean_dimensions_are_boolean` (2) | 6 |
| **H2** | ODCS is stamped `apiVersion: v0.9.3` while the current standard line is v3.1.0 | `test_odcs_apiversion_is_current` | 5 |
| **H2-ext** | The ODCS document is a hybrid of two standards: it omits v3.1.0's required top-level `version` and `status`, and carries an `info:` block belonging to the Data Contract Specification | `test_odcs_conforms_to_v3_fundamentals` | 5 |
| **H2/H4** | ODCS `required` restates the primary-key flag rather than deriving from declared nullability, so every non-key column is declared optional | `test_odcs_required_reflects_nullability` | 5 |
| **H9** | A generated dbt project does not declare the sources its own models reference, so it cannot parse standalone | `test_dbt_project_is_self_contained` | 5 |
| **H4/H3** | No `NOT NULL` is emitted anywhere; a primary key is non-nullable by definition and Databricks rejects a PK on a nullable column | `test_ddl_primary_key_columns_are_not_null` | 5 |
| **M11** | dbt generic tests are emitted with top-level arguments; dbt 1.11 requires them nested under `arguments:` | `test_dbt_no_deprecations` | 4 |
| **H5** | DDL is emitted in declaration order, not topological order, so a model not authored parent-first produces DDL that aborts on its first statement | `test_ddl_order_is_topological` | 4 |
| **H1** | Generated seed data ignores declared lengths and quality rules, so it violates the contract the same model exports | `test_seed_respects_declared_length` (1), `test_seed_respects_quality_rules` (1) | 2 |
| **M7** | A dbt project using quality rules emits `dbt_expectations` tests without declaring the package | `test_dbt_declares_packages_yml` | 1 |
| | | **Total** | **76** |

Counts are per parameterised case, so a defect affecting four of the five
reference models contributes four. Reproduce the table with:

```bash
MODELBOX_FIDELITY_STRICT=1 pytest tests/test_artifact_fidelity.py \
  -m "not preview" -rx --tb=no -q
```

Separately, **18** expected failures are marked `@preview` — the three Preview
dialects and LookML. These are labelled rather than scheduled, and are not
counted as debt. Inspect them with `pytest -m preview`.

### Not defects, but known limits

State these before a reviewer finds them. Two concern the gate itself:

- **A repository administrator can still bypass the required checks.**
  `enforce_admins` is deliberately off: a solo maintainer locked out of his own
  `main` is a worse failure mode than the theoretical bypass. The accurate claim
  is "changes are gated," not "changes cannot be forced." No reviewer approval
  is required either.
- **Verified after tagging (2026-08-11):** the published images were pulled from
  GHCR — neither existed locally beforehand — and the backend started, migrated
  and served `/health` reporting 1.6.0. Register **A9** is MET; see Proof Log
  PL-004. The limit that remains is that the host had previously built the
  project, so this is not a first-run test on a wholly clean machine (**G1**,
  Sprint 5). As originally written, this note read:
  The appliance was verified locally — `/health` reporting 1.6.0, UI and `/docs`
  both 200, backend healthy in ~5s — but a clean-machine pull of the GHCR image
  is a different test and has not been run.

And two concern coverage:

- **LookML has no offline parser**, so its output is structurally asserted only
  and is unverifiable in the harness by construction. This is why it is Preview.
- **No ODCS schema validator is installed.** Conformance is asserted against the
  specification's documented fundamentals (Bitol v3.1.0), not by a validator, so
  the ODCS findings above are spec-reading rather than tool output.

Everything else in this release is asserted by the tool that consumes the
artifact.

---

## Upgrade notes

- **Breaking (configuration):** the appliance refuses to start when
  `MASK_METADATA_IN_PROMPTS=true`. Remove the variable, or set it to `false`. If
  you were relying on it for a compliance control, it was never doing anything —
  see the governance note above and use `AIRGAPPED=true`.
- Container image tags move to `v1.6.0`.
- No database migration. The metadata schema is unchanged at `0012`.

## Corrections to previously published claims

`docs/PROJECT_STATE_REPORT.md` carries a dated corrections section covering
findings this sprint proved wrong, including two of the auditor's own. Notably,
CI **did** exist before this release — the audit checked the wrong directory and
reported it absent. The real gap was coverage, not existence.
