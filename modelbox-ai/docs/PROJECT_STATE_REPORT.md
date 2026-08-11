# ModelBox AI — Project State Report

*Read-only audit. Branch `audit/state-report`. No source file was modified.*
*Date of audit: 2026-08-10. Commit at audit start: `48b83a2`.*

**Bottom line.** The spine is real: a clean layered FastAPI service, a linear
12-step migration chain, a 143-test suite that passes, a genuinely well-built
graph linter, and a Trainer curriculum that is in exact lock-step with that
linter. The problems are concentrated in two places — **the exporters, which
have never been validated by a real consumer toolchain and are broken in ways
no current test can see**, and **the governance story, which is sold in the
README but is a `return prompt` stub with no audit record whatsoever.** There is
also **no CI at all**, despite README and release notes both asserting there is.
*(That last clause is wrong — see Corrections, C1.)*

---

## CORRECTIONS

*Added 2026-08-11 during Sprint 1. The report is the source of truth for finding
IDs cited by the Blueprint, Sprint Plan, Acceptance Criteria register and the
fidelity harness, so errors are corrected in place with a dated note rather than
silently rewritten. Section bodies below are left as originally written; where a
correction applies, it is flagged from here.*

### C1 — §2, §6, §8, §9: **CI existed. Finding B2 as written is wrong.** *(auditor error)*

The report states that `.github/` does not exist and that README, ROADMAP and the
v1.5.0 release notes assert a CI pipeline that does not. **All of that is false.**

`ls .github` was run from `modelbox-ai/`, the project subdirectory. The git
repository root is one level above, at `modelbox/`, where
`.github/workflows/ci.yml` and `.github/workflows/release.yml` are both present
and tracked. `git rev-parse --show-toplevel` would have shown this, and the
`modelbox-ai/…` prefixes already visible in `git status` output were a signal
that was not followed up.

At the time of the audit the CI workflow had run **59 times and was green on
every recent `main` push**. `release.yml` is named "Release Images" and does
exactly what `README.md:112-124` describes.

Consequently these three §2/§8 rows were wrong, and are withdrawn:

| Claim | Report said | Actually |
| :-- | :-- | :-- |
| README:112-124 — GHCR release via `.github/workflows/release.yml` | CLAIMED-BUT-ABSENT | **True** |
| ROADMAP:16 — "CI on every push, GHCR release on tags" | CLAIMED-BUT-ABSENT | **Substantially true** |
| RELEASE_NOTES_v1.5.0:3 — "CI: green" | False claim | **True and verifiable** |

**What was actually true, and survives as the revised B2 (high, not blocker):**
CI gated three of the six jobs the product needs — `pytest`, `tsc --noEmit`,
`next build` — with no fidelity harness, no `next lint`, no alembic-head check
and no version check. It triggered on `main` and PRs into `main` only, so
feature branches were unguarded. And `main` carried **no branch protection**, so
nothing *required* a green run to merge.

The sprint's premise is unaffected and arguably sharpened: every exporter defect
in §4 reached `main` *through* a green CI run, because the suite CI ran asserted
exporter output by substring.

**Closed in v1.6.0:** six required checks, triggers widened to all branches,
branch protection enabled.

### C2 — §4.2: **the dbt exporter does not produce a self-contained project.** *(auditor error)*

§4.2 reports dbt output as parsing on 5/5 gold graphs "with two real defects."
It does not parse at all. `generate_dbt_project` emits staging models
referencing `{{ source('raw', …) }}` (`exporter_service.py:160`) but never emits
a sources declaration, so `dbt parse` fails:

```
Compilation Error
  Model 'model.pure.stg_dim_customer' depends on a source named
  'raw.dim_customer' which was not found
```

The audit's dbt projects parsed only because the audit harness supplied a
`_sources.yml` written by the auditor. §4.2 therefore verified the auditor's
scaffolding, not the product — the same class of error the harness in
`test_artifact_fidelity.py` exists to prevent.

Recorded as **H9** (high) / register **B14**, Sprint 3, paired with M7 under
"the emitted dbt project is self-contained." Asserted by
`test_dbt_project_is_self_contained` (5 xfails).

### C3 — §4.6 and DISAGREEMENT (e): **H2 was under-called.**

The report describes ODCS output as "v3-shaped with a v0.9.3 stamp." Confirmed
against the specification (Bitol, via context7, 2026-08-10): the current line is
**v3.1.0**, and the emitted contract is a **hybrid of two standards missing two
required fields**, not merely mis-stamped:

- ODCS v3 requires top-level `version` and `status`; neither is emitted.
- The emitted `info:` block belongs to the Data Contract Specification
  (datacontract.com), a different standard.

Split out as **H2-ext** / register **B7**, asserted by
`test_odcs_conforms_to_v3_fundamentals`.

### C4 — §5 and B3: the README never carried a masking claim.

§5 and finding B3 are correct that masking was a no-op and that the flag was
advertised in `config/model_router.yaml:20-21` and `.env.example`. But
`README.md` contains no reference to masking at all — `README.md:106` is the
AIRGAPPED zero-egress statement, which is accurate. Sprint 1's spec inherited the
mis-citation. The claim was removed from the four surfaces that did carry it.

**Closed in v1.6.0:** the flag now fails startup; `_maybe_mask` is deleted.

### C5 — §6: the suite was 143 tests, not 129.

Noted in §6 as written; restated here because the figure appears in planning
documents. As of v1.6.0 the backend suite is **246 passed, 30 skipped, 80
xfailed** in the app venv.

### C6 — §4.5: LookML is Preview, not a repair target.

§4.5 records LookML as UNVERIFIED-by-toolchain and lists its defects under M3.
Ruled 2026-08-11: LookML drops to **Preview** alongside the three preview
dialects — proprietary, no offline parser so permanently unverifiable here, and
the install base does not justify the effort. M3 narrows to Cube only. The
LookML assertions carry `@pytest.mark.preview` and are excluded from the Sprint 3
burn-down.

### C7 — §4.6: a fidelity test that could not distinguish two different rules

*Added 2026-08-11 during Sprint 2.*

`test_odcs_required_reflects_nullability` asserted that ODCS `required` derives
from `ColumnSchema.is_nullable` rather than restating `is_primary_key`. It
failed only because the field did not exist.

Sprint 2 adds `is_nullable` defaulting to `True` with primary keys forced
`False`. Under that rule `not is_nullable` and `is_primary_key` are **equal on
every column of all five gold graphs** — verified, zero mismatches. The test
would therefore have gone green the moment the field landed, against an emitter
that still never read it: passing for the wrong reason, and silently closing a
Sprint 3 finding that was not fixed.

The gold graphs contain no counterexample because a correct model rarely has a
non-key column that is also non-nullable by declaration. The test now asserts
against a mutated copy in which one non-key column per entity is forced
non-nullable, which separates the two rules. Case count is unchanged at 5 and
the finding remains xfail until Sprint 3 changes the emitter.

Generalised as stop condition 4 in the Acceptance Criteria register: a criterion
met by a test that cannot distinguish the correct implementation from the
current one is NOT MET.

### C7-a — the ODCS foreign-key construct was named wrongly in C3

*Added 2026-08-11 during Sprint 3.*

Correction C3 stated that ODCS v3.1.0 has "native property-level `foreignKey`",
and Sprint 2's M6 ruling ("wire it, don't delete it") rested on that. **The
ruling holds — `ColumnSchema.references` does have a real downstream consumer —
but the construct was named wrongly.**

Verified against Bitol's `references.md` via context7:

* **Property level** uses `relationships`, with `from` implicit:
  `relationships: [{to: <object>.<property>}]`.
* `type: foreignKey` is the **schema-level** construct, and there both `from`
  and `to` are required.

The shorthand notation `<object>.<property>` happens to be exactly the shape
`ColumnSchema.references` already stores, so it maps across with no
transformation. That is a lucky outcome rather than a designed one — the field
predates the ruling and was never shaped against this spec.

Also recorded, because Sprint 3's task list had it incomplete: the **required
top-level set is `apiVersion`, `kind`, `id`, `version`, `status`**. `name` is
optional and `dataProduct` is deprecated since v3.1.0. The task list named only
`version` and `status`.

### H10 — ODCS quality blocks are not valid v3.1.0

*Added 2026-08-11 during Sprint 3, found while verifying C7-a.*

`_odcs_quality` (`exporter_service.py:969-982`) emits
`{"rule": "range", "mustBeGreaterThanOrEqualTo": …}` and
`{"rule": "regex", "pattern": …}`. **`rule` is not an ODCS key.** A v3.1.0
property-level quality entry is `{id, metric, mustBe*, arguments, unit,
description}` with an optional `type` of `library`, `sql` or `custom`.

No gold graph declares a quality rule, so this is reachable only through the
synthetic `quality-rules` fixture — which is why the audit's ODCS work never
surfaced it.

Severity high, not blocker: the surrounding contract is valid and a consumer
ignoring an unrecognised block still gets a usable document. **Assigned to
Sprint 4**, entered into the inventory now as an xfail so it is a test rather
than a paragraph.

### Scope of the ODCS re-read (Sprint 3)

The v3.1.0 conformance work read the specification **for the constructs this
emitter produces** — fundamentals, schema objects, properties, relationships,
quality. It was not an audit of the whole standard.

Within that scope, one further gap was found beyond H10 (`id` missing from the
required top-level set) and fixed. Anything outside it is unexamined rather
than confirmed clean, and the distinction should survive: a scoped check and an
audit look identical in a changelog.

### Findings closed since the audit

| Finding | Status |
| :-- | :-- |
| B2 | **Revised** (C1) and closed in v1.6.0 — six required checks, `main` protected |
| B3 | Masking half closed in v1.6.0 (retired, fails startup, logging configured); egress ledger remains open for Sprint 5 |
| H8 | Closed in v1.6.0 — `requirements.lock`, Linux-generated, reproduces byte-identically |
| M5 | Closed in v1.6.0 — single canonical version, enforced in CI |
| M9 | Partially closed — ESLint config added and `next lint` is a blocking CI job; the canvas smoke test remains Sprint 6 |
| M10 | Closed in v1.6.0 — see the section below and `docs/research/` |
| H9, M11 | **New**, found by the fidelity harness; scheduled for Sprint 3 |

---

## 1. ARCHITECTURE MAP

### Layers

| Layer | Location | Notes |
| :-- | :-- | :-- |
| HTTP | `backend/app/api/v1/endpoints/` (7 modules), mounted via `backend/app/api/v1/router.py:1` | Handlers are thin; logic lives in services. |
| DI / authz | `backend/app/api/v1/dependencies.py:37-261` | Session, gateway, service factories, JWT/API-key auth, workspace RBAC. |
| Services | `backend/app/services/` (10 modules) | Pure where possible; `exporter_service`, `graph_engine`, `diff_engine`, `seed_generator` have no DB/LLM deps. |
| Schemas (IR) | `backend/app/schemas/data_model.py:1-728` | Single Pydantic file serving API contract, LLM structured output, and ORM projection. |
| ORM | `backend/app/models/metadata_store.py:1-526` | 13 tables, SQLAlchemy 2.0 async. |
| Async work | `backend/app/worker.py:1-64`, `backend/app/services/job_service.py`, `backend/app/api/v1/endpoints/jobs.py` | Celery, per-task engine. |
| Frontend | `frontend/src/` — Next.js 14 App Router, Zustand, `@xyflow/react` | 5 routes, no tests. |

### Data flow, input to emitted artifact

```
NL / PRD / DDL text
  └─ POST /api/v1/model/synthesize            endpoints/models.py:70
       └─ SynthesisEngine.synthesize          synthesis_engine.py:73
            ├─ LLMGateway.structured_completion  llm_gateway.py:160   ← the only egress point
            │    └─ resolve_route → LiteLLM+Instructor → SynthesizedModel
            ├─ _normalize_relationships       synthesis_engine.py:324  (deterministic N:1 fixup)
            ├─ GraphEngine.validate           graph_engine.py:125      (12 lint codes)
            └─ _persist_graph                 synthesis_engine.py:254
                    → data_models / model_entities / entity_columns / entity_relationships

Canvas edit
  └─ PUT /api/v1/model/{id}/graph             endpoints/models.py:246
       └─ GraphRepository.replace_graph       graph_repository.py:30   (delete-all + reinsert)

Any export
  └─ GET /model/{id}/export[/contract|/semantic|/dictionary|/zip]
       └─ SynthesisEngine.get_model           synthesis_engine.py:118  (ORM → EntitySchema)
            └─ _to_synthesized                endpoints/models.py:54
                 └─ ExporterService.*         exporter_service.py:74-583
```

### Where the real seams are

1. **`SynthesizedModel` is the universal currency.** Everything — LLM output,
   canvas state, ORM projection, every exporter input, the diff engine, the
   seed generator, the grader — is this one shape (`data_model.py:534`). This is
   the project's best architectural decision and the reason new exporters are
   cheap. It is also the choke point for §3's gaps.
2. **`LLMGateway.structured_completion` is the single egress choke point**
   (`llm_gateway.py:160`). Nothing else in `backend/app` makes an outbound model
   call. Verified by grep: `synthesis_engine.py:76`, `paradigm_translator.py:82`,
   and `trainer_service.py:101` are the only three call sites.
3. **`ExporterService` is stateless and DB-free** (`exporter_service.py:61`).
   Every exporter is a pure function of the IR. Testing it needs no fixtures —
   which makes the absence of real-toolchain tests (§6) inexcusable rather than
   difficult.
4. **`GraphEngine` is reused three ways** — synthesis validation, the
   `/model/validate-graph` endpoint that Trainer labs grade against, and the
   seed generator's topological ordering (`seed_generator.py:108`). Good reuse.
5. **The seam that leaks: ORM ↔ IR.** `graph_repository.py:85-102` and
   `synthesis_engine.py:371-386` are two independently maintained
   column-mapping lists. They currently agree, but nothing enforces that, and
   both silently drop fields the IR declares (§3).

---

## 2. TRUTH AUDIT

### README.md

| Claim | Verdict | Evidence |
| :-- | :-- | :-- |
| Multi-dialect DDL (Snowflake/Databricks/BigQuery/Postgres) | **PARTIAL** | 7 dialects transpile and re-parse (`exporter_service.py:93`), but output is not accepted by BigQuery/Databricks/ClickHouse as written — see §4. |
| Visual ERD canvas | **SHIPPED** | `frontend/src/components/canvas/ERDCanvas.tsx`; `next build` succeeds (`frontend/build.log`). |
| Multi-paradigm transformation | **SHIPPED** (but LLM-mediated) | `paradigm_translator.py:66`. See DISAGREEMENTS (a). |
| "zero-data-egress options for regulated industries" | **PARTIAL** | `AIRGAPPED=true` correctly strips all non-local providers and cannot be escaped via `llm_override` (verified, §5). But there is no per-task residency control in normal mode and no record that anything left. |
| README §"Governance & air-gap": routing "keyed off the explicit `egress:` classification … so the policy is deterministic" | **SHIPPED** | `llm_gateway.py:122-132`, `config/model_router.yaml:35-84`. Verified empirically, §5. |
| README §Releases: "publishes versioned images to GHCR via the `Release Images` workflow (`.github/workflows/release.yml`)" | **CLAIMED-BUT-ABSENT** | `.github/` does not exist. `ls .github` → `No such file or directory`. |
| README §Releases: "CI gates every push" | **CLAIMED-BUT-ABSENT** | No workflow files anywhere in the repo. |
| Docker appliance single-node | **SHIPPED** | `docker/docker-compose.appliance.yml:1-169`. |

### docs/PRD_TRD_v2.md

| Requirement | Verdict | Evidence |
| :-- | :-- | :-- |
| FR-1.1 Async job execution | **SHIPPED** | `worker.py:43`, `endpoints/jobs.py`, migration `0005`, compose `modelbox-worker` service (`docker-compose.appliance.yml:78`). |
| FR-1.2 Canvas persistence | **SHIPPED** | `endpoints/models.py:246` → `graph_repository.py:30`. Positions, columns, cardinality all persist. |
| FR-2.1 Introspection: "PostgreSQL / Snowflake / BigQuery / **DuckDB**" | **PARTIAL** | Postgres, Snowflake, BigQuery, **MySQL** implemented (`introspection.py:234,349,456,553`). **DuckDB is not.** A DuckDB connection is registerable — `DUCKDB` is in `CONNECTION_ENGINES` (`metadata_store.py:45`) and passes the create check (`connectors.py:61`) — but introspection returns 501 (`connectors.py:164`). MySQL is shipped but not in the PRD list. |
| FR-2.2 Schema diff → ALTER | **PARTIAL** | `diff_engine.py:33` emits column add/drop/type-change and CREATE/DROP TABLE. **Relationship/FK changes are not diffed at all** — verified: removing all 3 FKs from `healthcare-ehr` produces 0 statements, 0 breaking changes (§4). PK changes and governance/quality-rule changes are likewise invisible. |
| FR-2.3 Contract & semantic exporters (ODCS, Avro, Protobuf, LookML, MetricFlow) | **PARTIAL** | All five emit. Avro and Protobuf pass their real parsers. ODCS is mis-stamped. **MetricFlow fails `dbt parse` on all five gold graphs.** See §4. |
| FR-2.4 seed "honoring `topological_order()` … **+ column constraints**" | **PARTIAL** | Topological ordering is correct and verified. **Column constraints are ignored**: seed values violate declared `min_value`/`max_value`/`regex_pattern` and overflow declared `VARCHAR(n)` (§4). |
| FR-2.5 RealityDB / SafeSQL seams | **CLAIMED-BUT-ABSENT** | Zero references in `backend/app`. Grep for `realitydb|safesql` returns nothing. |
| FR-3.1 Socratic tutor | **SHIPPED** | `trainer_service.py:79`, dedicated prompt at `trainer_service.py:30`, isolated task route `socratic_tutoring` (`model_router.yaml:118`). |
| FR-3.2 Spot-the-Flaw | **SHIPPED** | 5 labs in `frontend/src/content/trainer/`, graded by the shipped linter via `/model/validate-graph` (`frontend/src/app/trainer/page.tsx:67`). |
| FR-3.3 Auto-graded rubrics: "graph invariants **+ requirements coverage**" | **PARTIAL** | Graph invariants: 3 of them (`trainer_service.py:41-45`). **Requirements coverage: absent.** |
| NFR: creds encrypted at rest via "KMS/`hvac` provider" | **PARTIAL** | AES-256-GCM is real (`core/crypto.py:26-40`). **No KMS, no `hvac`** — `hvac` is not in `requirements.txt`; the key is a plain env var (`config.py:97`). |
| TRD §5 "Security notes (carry v1 + **audit**)" | **CLAIMED-BUT-ABSENT** | No audit table, no audit module, no audit call site. Grep for `audit` across `backend/app` returns zero hits. |

### docs/ROADMAP.md

The `## 0. What exists today` table and the `**Honest gaps**` paragraph
(`ROADMAP.md:9-19`) are **stale in both directions** and should not be used for
sequencing:

- **Understates:** the "NOT built yet" list names reverse-engineering, saving
  canvas edits, async synthesis, schema diff, LookML/MetricFlow, and data
  contracts. All six now exist (`introspection.py`, `graph_repository.py`,
  `worker.py`, `diff_engine.py`, `exporter_service.py:442,438,318`).
- **Overstates:** `ROADMAP.md:16` claims "CI on every push, GHCR release on
  tags" as *shipped infra*. Neither exists.
- **Wrong fact:** `ROADMAP.md:83` says "`hvac` already in deps". It is not in
  `requirements.txt`.
- Still-true gaps from that list: **audit trail** and **SSO/OIDC hardening**
  (RS256 verifies, but `aud`/`iss` are unchecked — `core/security.py:94`).

---

## 3. IR AUDIT — `backend/app/schemas/data_model.py`

### `ColumnSchema` (`data_model.py:420-465`)

| Field | Line | Downstream consumers | ORM round-trip |
| :-- | :-- | :-- | :-- |
| `name` | 425 | every exporter, linter, seed, diff | persisted (`entity_columns.column_name`) |
| `data_type` | 426 | DDL, dbt casts, Avro/proto/LookML/Cube/ODCS type maps, seed, diff | persisted |
| `is_primary_key` | 427 | DDL `PRIMARY KEY`, dbt unique+not_null, Cube `primaryKey`, LookML `primary_key`, MetricFlow primary entity, Avro non-null, ODCS `required`+`primaryKey`, `MISSING_PK` lint | persisted |
| `is_foreign_key` | 428 | dictionary key label only (`exporter_service.py:597`) | persisted |
| `is_pii` / `pii_type` | 429-430 | ODCS `classification: PII`, dictionary PII column, `PII_EXPOSURE` lint | persisted |
| `description` | 431 | dbt/ODCS/Avro `doc`, dictionary glossary, `MISSING_DESCRIPTION` lint | persisted |
| `ordinal_position` | 432 | ORM ordering only | persisted; **not used by the Protobuf emitter** (verified §4) |
| **`references`** | **436** | **nothing — zero consumers** | **DROPPED. No ORM column exists.** |
| `is_metric` / `aggregation` | 439-440 | Cube/LookML/MetricFlow measures, diff `semantic_breaks` | persisted |
| `min_value` / `max_value` | 444-448 | dbt `expect_column_values_to_be_between`, ODCS range rule, `INVALID_RANGE` lint | persisted (migration `0012`) |
| `regex_pattern` | 450 | dbt regex test, ODCS regex rule, `INVALID_REGEX` lint | persisted |

**`references` is dead weight.** Declared at `data_model.py:436` with a
docstring promising it is "preserved across paradigm switches", exposed in the
frontend `Column` type (`frontend/src/types/schema.ts`) and the template builder
options (`frontend/src/lib/templates.ts:38`) — and read by nothing. A grep for
`.references` / `references=` across `backend/app` and `frontend/src` returns
zero hits. It is silently discarded by both persistence paths
(`graph_repository.py:85`, `synthesis_engine.py:278`).

### `EntitySchema` (`data_model.py:468-496`)

All seven fields persist: `entity_name`, `entity_type`, `description`, `grain`,
`tier`, `freshness_sla`, `canvas_position_x/y` (`metadata_store.py:217-230`).
`tier` and `freshness_sla` reach ODCS (`exporter_service.py:365-371`) and the dbt
`meta` block (`exporter_service.py:926`); `grain` reaches the dictionary and the
`MISSING_GRAIN` lint. **No IR gap here.** This part is in good shape.

### `RelationshipSchema` (`data_model.py:499-518`)

Three fields: `from_ref`, `to_ref`, `cardinality`. Persisted as
`(from_entity_id, from_column_id, to_entity_id, to_column_id, cardinality)`
(`metadata_store.py:291-320`).

**Lossy on read-back.** `synthesis_engine.py:168-175` reconstructs `from_ref`
from `column_ref[from_column_id]`, falling back to the bare entity name when
`from_column_id` is NULL. `from_column_id` is NULL whenever the column lookup
missed at write time (`graph_repository.py:116`). So a relationship whose ref
named a non-existent column degrades from `orders.cust_id` to `orders` on the
next read — and every downstream FK emitter (`_entity_create_table:128`,
`_dbt_schema_yml:184`, `_metricflow:485`) skips refs with no column part. The
edge survives in the ERD but vanishes from every artifact, silently.

### Dropped at the model level

**`suggested_metrics` never survives a round-trip.** `SynthesizedModel` carries
it (`data_model.py:546`) and synthesis returns it, but it is never persisted —
there is no table — and `get_model` hard-codes `suggested_metrics=[]`
(`synthesis_engine.py:188`). Consequence: `DiffEngine._semantic_breaks` builds
its `formulas` list from `source.suggested_metrics` (`diff_engine.py:102`), so
the entire formula-reference branch (`diff_engine.py:117-122, 141-146`) is
**unreachable through the API** — `POST /model/diff` always feeds it an empty
list (`endpoints/models.py:161-167` → `_to_synthesized:54`). Only the
`is_metric`-based branch can ever fire.

### Physical / semantic / governance attributes with no home in the IR

| Missing | Impact |
| :-- | :-- |
| **`is_nullable`** | DDL emits no `NOT NULL`, ever (verified: 0 `NOT NULL` across all 35 emitted DDL files, §4). ODCS falls back to `required: is_primary_key`. Avro guesses `["null", T]` for every non-PK. Databricks and BigQuery reject PKs on nullable columns. |
| **`is_unique`** | No `UNIQUE` constraint, no dbt `unique` test except on PKs. |
| **`default_value`** | No `DEFAULT` in DDL or diff; a default change is an invisible migration. |
| **`check_constraint`** | `min_value`/`max_value`/`regex_pattern` exist but emit only to *test frameworks*, never to DDL `CHECK`. The database itself is unconstrained. |
| **`is_surrogate_key` / `is_business_key`** | Data Vault hub/link semantics are inferred from name prefixes in the linter (`graph_engine.py:31-37`) rather than declared. |
| **SCD type / validity window** | The `saas-subscription` gold graph *is* SCD2 (`valid_from`/`valid_to`/`is_current`) but the IR cannot say so, so no exporter emits MetricFlow `validity_params` or a LookML `dimension_group` pairing. |
| **`owner` / `steward` / `classification` beyond PII** | ODCS hard-codes `owner: modelbox` (`exporter_service.py:381`). |
| **Column-level `tier`/SLA** | Governance is entity-granular only. |
| **Time-grain declaration** | The single root cause of the MetricFlow `agg_time_dimension` failure (§4): nothing in the IR marks *which* temporal column a fact aggregates over. |

---

## 4. EXPORTER FIDELITY

Every check below ran against the five Requirements Library gold graphs
transcribed verbatim from `frontend/src/lib/templates.ts:97-339`:
`saas-subscription`, `ecommerce-orders`, `banking-datavault`, `healthcare-ehr`,
`marketing-attribution`. 150 artifact files were emitted and then handed to the
real toolchain for each format. Venv used is noted per check.

### Summary

| Emitter | Toolchain | Result |
| :-- | :-- | :-- |
| DDL × 7 dialects | `sqlglot.parse` per dialect (`.venv`) | **35/35 re-parse clean.** But 3 dialects would be rejected by the actual engine. |
| dbt | `dbt parse` 1.11.12 (`.venv-tools`) | **5/5 parse.** Deprecation warnings; undeclared package dependency. |
| MetricFlow | `dbt parse` + `SemanticManifestValidator` (`.venv-tools`) | **0/5 parse. Four independent blockers.** |
| Cube.js | `node --check` v22.18.0 | **15/15 valid JS.** Semantically wrong measures. |
| LookML | *no offline parser available* | **UNVERIFIED** by toolchain; structural review below. |
| ODCS | *no offline validator available* | **UNVERIFIED** by validator; version stamp and `required` semantics are wrong by inspection. |
| Avro | `fastavro.parse_schema` 1.12.2 (`.venv-tools`) | **15/15 parse clean.** |
| Protobuf | `protoc` libprotoc 26.1 | **5/5 compile clean.** Wire-compat and type fidelity problems. |
| Dictionary | `yaml.safe_load` / JSON / manual | **Clean.** Weakest-value artifact but correct. |
| Seed | conformance checks vs the model's own contract | **Violates the contract the same model exports.** |

---

### 4.1 DDL — parses everywhere, deployable in four of seven

`.venv` · sqlglot 30.16.0. All 35 files (`5 graphs × 7 dialects`) re-parse in
their own dialect with zero opaque `Command` fallbacks.

Deployable as-is: **postgres, snowflake, redshift, duckdb**.

Would be rejected by the real engine:

- **BigQuery** (`ecommerce-orders/ddl/bigquery.sql`): emits
  `PRIMARY KEY (customer_sk)` and `FOREIGN KEY (customer_sk) REFERENCES
  dim_customer (customer_sk)`. BigQuery requires the `NOT ENFORCED` suffix on
  both. Root cause: `_entity_create_table` (`exporter_service.py:113-135`)
  builds one ANSI string and lets sqlglot transpile it — sqlglot preserves
  constraint syntax but does not add dialect-mandatory modifiers.
- **Databricks** (`ecommerce-orders/ddl/databricks.sql`): primary-key columns
  must be `NOT NULL`. Nothing in the IR can express nullability (§3), so
  `customer_sk INT, … PRIMARY KEY (customer_sk)` is invalid Unity Catalog DDL.
- **ClickHouse** (`ecommerce-orders/ddl/clickhouse.sql`): no `ENGINE =` clause
  (mandatory), and every column including the PK is emitted as
  `Nullable(Int32)` — ClickHouse forbids `Nullable` in a primary key.

**No `NOT NULL` is emitted anywhere.** Verified across all 35 files: zero
occurrences. Confirms DISAGREEMENT (b).

**Emission order is declaration order, not topological.** `generate_ddl`
(`exporter_service.py:101-104`) iterates `model.entities` as given.
`GraphEngine.topological_order` exists and its docstring claims it is used for
"deterministic DDL emission order" (`graph_engine.py:107-114`) — the exporter
never calls it. Demonstrated with `healthcare-ehr` entities reversed:

```
emitted order: ['diagnosis', 'encounter', 'provider', 'patient']
```

`diagnosis` declares `FOREIGN KEY (encounter_id) REFERENCES encounter` before
`encounter` exists — `psql` aborts on statement 1. The five templates happen to
be declared parent-first, which is why this has never surfaced. Any LLM-emitted
or canvas-reordered model can hit it.

### 4.2 dbt — parses, with two real defects

`.venv-tools` · dbt-core 1.11.12, dbt-postgres 1.11.0. All five projects
`dbt parse` successfully (staging models + `schema.yml` + sources).

- **Deprecated test syntax on 4/5 graphs.** dbt 1.11 emits
  `MissingArgumentsPropertyInGenericTestDeprecation` for every `relationships`
  and `accepted_values` test — `banking-datavault` 4 occurrences,
  `healthcare-ehr` 3, `saas-subscription` 3, `ecommerce-orders` 2. Generated at
  `exporter_service.py:201-211`; arguments must nest under `arguments:`.
- **Undeclared package dependency.** `_dbt_quality_tests`
  (`exporter_service.py:942-967`) emits
  `dbt_expectations.expect_column_values_to_be_between` and
  `…_to_match_regex`, but `generate_dbt_project` (`exporter_service.py:140-151`)
  never emits a `packages.yml`. Any model carrying a quality rule produces a
  project that cannot resolve its own tests. (Not triggered by the five gold
  graphs — none declares quality rules — which is exactly why it shipped.)

### 4.3 MetricFlow — **0/5 parse. Four independent blockers.**

`.venv-tools` · dbt-core 1.11.12, dbt-semantic-interfaces 0.9.0,
metricflow 0.211.0. Each blocker was found by fixing the previous one and
re-running, so all four are real and independent.

**Blocker 1 — `label` is required on every metric.** All 5 graphs.
```
Invalid metrics config … @ metrics: {'name': 'hub_customer_count', 'type': 'simple',
  'type_params': {'measure': 'hub_customer_count'}} - at path []: 'label' is a required property
```
`_metricflow` emits metrics at `exporter_service.py:531-548` with no `label`.

**Blocker 2 — the semantic layer points at models the dbt exporter never
creates.** 4/5 graphs (all except `saas-subscription`, which dies on blocker 3
first).
```
Semantic_Model 'semantic_model.healthcare_ehr.patient' depends on a node named
'patient' which was not found
```
`exporter_service.py:552` emits `model: ref('{entity.entity_name}')`, but
`generate_dbt_project` names its models `stg_{entity_name}`
(`exporter_service.py:147`). The two exporters disagree about their own naming
convention.

**Blocker 3 — `avg` is not a MetricFlow aggregation.** `saas-subscription`
(`dim_plan.list_price` carries `aggregation: 'avg'`).
```
Invalid enum value: `avg` in enum AggregationType
```
This one is an **unhandled crash**, not a parse error — dbt exits with a Python
traceback. `exporter_service.py:520` passes `col.aggregation` through
lower-cased with no mapping to MetricFlow's vocabulary (`average`).

**Blocker 4 — `defaults.agg_time_dimension` is never emitted.** All 5 graphs.
Confirmed twice: no `defaults` key appears in any emitted semantic model, and
the validator reports one error per measure:
```
banking-datavault      5 errors  (hub_customer_count, hub_account_count,
                                  lnk_transaction_count, total_balance,
                                  + sat_account_details has no primary entity)
ecommerce-orders       3 errors
healthcare-ehr         4 errors
marketing-attribution  1 error
saas-subscription      4 errors
```
Message: `Aggregation time dimension for measure X is not set!`

Two further defects surfaced at this layer:

- **`banking-datavault`:** `sat_account_details` has no primary-key column, so
  `entities_block` is empty and the validator rejects it —
  *"contains dimensions, but it does not define a primary entity."* Satellites
  legitimately have no single-column PK; the emitter has no story for them.
- **`saas-subscription`:** the `month` dimension collides with a reserved word —
  *"names cannot match reserved time granularity keywords."* No name guard
  exists at `exporter_service.py:506`.

**Foreign-entity naming** (DISAGREEMENT (c), second half): `exporter_service.py:502`
names foreign entities after the *local FK column*. In all five gold graphs the
FK column name happens to equal the parent's PK column name, so the joins line
up by luck. Probed with a divergent name:

```
dim_customer     entities=[('customer_sk', 'primary')]
fact_order_line  entities=[('ship_to_customer_sk', 'foreign'), ('product_sk', 'foreign')]
```
MetricFlow joins entities by name. `ship_to_customer_sk` has no counterpart on
`dim_customer`, so the join **silently does not exist** — no error, just a
semantic layer that cannot answer the question. Role-playing dimensions
(`ship_to_` / `bill_to_`), which are the normal Kimball case, break this.

### 4.4 Cube.js — valid JS, wrong measures

`node --check` v22.18.0: all 15 files parse. Semantically:

- **Sums over keys.** `saas-subscription/semantic_cube/schema/FactSubscriptionMonthly.js`
  emits `totalSubscriptionMonthSk`, `totalCustomerSk`, `totalPlanSk` — `SUM()`
  over a primary key and two foreign keys. `_cube_file`
  (`exporter_service.py:284-291`) gates on `col.is_metric or self._is_numeric(col)`
  with no key exclusion. LookML's equivalent loop *does* exclude the PK
  (`exporter_service.py:465`) but not FKs — so the two emitters disagree, and
  both are wrong.
- **Booleans become strings.** `isChurned: type: 'string'` for a `BOOLEAN`
  column. `_cube_type` (`exporter_service.py:999-1005`) has no boolean branch,
  though `_logical_type` and `_lookml_type` both do.
- **Mixed API generation.** `sql_table` (Cube v2 snake_case) sits alongside
  `primaryKey` and `relationship: 'belongsTo'` (both legacy camelCase,
  deprecated in favour of `primary_key` and `many_to_one`).

### 4.5 LookML — **UNVERIFIED** (no offline parser installed)

No LookML parser is available in this environment, so no toolchain verdict.
Structural review of `saas-subscription/semantic_lookml/fact_subscription_monthly.view.lkml`:
syntax is well-formed; `dimension_group` for temporals, `primary_key: yes`,
`type: yesno` for booleans are all correct. Same FK-sum defect as Cube
(`total_customer_sk`, `total_plan_sk`). No `explore` is emitted for any graph,
so the relationships in the IR produce no joins at all in LookML — the views are
islands. No PII handling despite the IR carrying it: `patient.view.lkml` exposes
`ssn` as a plain dimension with no `required_access_grants` or field-level
restriction.

### 4.6 ODCS — v3 body, v0.9.3 stamp; `required` is wrong

`yaml.safe_load` clean on all 5. No ODCS schema validator is installed, so
**schema conformance is UNVERIFIED**. Two defects are determinable by
inspection:

- **Version stamp.** `exporter_service.py:375` writes `apiVersion: v0.9.3`
  while the body uses ODCS **v3** vocabulary throughout: top-level `schema:`
  (v0.9.x used `dataset:`), `properties:` (v0.9.x used `columns:`),
  `logicalType`/`physicalType`, `slaProperties`, per-property `quality`. Confirms
  DISAGREEMENT (e).
- **`required: col.is_primary_key`** (`exporter_service.py:347`). From
  `banking-datavault/odcs/datacontract.yaml`: `load_dts` and `record_source` —
  structurally mandatory in every Data Vault load — emit `required: false`.
  Every non-PK column in every graph is declared optional. The contract asserts
  the opposite of the truth for most columns.
- Also: `info.owner` is hard-coded `modelbox` (`exporter_service.py:381`) and
  `info.version` is hard-coded `1.0.0` (`exporter_service.py:380`) — the model's
  real `version_number` (`metadata_store.py:174`) is not used, so a contract
  never advances a version.

### 4.7 Avro — clean

`fastavro.parse_schema` 1.12.2: **15/15 parse**. Decimal logical types carry
precision/scale from the declared type (`exporter_service.py:843-850`);
timestamps map to `timestamp-micros`; namespaces are sanitized
(`_safe_identifier:889`). This exporter is in good shape. The only semantic
issue is the nullability guess (`["null", T]` for every non-PK,
`exporter_service.py:393-398`) — a defensible default given the IR gap, but it
means Avro and Protobuf describe the *same model* with contradictory
nullability.

### 4.8 Protobuf — compiles; wire-unstable and type-lossy

`protoc` libprotoc 26.1: **5/5 compile clean** with `--descriptor_set_out`.

- **Ordinal tags break wire compatibility.** Verified on `saas-subscription` by
  inserting one column at position 1 of `dim_customer`:
  ```
  customer_sk  1 -> 1
  customer_id  2 -> 3   TAG CHANGED
  email        3 -> 4   TAG CHANGED
  tier         4 -> 5   TAG CHANGED
  valid_from   5 -> 6   TAG CHANGED
  valid_to     6 -> 7   TAG CHANGED
  is_current   7 -> 8   TAG CHANGED
  ```
  Confirms DISAGREEMENT (d). Additionally verified that `ordinal_position` is
  *not* the driver — reversing every `ordinal_position` left the tags unchanged,
  because `exporter_service.py:421` enumerates the Python list directly.
- **Type loss.** `NUMERIC(18,2)` → `double` (`exporter_service.py:864`). For
  `banking-datavault`'s `sat_account_details.balance` — a ledger balance — that
  is a floating-point money field in a contract sold as governance-grade. Avro
  gets this right (`decimal` with precision/scale); Protobuf does not.
- **Temporals become strings.** `valid_from DATE` → `string`,
  `event_ts TIMESTAMP` → `string`. No `google.protobuf.Timestamp`, no
  `int64` epoch.
- **No field presence.** proto3 without `optional` means no consumer can
  distinguish "null" from `0`/`""`, contradicting the Avro contract emitted from
  the same model.
- **Filename is not sanitized.** The package name goes through
  `_safe_identifier` (`exporter_service.py:417`) but the file key does not
  (`exporter_service.py:334`): `{dataset_name}.proto`, where `dataset_name` is
  `model.title` (`endpoints/models.py:357`). A model titled `Untitled Model`
  yields `Untitled Model.proto`.

### 4.9 Dictionary — correct

Markdown, HTML, and JSON all emit cleanly for all five graphs. Pipe-escaping
(`_md_cell:608`) and HTML escaping (`esc:686`) are handled. Glossary only
includes documented terms, deliberately (`exporter_service.py:663`). No defects
found. It is the least valuable artifact and the most correct one.

### 4.10 Seed — FK-safe, but violates the contract the same model exports

- **Ordering is correct.** `healthcare-ehr` generates
  `patient, provider, encounter, diagnosis` and every FK value is drawn from the
  parent's pool (`seed_generator.py:82-85`). This part works.
- **Length overflow.** `healthcare-ehr` `diagnosis.icd10_code` is
  `VARCHAR(10)`; the generator emits `'icd10_code_1'` — 12 characters
  (`seed_generator.py:178`). Inserting the emitted seed into the emitted DDL
  fails. The generator never reads the declared length.
- **Quality rules ignored entirely.** For a column declaring
  `min_value: 0.0, max_value: 5.0` and `regex_pattern: ^[A-Z]{3}-\d{4}$`, the
  generator produced:
  ```
  order_id,score,ref_code
  1,6301.38,ref_code_1
  2,2733.24,ref_code_2
  ```
  while `generate_dbt_project` on the *same model* emitted
  `expect_column_values_to_be_between: {min_value: 0.0, max_value: 5.0}` and
  `expect_column_values_to_match_regex: {regex: ^[A-Z]{3}-\d{4}$}`. Ship both
  artifacts and `dbt build` fails on your own seed data. `_value`
  (`seed_generator.py:134-178`) never consults `col.min_value`, `col.max_value`,
  or `col.regex_pattern`.

### 4.11 Diff — column-only

`healthcare-ehr` with all 3 relationships removed:
`0 statements, 0 breaking changes, 0 semantic breaks`. FK/PK/governance changes
are invisible (`diff_engine.py:33-90`). `ALTER COLUMN … TYPE` re-parses in
sqlglot for all 6 supported dialects, but sqlglot is lenient — Databricks Delta
does not support arbitrary column type changes, so `ALTER TABLE t ALTER COLUMN c
TYPE BIGINT` is emitted for a platform that will reject it. `_transpile`
(`diff_engine.py:165-170`) also reads with sqlglot's *default* dialect rather
than the source dialect, and swallows every exception into a silent raw-SQL
passthrough.

---

## 5. LLM GATEWAY & EGRESS

**No LLM or provider calls were made during this audit.** No API keys are set;
none were added. All findings below come from `resolve_route`, which is pure.

### Routing

`llm_gateway.py:97-128`. Precedence: `llm_override` → air-gapped overrides →
`task_routing`. Resolved chains, normal mode, with each hop's declared egress
class:

```
unstructured_doc_parsing    anthropic_cloud[cloud] -> openai_cloud[cloud] -> kimi_cloud[cloud_apac] -> airgapped_vllm[local]
schema_reasoning_and_erd    airgapped_vllm[local] -> anthropic_cloud[cloud] -> openai_cloud[cloud] -> deepseek_cloud[cloud_apac]
ddl_code_generation         local_ollama[local] -> deepseek_cloud[cloud_apac] -> openai_cloud[cloud] -> mistral_cloud[cloud_eu]
data_dictionary_enrichment  local_ollama[local] -> gemini_cloud[cloud] -> kimi_cloud[cloud_apac] -> openai_cloud[cloud]
socratic_tutoring           anthropic_cloud[cloud] -> openai_cloud[cloud] -> local_ollama[local]
```

### Failover

`llm_gateway.py:186-206`: iterate the chain, `except Exception → continue`,
raise `LLMRouterError` when exhausted. Correct as a mechanism. Two problems:

- **Failover crosses jurisdictions without a gate.** `unstructured_doc_parsing`
  — the route that receives the customer's raw PRD — degrades US → US → APAC
  with no policy check. The README calls the APAC providers "opt-in fallbacks,
  never primaries for sensitive tasks" (`README.md:99-102`); in code they are
  ordinary chain members with no opt-in mechanism of any kind.
- **The catch is total.** A `pydantic.ValidationError` from Instructor, an auth
  failure, and a network timeout are indistinguishable — all silently advance to
  the next provider, potentially in another jurisdiction.

### Air-gap enforcement — works, coarsely

`llm_gateway.py:122-128`. Verified empirically:

```
AIRGAPPED=true:
  unstructured_doc_parsing    airgapped_vllm[local] -> local_ollama[local]
  schema_reasoning_and_erd    airgapped_vllm[local] -> local_ollama[local]
  ddl_code_generation         local_ollama[local] -> airgapped_vllm[local]
  data_dictionary_enrichment  local_ollama[local] -> airgapped_vllm[local]
  socratic_tutoring           local_ollama[local]

llm_override escape attempts under AIRGAPPED=true:
  anthropic_cloud  -> REFUSED
  deepseek_cloud   -> REFUSED
  local_ollama     -> ['local_ollama']
```

**This is correct and worth crediting.** The filter is applied *after* override
resolution (`llm_gateway.py:122`), so a caller cannot escape via
`llm_override` — a mistake that would have been easy to make. `socratic_tutoring`
has no `airgapped_overrides` entry (`model_router.yaml:127-139`) and correctly
falls through to `task_routing` filtered to local.

Three caveats:

- **The appliance cannot actually serve air-gapped mode.** The air-gapped
  primary for both reasoning tasks is `airgapped_vllm` at
  `http://vllm-server.internal:8000/v1` (`model_router.yaml:79-84`). No vLLM
  service exists in `docker-compose.appliance.yml` — only `ollama-engine` under
  the `airgap` profile (`docker-compose.appliance.yml:157-164`). Every
  air-gapped request therefore fails its primary and falls back.
- **Cloud keys are injected regardless.** `AIRGAPPED=${AIRGAPPED:-false}` sits
  alongside six cloud API keys on both `modelbox-backend` and `modelbox-worker`
  (`docker-compose.appliance.yml:49-58, 90-98`), and `litellm-proxy` runs with
  cloud keys unconditionally (`docker-compose.appliance.yml:120-124`). There is
  no `internal: true` network, no egress firewall. Air-gap is a Python
  conditional, not a network property. For a regulated buyer that is the
  difference between a control and a promise.
- **Temperature leaks across modes.** `_resolve_task_temperature`
  (`llm_gateway.py:134-136`) reads `task_routing` only, so in air-gapped mode
  the temperature comes from the cloud route's config. Cosmetic, but it shows
  the two config trees are not consistently paired.

### Masking — a no-op

`llm_gateway.py:212-221`. With `MASK_METADATA_IN_PROMPTS=true`:

```
in :  Table hr_salaries has columns employee_ssn, base_salary_usd
out:  Table hr_salaries has columns employee_ssn, base_salary_usd
identical? True
```

The docstring claims "Full tokenized masking is implemented in the governance
engine" (`llm_gateway.py:215`). There is no governance engine — grep for it
returns nothing. The body is `# TODO(governance)` followed by `return prompt`.
Confirms DISAGREEMENT (f). Setting the flag changes nothing but the operator's
belief. `config/model_router.yaml:20-21` and `.env.example` both advertise it.

### What actually leaves the box

For `POST /model/synthesize`: the full `_SYSTEM_PROMPT`
(`synthesis_engine.py:44`) plus the user's verbatim `request.content` — the raw
PRD, Jira story, or DDL — unmodified (`synthesis_engine.py:207-213`).
For `transform-paradigm`: every entity name, entity type, and **every column
name** in the model (`paradigm_translator.py:115-119`). For
`socratic/step`: entity names plus the full conversation history
(`trainer_service.py:86-100`).

### What record exists that it left — **none**

There is no audit table, no audit module, and no audit call site. Grep for
`audit` across `backend/app` returns zero hits. The only trace of an outbound
call is `logger.info("Routing task '%s' -> provider '%s'")`
(`llm_gateway.py:189`), and:

- it records the task and provider but **not** the model id, user, workspace,
  prompt hash, token count, or timestamp of what was sent;
- the application **never configures logging** — no `basicConfig`, no
  `dictConfig`, verified by grep. Under uvicorn's default config the root logger
  sits at WARNING and application loggers propagate to it. Verified:
  ```
  root logger at default WARNING captured: ''
  ```
  **The one line that would tell you a prompt left the box is not emitted at
  runtime.**

So: an operator running `MASK_METADATA_IN_PROMPTS=true` in production is
sending unmasked schema metadata to a US cloud provider, with no durable
record that it happened. That combination is the single most serious finding in
this report.

---

## 6. TEST & CI COVERAGE

### The suite

`backend/.venv` (Python 3.11.9, pytest 9.1.1): **143 passed in 22.67s.**

Note: the brief said 129. The current count is 143 — 12 of those are the
parametrized Trainer-lab guard plus recent additions. Whatever inventory said
129 is stale.

| File | Asserts | What it actually does |
| :-- | --: | :-- |
| `test_synthesis_pipeline.py` | 124 | The strongest file. Real async DB (aiosqlite), real ORM writes, mocked gateway. Exercises persistence, RBAC, cardinality normalization, round-trip. Genuine behavioral coverage. |
| `test_graph_engine.py` | 48 | Behavioral — constructs graphs, asserts on emitted codes and severities. Solid. |
| `test_introspection_snowflake.py` | 44 | 39 of 44 asserts are string/dict-literal comparisons against mocked cursor rows. Tests the mapping table, not the driver. |
| `test_exporter_service.py` | 41 | 14 string-literal asserts. `assert "CREATE TABLE" in ddl`-shaped. |
| `test_phase3_exporters.py` | 35 | **The gap.** See below. |
| `test_diff_engine.py` | 25 | Reasonable behavioral coverage of column add/drop/type. |
| `test_data_dictionary.py` | 20 | Structural key checks. |
| `test_seed_generator.py` | 19 | Checks FK integrity and determinism — good. Does not check values against declared constraints. |
| `test_api_keys.py` | 12 | Real behavior — hashing, expiry, auth. Good. |
| `test_column_semantics_roundtrip.py` | 9 | Real round-trip test. Good — and exactly the pattern the other IR fields need. |
| `test_list_models.py` / `test_connectors_delete.py` / `test_config.py` / `test_validate_graph.py` | 14 | Small, behavioral, fine. |
| `test_trainer_labs.py` | 1 | Parametrized ×5. **The best test in the repo** — see §7. |

### What the tests do not assert

**No exporter output is ever handed to its own toolchain.** This is the direct
cause of every §4 finding. Concretely, `test_phase3_exporters.py` asserts:

```python
assert 'syntax = "proto3";' in proto              # :147
assert "int32 id = 1;" in proto                   # :149
assert "customers_count" in metric_names          # :201
assert "measure: total_total {" in orders         # :187
assert doc["kind"] == "DataContract"              # :124
```

Every one of these passes on output that `dbt parse` rejects outright. The
MetricFlow test (`test_phase3_exporters.py:190-201`) checks that a measure name
appears in a list — it would pass unchanged if the file were missing `label`,
pointed at a nonexistent `ref()`, used an invalid `agg`, and omitted
`agg_time_dimension`. Which is exactly what it does.

Also untested:
- DDL correctness beyond substring presence — no dialect re-parse, no
  topological-order test, no `NOT NULL` expectations.
- Seed output against the model's own declared constraints.
- `_maybe_mask` behavior with masking enabled (no test asserts it does
  anything, which is consistent with it doing nothing).
- Air-gap routing (`resolve_route` under `AIRGAPPED=true`) — there is no test.
  This is the flagship compliance control.
- `llm_override` escape attempts.
- Relationship diffing (correctly, since the feature does not exist).
- `references` round-trip (would fail).
- `suggested_metrics` round-trip (would fail).

### Frontend

- **Zero tests.** No `*.test.*` or `*.spec.*` files exist under `frontend/src`.
- `tsc --noEmit` **passes** (exit 0).
- `next build` **succeeds** (`frontend/build.log`).
- **`npm run lint` is non-functional.** `next lint` drops into its interactive
  "How would you like to configure ESLint?" setup prompt — there is no
  `.eslintrc*` in `frontend/`. The script exists in `package.json:10` and has
  never run.

### CI — there is none

`.github/` does not exist. There is no workflow, no gate, no release automation.
Consequently CI gates: **nothing**. Not tests, not typecheck, not build, not
lint, not migrations, not image publication.

This directly contradicts `README.md:112-124` (which names
`.github/workflows/release.yml` by path), `ROADMAP.md:16` ("CI on every push,
GHCR release on tags"), and `docs/RELEASE_NOTES_v1.5.0.md:3` ("**CI:** green").

### Dependency reproducibility

`backend/requirements.txt` uses `>=` for **all 38 direct dependencies** — zero
upper bounds, no lockfile, no constraints file. CI (if it existed) and the
appliance image resolve to whatever PyPI serves at build time. `Dockerfile.backend`
runs a plain `pip install -r requirements.txt`.

Resolved versions in `backend/.venv` versus the floor the code was written
against:

| Package | Floor | Resolved | Delta |
| :-- | :-- | :-- | :-- |
| **sqlglot** | `>=23.0.0` | **30.16.0** | **7 majors ahead** |
| **pytest** | `>=8.0.0` | **9.1.1** | **1 major ahead** |
| **mypy** | `>=1.9.0` | **2.3.0** | **1 major ahead** |
| **openai** | `>=1.14.0` | **2.53.0** | **1 major ahead** |
| **mistralai** | `>=0.1.0` | **2.9.1** | **2 majors ahead** |
| **google-genai** | `>=0.1.0` | **2.17.0** | **2 majors ahead** |
| **redis** | `>=5.0.3` | **8.1.0** | **3 majors ahead** |
| **rq** | `>=1.16.0` | **2.10.0** | 1 major ahead |
| **bcrypt** | `>=4.1.0` | **5.0.0** | 1 major ahead |
| **duckdb** | `>=0.10.0` | **1.5.5** | 1 major ahead |
| **snowflake-connector-python** | `>=3.7.1` | **4.7.2** | 1 major ahead |
| **databricks-sql-connector** | `>=3.1.0` | **4.4.0** | 1 major ahead |
| **sqlfluff** | `>=3.0.0` | **4.3.0** | 1 major ahead |
| pydantic | `>=2.6.0` | 2.13.4 | minor |
| litellm | `>=1.35.0` | 1.96.0 | minor |
| fastapi | `>=0.110.0` | 0.141.1 | minor (0.x — minors are breaking) |
| anthropic | `>=0.19.0` | 0.121.0 | 0.x, 100 minors ahead |
| instructor | `>=1.2.0` | 1.15.4 | minor |
| sqlalchemy | `>=2.0.28` | 2.0.51 | patch |
| celery | `>=5.3.6` | 5.6.3 | minor |

Transitively pulled: `starlette 1.6.0`, `pandas 3.0.5`, `numpy 2.4.6`,
`protobuf 7.35.1` — none pinned, all major-version-sensitive.

**The four the brief called out.** `sqlglot` is the sharp one: it is the entire
DDL and diff engine, and 23→30 spans seven majors of dialect-generation changes.
Every §4 DDL result in this report is a statement about sqlglot 30.16.0 and
carries no guarantee for the next `docker build`. `pydantic` is fine (2.6→2.13
is additive). `litellm` 1.35→1.96 is 61 minors of provider-adapter churn on the
only egress path. `pytest` 9 is a testing-only risk but does mean the suite may
simply stop collecting on a fresh install.

**What pinning would cost.** Generating `requirements.lock` via
`pip freeze` from the current working `.venv` is roughly a half-day: produce the
lock, switch `Dockerfile.backend` to install from it, keep `requirements.txt` as
the human-readable direct-dependency list with floors, and add a monthly
`pip-compile --upgrade` refresh. The ongoing cost is one PR a month plus the
occasional real upgrade. The cost of *not* doing it is that a Tuesday image
rebuild silently changes DDL output for every customer, and no test would catch
it because no test parses DDL.

**Venv separation.** The audit toolchain was deliberately kept out of the app
venv, as instructed. Installing `dbt-core`/`metricflow` into `backend/.venv`
would downgrade `protobuf` 7.35.1 → 6.33.6, `pathspec` 1.1.1 → 0.12.1, and
remove `mypy` 2.3.0. Every result in this report is labelled with the venv that
produced it; see the Appendix.

---

## 7. TRAINER & CURRICULUM

### Codes emitted by the linter — 12

From `graph_engine.py`: `CYCLIC_FK` (:141), `MISSING_PK` (:152),
`DANGLING_REF` (:169, :186), `NAMING_CONVENTION` (:230, :241, :272),
`MISSING_GRAIN` (:295), `MISSING_DESCRIPTION` (:315, :332), `PII_EXPOSURE` (:359),
`FAN_OUT_RISK` (:404), `MISSING_SLA` (:429), `INVALID_RANGE` (:459),
`INVALID_REGEX` (:477), `ORPHAN_ENTITY` (:508).

### Lab coverage per module — and it is exact

| Module | Lab | Codes exercised |
| :-- | :-- | :-- |
| 1 | `m1_lab1_grain_and_fanout.json` | `FAN_OUT_RISK`, `MISSING_GRAIN`, `NAMING_CONVENTION` |
| 2 | `m2_lab1_semantic_grain_and_fanout.json` | `FAN_OUT_RISK`, `MISSING_DESCRIPTION`, `MISSING_GRAIN` |
| 3 | `m3_lab1_governance_and_contracts.json` | `MISSING_DESCRIPTION`, `MISSING_SLA`, `NAMING_CONVENTION`, `PII_EXPOSURE` |
| 4 | `m4_lab1_quality_and_testing.json` | `INVALID_RANGE`, `INVALID_REGEX` |
| 5 | `m5_capstone_mastery.json` | `INVALID_RANGE`, `INVALID_REGEX`, `MISSING_GRAIN`, `MISSING_PK`, `MISSING_SLA`, `NAMING_CONVENTION`, `PII_EXPOSURE` |

**Labs ↔ curriculum: zero drift.** The code set in each
`docs/curriculum/MODULE_N.md` matches its lab JSON exactly, module for module,
verified by extraction. **Say so plainly: this is the best-maintained part of
the project.**

The reason it holds is `backend/tests/test_trainer_labs.py:44-54`, which loads
every lab JSON, runs the real `GraphEngine.validate` on its flawed graph, and
asserts `produced == expected` as **set equality** — not a subset. A lab that
seeds an unlisted flaw, or lists a flaw the linter no longer emits, fails CI…
except there is no CI (§6), so it only fails on a manual `pytest` run. This is
the exact pattern every exporter needs.

### Drift that does exist

- **Three linter codes are never taught:** `CYCLIC_FK`, `DANGLING_REF`,
  `ORPHAN_ENTITY`. The two hard *errors* the linter can raise —
  the only two that set `is_valid: false` (`graph_engine.py:208`) — have no
  lab. Students never encounter a model that fails validation outright.
- **Two grading paths that disagree.** Labs grade against the full 12-code
  linter via `POST /model/validate-graph`
  (`frontend/src/app/trainer/page.tsx:67` → `frontend/src/lib/api.ts:255-260`).
  The `POST /trainer/grade` endpoint uses a completely separate 3-invariant
  rubric (`trainer_service.py:41-45`, `:136-169`). **Their intersection is
  exactly one code: `MISSING_PK`.** Eight of the nine competencies the
  curriculum teaches cannot be scored by the assignment grader; the two hard
  errors the grader checks are never taught. See DISAGREEMENT (h).
- `POST /model/validate-graph` — the endpoint the entire Trainer product runs
  on — **is not documented** in `docs/API_REFERENCE.md` (0 occurrences).
- `grade_graph` silently substitutes the full 3-invariant default when an
  assignment's `expected_invariants` names only unknown codes
  (`trainer_service.py:149-151`). An instructor who writes
  `{"MISSING_GRAIN": true}` gets graded on cycles, PKs, and dangling refs
  instead, with no warning.

---

## 8. DOC & VERSION DRIFT

### Version stamps disagree four ways

| Where | Value | Line |
| :-- | :-- | :-- |
| FastAPI app | `1.2.0` | `backend/app/main.py:87` |
| Frontend package | `1.2.0` | `frontend/package.json:3` |
| Appliance images (×3) | `v1.3.0` | `docker/docker-compose.appliance.yml:22,36,82` |
| Latest release notes | `v1.5.0` | `docs/RELEASE_NOTES_v1.5.0.md:1` |

`/health` reports `1.2.0` (`main.py:107`), so an operator running a v1.5.0
appliance is told they are on 1.2.0.

### Stale or false documentation

| Doc | Problem |
| :-- | :-- |
| `README.md:112-124` | Documents a GHCR release workflow at a path that does not exist. |
| `README.md:116` | "CI gates every push" — no CI exists. |
| `ROADMAP.md:16` | Lists CI + GHCR release as shipped infrastructure. |
| `ROADMAP.md:19` | "Honest gaps" list names six things that now ship (§2). |
| `ROADMAP.md:83` | "`hvac` already in deps" — it is not in `requirements.txt`. |
| `RELEASE_NOTES_v1.5.0.md:3` | "**CI:** green" — asserts the status of a system that does not exist. |
| `docs/API_REFERENCE.md` | Missing `POST /api/v1/model/validate-graph`, the Trainer's grading endpoint. |
| `PRD_TRD_v2.md:55` | FR-2.1 names DuckDB (not implemented) and omits MySQL (implemented). |
| `graph_engine.py:107-114` | Docstring claims `topological_order` is used for "deterministic DDL emission order". It is not (§4.1). |
| `llm_gateway.py:215` | Docstring claims "Full tokenized masking is implemented in the governance engine." No governance engine exists. |
| `graph_repository.py:5-6` | "synthesis/transform currently keep their own copies and can delegate here in a later refactor" — accurate, and the duplication is a live risk (§1). |

### What is *not* drifted — credit where due

- **Migrations:** `0001`→`0012` form a single clean linear chain, one head, no
  branches, no gaps. Verified by reading every `revision`/`down_revision` pair.
  Migration content matches the ORM (`0010` column semantics, `0011` entity
  governance, `0012` quality rules all correspond to live `metadata_store.py`
  columns).
- **`docs/API_REFERENCE.md` and `docs/USER_GUIDE.md` are byte-identical to their
  `frontend/public/content/` copies.** Someone is keeping those in sync.
- **`.env` is correctly gitignored** (`.gitignore:20`) and untracked.
- **Curriculum ↔ labs:** zero drift (§7).

---

## 9. TOP FINDINGS

### BLOCKERS

**B1 — MetricFlow export is non-functional. 0/5 gold graphs parse.**
*Impact:* A shipped, documented, PRD-committed exporter (FR-2.3) produces output
that dbt rejects on every model. Any customer who clicks "MetricFlow" gets a
file that cannot be added to a dbt project.
*Root cause:* four independent defects, none caught because no test invokes dbt.
Missing `label` (`exporter_service.py:531-548`); `model: ref('{name}')` instead
of `ref('stg_{name}')` (`exporter_service.py:552` vs `:147`); unmapped
aggregation vocabulary — `avg` crashes dbt with a traceback
(`exporter_service.py:520`); no `defaults.agg_time_dimension`, which the IR
cannot express (§3).
*Effort:* 2–3 days for the first three. The fourth needs an IR field
(`is_agg_time_dimension` or entity-level `agg_time_column`) plus a canvas
control: **1 week total.**

**B2 — No CI exists, and three documents claim it does.**
*Impact:* Nothing gates `main`. Every §4 defect reached `main` through a green
local run. The README instructs users to cut release tags from "a green `main`"
against a workflow file that does not exist.
*Root cause:* `.github/` was never created; docs were written aspirationally
(`README.md:112-124`, `ROADMAP.md:16`, `RELEASE_NOTES_v1.5.0.md:3`).
*Effort:* **1 day** for pytest + `tsc --noEmit` + `next build` + alembic-head
check on push. Half a day more for the GHCR release workflow the README already
documents.

**B3 — Masking is a stub while the README sells zero-egress governance, and no
audit record exists.**
*Impact:* An operator sets `MASK_METADATA_IN_PROMPTS=true`, believes schema
metadata is tokenized, and ships raw table and column names — plus the verbatim
source PRD — to a US cloud provider. There is no durable record it happened: no
audit table, and the single `logger.info` at `llm_gateway.py:189` is not emitted
because the app never configures logging (verified empirically, §5). This is a
compliance misrepresentation, not just a missing feature.
*Root cause:* `_maybe_mask` is `return prompt` behind a `# TODO(governance)`
(`llm_gateway.py:212-221`); zero `audit` references in `backend/app`.
*Effort:* **1 day** to make the flag honest — either implement reversible
identifier tokenization or fail startup when the flag is set and masking is
unimplemented, and delete the claim from `README.md:106` and
`model_router.yaml:20-21`. **3–4 days** for an append-only `egress_audit` table
(model id, user, workspace, task, provider, egress class, prompt SHA-256, token
counts, timestamp) written from the one choke point, plus `logging.dictConfig`
at startup.

### HIGH

**H1 — Synthetic seed data violates the contract the same model exports.**
*Impact:* Ship the seed and the dbt tests together and `dbt build` fails on your
own fixtures. Verified: `score` values of 6301.38 against a declared
`max_value: 5.0`; `ref_code_1` against `^[A-Z]{3}-\d{4}$`; `'icd10_code_1'`
(12 chars) into `VARCHAR(10)` on `healthcare-ehr`.
*Root cause:* `seed_generator.py:134-178` reads `col.name` and `col.data_type`
and nothing else — never `min_value`, `max_value`, `regex_pattern`, or the
declared length.
*Effort:* **2–3 days.** Bounds and length clamping are easy; regex needs a small
generator (`exrex`-style or a hand-rolled subset) or a documented fallback.

**H2 — ODCS declares every non-PK column optional and is stamped with the wrong
spec version.**
*Impact:* The governance artifact asserts the opposite of the truth for most
columns — `banking-datavault` emits `required: false` for `load_dts` and
`record_source`. Consumers validating against `apiVersion: v0.9.3` will not find
`schema`/`properties` at that version.
*Root cause:* `required: col.is_primary_key` (`exporter_service.py:347`) is the
only nullability signal the IR offers; `apiVersion: v0.9.3`
(`exporter_service.py:375`) with a v3 body.
*Effort:* **1 day** for the version stamp. The `required` fix depends on H4.

**H3 — DDL emits no `NOT NULL` and is not deployable on BigQuery, Databricks, or
ClickHouse.**
*Impact:* Three of seven advertised dialects produce DDL the engine rejects.
BigQuery needs `NOT ENFORCED`; Databricks needs `NOT NULL` on PK columns;
ClickHouse needs `ENGINE =` and forbids `Nullable` PKs.
*Root cause:* `_entity_create_table` (`exporter_service.py:113-135`) builds one
ANSI string and delegates everything dialect-specific to sqlglot, which does not
add mandatory modifiers.
*Effort:* **3–4 days** for per-dialect constraint post-processing. Depends on
H4 for `NOT NULL`.

**H4 — The IR has no nullability, uniqueness, default, or check.**
*Impact:* The root cause under H2, H3, and part of B1. Four exporters guess, and
they guess differently: Avro says every non-PK is nullable, Protobuf says
nothing is, ODCS says only PKs are required, DDL says nothing at all.
*Root cause:* `ColumnSchema` (`data_model.py:420-454`) stops at PK/FK/PII/metric
plus three test-only quality rules.
*Effort:* **1 week.** Four Pydantic fields, one migration, two persistence-map
updates (`graph_repository.py:85`, `synthesis_engine.py:371`), canvas editor
controls (`frontend/src/components/canvas/ColumnSemanticEditor.tsx`), LLM prompt
update, and the round-trip test — `test_column_semantics_roundtrip.py` is
already the right template.

**H5 — DDL emission order is declaration order, so FK-forward-references abort.**
*Impact:* Any model whose entities are not declared parent-first emits DDL that
fails on the first statement. The five templates are ordered correctly by hand,
which is the only reason this is invisible today; LLM-synthesized models have no
such guarantee.
*Root cause:* `exporter_service.py:101-104` ignores
`GraphEngine.topological_order`, whose docstring says it exists for this purpose
(`graph_engine.py:107-114`).
*Effort:* **Half a day.** The function already exists; call it, with the
existing `NetworkXUnfeasible` fallback the seed generator already uses
(`seed_generator.py:109-113`).

**H6 — Protobuf field tags are wire-unstable.**
*Impact:* Inserting a column renumbers every subsequent field — verified,
6 of 7 tags shifted on `saas-subscription/dim_customer`. Any deployed consumer
silently misparses. For a product positioned around data contracts this is the
opposite of the value proposition.
*Root cause:* `enumerate(entity.columns, start=1)`
(`exporter_service.py:421`). `ordinal_position` exists in the IR but is ignored
(verified: reversing it changed nothing).
*Effort:* **2–3 days.** Needs a stable per-column tag: either a persisted
`proto_tag` allocated once and never reused, or derive from a stable column
identity. Also fix `NUMERIC → double` (money as float) and unsanitized filenames
while in there.

**H7 — JWT accepts RS256 tokens without validating `aud` or `iss`.**
*Impact:* An RS256 token minted by the same IdP for a *different* application is
accepted as a ModelBox session. This is the enterprise SSO gate.
*Root cause:* `jwt.decode(token, key, algorithms=[algorithm])`
(`core/security.py:94`) — no `audience=`, no `issuer=`, and no settings fields
for them (`config.py:89-94`).
*Effort:* **1–2 days**, including config, validation, and tests. Already
identified as ROADMAP T8 (`ROADMAP.md:75`).

**H8 — All 38 dependencies are floor-only; sqlglot is 7 majors past its floor.**
*Impact:* Every DDL and diff result in this report is a statement about sqlglot
30.16.0. A rebuild resolves to whatever PyPI serves, and no test parses DDL, so
a behavior change ships silently.
*Root cause:* `backend/requirements.txt` uses `>=` throughout; no lockfile;
`Dockerfile.backend` does a plain `pip install -r`.
*Effort:* **Half a day** to add `requirements.lock` from the working `.venv` and
switch the Dockerfile. Ongoing: one refresh PR a month.

### MEDIUM

**M1 — `suggested_metrics` never round-trips, making half the diff engine
unreachable.** `synthesis_engine.py:188` hard-codes `[]`; `DiffEngine`'s
formula-reference branch (`diff_engine.py:102, 117-146`) can never fire through
`POST /model/diff`. Either persist metrics or delete the dead branch. **2 days.**

**M2 — Diff ignores relationships, PKs, and governance.** Verified: removing all
3 FKs from `healthcare-ehr` yields 0 statements and 0 breaking changes
(`diff_engine.py:33-90`). FK drops are the most common breaking migration.
**3 days.**

**M3 — Cube and LookML emit `SUM()` over foreign keys.** `totalCustomerSk`,
`total_plan_sk`. Cube also excludes nothing (`exporter_service.py:285`); LookML
excludes only the PK (`:465`). Cube also maps `BOOLEAN → string`
(`_cube_type:999-1005` has no boolean branch). **1 day.**

**M4 — Trainer's two grading paths intersect on one code.** Labs grade against
12 linter codes; `POST /trainer/grade` scores 3 invariants
(`trainer_service.py:41-45`). Reconcile onto the linter. **2 days.**
See DISAGREEMENT (h).

**M5 — Version stamps disagree four ways** (1.2.0 / 1.2.0 / v1.3.0 / v1.5.0).
`/health` misreports the running version. **Half a day**, plus a CI check once
B2 lands.

**M6 — `ColumnSchema.references` is dead.** Declared at `data_model.py:436`,
plumbed into the frontend types, read by nothing, dropped by both persistence
paths. Either wire it (it would give the ODCS/dbt emitters a column-level FK
target independent of the relationship list) or delete it. **1 day either way.**

**M7 — dbt emits `dbt_expectations` tests with no `packages.yml`.**
`exporter_service.py:942-967` vs `:140-151`. Any model with a quality rule
produces an unresolvable project. **Half a day.**

**M8 — Air-gap is a Python conditional, not a network control.** Cloud keys are
injected into backend, worker, and litellm-proxy regardless of `AIRGAPPED`
(`docker-compose.appliance.yml:49-58, 90-98, 120-124`); no `internal: true`
network. Separately, air-gapped mode's primary provider `airgapped_vllm` has no
service in the compose file at all. **2 days** for a compose profile that omits
cloud keys and isolates the network.

**M9 — `next lint` has never run.** No `.eslintrc*`; the script drops into
interactive setup. Zero frontend tests. **1 day** for ESLint config plus a
smoke test on the canvas store.

**M10 — README, ROADMAP, and release notes assert facts that are false.**
Beyond B2's CI claims: `hvac` in deps, six shipped features listed as gaps,
DuckDB introspection, `topological_order` used for DDL ordering, "governance
engine" masking. **1 day** of doc reconciliation, ideally right after B2 so the
CI claim becomes true rather than deleted.

### Suggested sprint sequence

1. **Sprint 1 (credibility):** B2, B3, H8, M5, M10. Make the claims true or
   remove them. One week.
2. **Sprint 2 (IR foundation):** H4, then H2/H3's dependent halves. One to two
   weeks. Everything else queues behind this.
3. **Sprint 3 (exporters):** B1, H5, H6, M3, M7 — and a toolchain-verification
   test harness modelled on `test_trainer_labs.py`, run against the five gold
   graphs. Two weeks.
4. **Sprint 4 (correctness debt):** H1, H7, M1, M2, M4.

---

## 10. OPEN QUESTIONS

1. **Is the appliance meant to serve air-gapped mode out of the box?** The
   air-gapped route's primary is `airgapped_vllm`
   (`model_router.yaml:99, 128-137`) and the compose file has no vLLM service.
   Ship a vLLM container, or repoint `airgapped_overrides` at `local_ollama` and
   demote vLLM to a documented BYO endpoint?
2. **What is the intended masking semantic?** Reversible tokenization (so the
   LLM's output can be un-tokenized back onto real names) is a materially bigger
   build than one-way redaction. The docstring says "reversible tokens"
   (`llm_gateway.py:220`); the README says "obfuscate". Which are we selling?
3. **Does `POST /trainer/grade` have real users?** If the labs are the product,
   the cleanest fix for M4 is to delete the 3-invariant rubric and grade
   everything through the linter. If instructors are authoring assignments
   against those invariants, that is a migration, not a deletion.
4. **Which dialects are we willing to certify?** Making BigQuery, Databricks,
   and ClickHouse actually deployable (H3) is real per-dialect work. Certifying
   four (postgres/snowflake/redshift/duckdb) and labelling the rest "best
   effort" in the UI is a legitimate alternative, and honest.
5. **Should quality rules reach the database?** `min_value`/`max_value`/
   `regex_pattern` currently emit only to dbt and ODCS. Emitting `CHECK`
   constraints in DDL would make them enforced rather than tested — but changes
   the DDL's failure mode from "test fails in CI" to "insert rejected at
   runtime". Product call.
6. **Is `ordinal_position` intended to be the stable column identity?** It is
   the natural anchor for a stable Protobuf tag (H6), but nothing currently
   guarantees it is stable across a canvas reorder —
   `graph_repository.py:99-101` falls back to list position when it is null.
7. **Are FR-2.5's RealityDB/SafeSQL seams live commitments or removed scope?**
   The PRD dedicates §2.6 to them; the code has zero references. If removed,
   `PRD_TRD_v2.md:59, 208-215` should say so.
8. **Do we want one persistence path or two?** `GraphRepository._persist` and
   `SynthesisEngine._persist_graph` are duplicated column-by-column
   (`graph_repository.py:85-102`, `synthesis_engine.py:278-295`).
   `graph_repository.py:5-6` acknowledges this. H4 will require editing both;
   consolidating first is roughly a day and removes a class of future drift.

---

## DISAGREEMENTS — response to prior architect findings

### (a) *"ParadigmTranslator routes a deterministic transformation through the LLM"* — **CONFIRMED**

`ParadigmTranslator.transform` sends the model to
`structured_completion(task="schema_reasoning_and_erd", …)`
(`paradigm_translator.py:82-91`) and replaces the persisted graph with whatever
comes back (`:94`). The prompt (`:113-126`) carries only entity names, types, and
column *names* — not data types, keys, PII flags, descriptions, or
relationships — while the system prompt instructs the model to "Preserve all
column descriptions and semantic tags" (`:86-90`) that were never sent. So the
transformation is both non-deterministic *and* structurally lossy by
construction.

**Refinement worth noting:** the codebase already demonstrates the deterministic
alternative twice. `SynthesisEngine._normalize_relationships`
(`synthesis_engine.py:324-368`) deterministically fixes Fact→Dimension
cardinality *after* the LLM, and `_PARADIGM_STRATEGY`
(`paradigm_translator.py:37-55`) already encodes the transformation rules as
prose. Kimball→OBT (flatten along `dependency_layers`, which exists at
`graph_engine.py:117`) and 3NF→Data Vault (hub/link/satellite decomposition plus
hash-key/`load_dts`/`record_source` columns) are mechanical given the graph.
`TransformOptions.hash_key_algorithm` and `satellite_split_strategy`
(`data_model.py:632-633`) are accepted, serialized into the prompt as
`str(dict)`, and otherwise unused — they were designed for a deterministic
implementation that was not written.

### (b) *"ColumnSchema lacks nullability/uniqueness/default/check, so ODCS emits `required: is_primary_key` and DDL cannot emit NOT NULL"* — **CONFIRMED**

Both halves verified directly.

`ColumnSchema` (`data_model.py:420-454`) has none of the four.
ODCS: `"required": col.is_primary_key` (`exporter_service.py:347`) — visible in
`banking-datavault/odcs/datacontract.yaml` as `required: false` on `load_dts`
and `record_source`.
DDL: `_entity_create_table` emits `f"    {col.name} {col.data_type}"`
(`exporter_service.py:118`) and nothing else. Verified by scanning all 35
emitted DDL files across 7 dialects: **zero `NOT NULL`**.

**Refinement — the blast radius is wider than stated.** The same gap causes:
Avro to guess `["null", T]` for every non-PK (`exporter_service.py:393-398`);
Protobuf to have no presence at all, so Avro and Protobuf describe the same
model with contradictory nullability; Databricks DDL to be invalid (PK columns
must be `NOT NULL`); and dbt to emit `not_null` only on PKs
(`exporter_service.py:197`). Also note `min_value`/`max_value`/`regex_pattern`
*do* exist (`data_model.py:444-454`) — they are constraints, but they only ever
reach test frameworks, never DDL `CHECK`. So the IR can say "assert this in CI"
but not "enforce this in the database."

### (c) *"MetricFlow output omits `defaults.agg_time_dimension`, and foreign entities are named after the local FK column rather than the parent's primary entity"* — **CONFIRMED, and it is worse than stated**

Both halves confirmed. `defaults` never appears in any emitted semantic model
(verified programmatically); the validator reports one
`Aggregation time dimension for measure X is not set!` per measure across all
five graphs. Foreign entities use `col.name` (`exporter_service.py:502`).

**Refinement 1 — the naming defect is latent, not active, in the gold graphs.**
In all five templates the FK column name equals the parent's PK column name
(`fact_order_line.customer_sk` → `dim_customer.customer_sk`), so entity names
coincidentally align and the joins would work. Probed with a divergent name:

```
dim_customer     entities=[('customer_sk', 'primary')]
fact_order_line  entities=[('ship_to_customer_sk', 'foreign'), ('product_sk', 'foreign')]
```

MetricFlow joins by entity name, so the join **silently does not exist** — no
error, just a semantic layer that cannot answer the question. Role-playing
dimensions (`ship_to_` / `bill_to_` / `ordered_by_`) are the ordinary Kimball
case, so this will surface the moment a real customer models one.

**Refinement 2 — these are two of *six* MetricFlow defects, and neither is the
first one you hit.** `dbt parse` never reaches the `agg_time_dimension` check.
In order of encounter: missing `label` (kills all 5), `ref()` pointing at
`{name}` instead of `stg_{name}` (kills 4), `agg: avg` crashing dbt with a
traceback (kills `saas-subscription`), *then* `agg_time_dimension`, then
`sat_account_details` having no primary entity, then `month` colliding with a
reserved granularity keyword. Fixing (c) alone changes nothing observable — the
export still fails at the first line. **Treat MetricFlow as one blocker (B1),
not four tickets.**

### (d) *"Protobuf field tags are ordinal-derived and break wire compatibility on column insertion"* — **CONFIRMED, with a correction to the mechanism**

Wire break verified empirically on `saas-subscription/dim_customer`, inserting
one column at position 1:

```
customer_sk 1→1 | customer_id 2→3 | email 3→4 | tier 4→5
valid_from 5→6  | valid_to 6→7    | is_current 7→8
```

Six of seven tags moved.

**Correction:** the tags are **not** derived from `ordinal_position`. They come
from `enumerate(entity.columns, start=1)` (`exporter_service.py:421`) — Python
list position. Verified by reversing every `ordinal_position` on the entity and
re-emitting: the tags were byte-identical. The distinction matters for the fix.
`ordinal_position` is at least persisted (`metadata_store.py:266`) and is
therefore a *candidate* stable anchor — but it is not currently one, because
`graph_repository.py:99-101` falls back to list position whenever it is null,
and nothing preserves it across a canvas reorder. A durable fix needs an
allocate-once-never-reuse tag persisted per column, not a re-derivation from
either field.

Two adjacent defects found while verifying: `NUMERIC(18,2) → double`
(`exporter_service.py:864`) makes `sat_account_details.balance` a floating-point
ledger balance, and the `.proto` filename is not run through `_safe_identifier`
(`exporter_service.py:334`) even though the package name is (`:417`), so a model
titled `Untitled Model` yields `Untitled Model.proto`.

### (e) *"ODCS is v3-shaped but stamped apiVersion v0.9.3"* — **CONFIRMED** (by inspection; no validator available)

`apiVersion: v0.9.3` at `exporter_service.py:375`. The body is v3 vocabulary
throughout: top-level `schema:` (`:384`) where v0.9.x used `dataset:`;
`properties:` (`:361`) where v0.9.x used `columns:`; `logicalType`/`physicalType`
(`:345-346`); `slaProperties` (`:369`); per-property `quality` (`:354`).

**Caveat, per the verification rules:** no ODCS JSON-Schema validator is
installed in either venv, so this verdict rests on reading the emitted document
against the spec's field vocabulary, **not** on a validator run. Mark
**UNVERIFIED** for schema conformance; the version-stamp mismatch itself is a
one-line source fact and needs no tool.

**Refinement:** the stamp is the cheap half. The expensive half is `required:`
(see (b)) — a consumer that *does* accept the v3 shape gets a contract asserting
that almost nothing is mandatory. Also `info.version: "1.0.0"` is hard-coded
(`:380`) while `DataModel.version_number` exists (`metadata_store.py:174`), so
contracts never version, and `info.owner: "modelbox"` is hard-coded (`:381`)
despite real workspace ownership being available.

### (f) *"`_maybe_mask` is a no-op while masking is sold in the README"* — **CONFIRMED**

`llm_gateway.py:212-221`: checks the flag, then `# TODO(governance)` and
`return prompt`. Verified with `mask_metadata_in_prompts=True`:

```
in :  Table hr_salaries has columns employee_ssn, base_salary_usd
out:  Table hr_salaries has columns employee_ssn, base_salary_usd
identical? True
```

The docstring's claim that "Full tokenized masking is implemented in the
governance engine" is false — no such module exists. The flag is advertised in
`config/model_router.yaml:20-21`, `.env.example`, and both compose services
(`docker-compose.appliance.yml:50, 91`).

**Refinement — pair this with the audit gap and it changes severity.** A no-op
masking flag is a missing feature. A no-op masking flag *plus no record of what
was sent* is an unfalsifiable compliance claim: an operator cannot even
retroactively determine what leaked. There is no audit table, and the sole
`logger.info` at `llm_gateway.py:189` does not fire because the app never calls
`logging.basicConfig`/`dictConfig` (verified: root logger at default WARNING
captures nothing). That combination is why I ranked this a blocker (B3) rather
than a medium.

Worth saying plainly: the *choke point* is correct. Every prompt does pass
through this one function (`llm_gateway.py:183`), and there are exactly three
call sites into the gateway. The architecture for masking and audit is right;
only the bodies are missing. That makes B3 a days-scale fix, not a redesign.

### (g) *"air-gap is a global boolean, so residency is not enforced per task in normal mode"* — **CONFIRMED, with credit where it is due**

`Settings.airgapped` is process-global (`config.py:74`), read through
`is_airgapped` (`:129-132`), and consulted once in `resolve_route`
(`llm_gateway.py:114, 122`). There is no per-task, per-workspace, or
per-request residency policy. The only granularity available is
`llm_override`, which is caller-supplied and per-request — a preference, not a
control.

Verified consequence in normal mode: `unstructured_doc_parsing`, the route that
receives the customer's raw PRD, resolves
`anthropic_cloud[cloud] → openai_cloud[cloud] → kimi_cloud[cloud_apac] →
airgapped_vllm[local]`. The EU-sovereign provider `mistral_cloud[cloud_eu]`
appears in exactly one chain — as the *last* fallback on `ddl_code_generation`.
An EU customer has no way to pin EU residency short of full air-gap.

**Credit:** the boolean itself is implemented correctly, which is not nothing.
The filter is applied *after* override resolution (`llm_gateway.py:122`), so a
caller cannot escape it — verified: `llm_override=anthropic_cloud` and
`=deepseek_cloud` are both REFUSED under `AIRGAPPED=true`. And the filter keys
off the declared `egress:` field rather than a provider-name blocklist
(`llm_gateway.py:130-132`), so adding a cloud provider to
`model_router.yaml` cannot accidentally bypass it. The design is sound; the
granularity is the gap.

**Refinement:** the more urgent problem is not the granularity but that the
control is a language-level conditional. Cloud API keys are injected into
`modelbox-backend`, `modelbox-worker`, and `litellm-proxy` regardless of the flag
(`docker-compose.appliance.yml:49-58, 90-98, 120-124`), and there is no isolated
network. A bug, a future code path, or a direct call to `litellm-proxy:4000`
egresses. And air-gapped mode's own primary provider — `airgapped_vllm` at
`http://vllm-server.internal:8000/v1` — has no service in the compose file at
all, so the mode's happy path is a guaranteed connection failure followed by
fallback. Per-task residency (a `max_egress` field per task route, checked in
`resolve_route`) is roughly a day; the network isolation is the part that makes
either claim defensible.

### (h) *"Trainer grades 3 invariants while the linter emits 9"* — **DIRECTIONALLY RIGHT, NUMBERS WRONG, and the real problem is structural**

**The linter emits 12 codes, not 9:** `CYCLIC_FK`, `MISSING_PK`, `DANGLING_REF`,
`NAMING_CONVENTION`, `MISSING_GRAIN`, `MISSING_DESCRIPTION`, `PII_EXPOSURE`,
`FAN_OUT_RISK`, `MISSING_SLA`, `INVALID_RANGE`, `INVALID_REGEX`, `ORPHAN_ENTITY`
(`graph_engine.py:141, 152, 169, 230, 295, 315, 359, 404, 429, 459, 477, 508`).

**The trainer grader scores 3:** `NO_CYCLIC_FK`, `PK_PRESENT`,
`NO_DANGLING_REF` (`trainer_service.py:41-45`).

**9 is the number of codes the labs actually teach** — `FAN_OUT_RISK`,
`INVALID_RANGE`, `INVALID_REGEX`, `MISSING_DESCRIPTION`, `MISSING_GRAIN`,
`MISSING_PK`, `MISSING_SLA`, `NAMING_CONVENTION`, `PII_EXPOSURE`. So the "9"
was probably a count of the curriculum, not the linter.

**The structural finding is sharper than the arithmetic.** There are two
independent grading paths:

- **Labs** grade through the full 12-code linter, via
  `POST /model/validate-graph` (`frontend/src/app/trainer/page.tsx:67` →
  `frontend/src/lib/api.ts:255-260` → `endpoints/models.py:183-187`).
- **Assignments** grade through the 3-invariant rubric
  (`POST /trainer/grade` → `trainer_service.py:136-169`).

**Their intersection is exactly one code: `MISSING_PK`.** Eight of the nine
competencies the curriculum teaches cannot be scored by the assignment grader,
and the two hard errors the grader checks — `CYCLIC_FK` and `DANGLING_REF`, the
only codes that set `is_valid: false` (`graph_engine.py:208`) — appear in no
lab and no curriculum module.

Two further defects in the grader worth pricing into the same ticket:
`grade_graph` silently substitutes the full 3-invariant default when an
assignment names only unrecognized invariants (`trainer_service.py:149-151`), so
an instructor writing `{"MISSING_GRAIN": true}` is scored on cycles, PKs, and
dangling refs with no warning; and the score is a flat
`len(passed)/len(required)` (`:166`) with no severity weighting, so a cyclic FK
and a missing description would count equally if both were gradable.

**Credit where due, and it is substantial:** the *labs* side has no drift at all.
`test_trainer_labs.py:44-54` asserts **set equality** between each lab's
`expected_flaws` and the linter's actual output, parametrized across all five
labs. The curriculum markdown matches the lab JSON code-for-code, module for
module. This is the one subsystem in the repo with a working drift guard, and it
is the model the exporters should copy.

---

## Appendix A — Tool versions and provenance

| Tool | Version | Where |
| :-- | :-- | :-- |
| Python (app) | 3.11.9 | `backend/.venv` |
| Python (audit toolchain) | 3.11.9 | `backend/.venv-tools` |
| Python (system) | 3.13.7 | not used for results |
| pytest | 9.1.1 | `backend/.venv` |
| sqlglot | 30.16.0 | both venvs, same version |
| pydantic | 2.13.4 | both venvs, same version |
| litellm | 1.96.0 | `backend/.venv` (no calls made) |
| dbt-core | 1.11.12 | `backend/.venv-tools` |
| dbt-postgres | 1.11.0 | `backend/.venv-tools` |
| dbt-semantic-interfaces | 0.9.0 | `backend/.venv-tools` |
| metricflow | 0.211.0 | `backend/.venv-tools` |
| fastavro | 1.12.2 | `backend/.venv-tools` |
| protoc | libprotoc 26.1 | system PATH |
| node | v22.18.0 | system PATH |
| npm | 11.7.0 | system PATH |
| ODCS validator | **not installed** | §4.6 marked UNVERIFIED |
| LookML parser | **not installed** | §4.5 marked UNVERIFIED |

### Which venv produced which result

| Check | Venv / tool |
| :-- | :-- |
| `pytest` — 143 passed | `backend/.venv` |
| DDL re-parse × 7 dialects | `backend/.venv` (sqlglot 30.16.0) |
| Exporter artifact emission (150 files) | `backend/.venv` |
| Seed / diff / claim probes (§4.10, §4.11, DISAGREEMENTS c & d) | `backend/.venv` |
| Gateway routing / air-gap / masking (§5) | `backend/.venv` |
| Avro `parse_schema` | `backend/.venv-tools` |
| `dbt parse` × 5 projects | `backend/.venv-tools` |
| `SemanticManifestValidator` | `backend/.venv-tools` |
| YAML well-formedness | `backend/.venv-tools` |
| Protobuf compile | system `protoc` 26.1 |
| Cube.js syntax | system `node` v22.18.0 |
| Frontend `tsc --noEmit` | `frontend/node_modules` |

The audit toolchain was installed only into `backend/.venv-tools`, as
instructed. Installing it into `backend/.venv` would downgrade `protobuf`
7.35.1 → 6.33.6 and `pathspec` 1.1.1 → 0.12.1 and remove `mypy` 2.3.0, which
would have invalidated the app-venv results above.

## Appendix B — Verification protocol

- **Zero LLM or provider calls were made.** No API keys were set or added. All
  gateway findings come from `resolve_route` and `_maybe_mask`, both pure.
- **All exporter checks ran against the five Requirements Library gold graphs**
  from `frontend/src/lib/templates.ts:97-339`, transcribed field-for-field into
  `SynthesizedModel` objects. Each failure in §4 names its originating graph.
- **No secrets appear in this report.** `.env` was inspected for key *names*
  only; no values, URIs, or credentials were read into the report.
- **Working tree.** The only uncommitted change on `audit/state-report` is this
  file. Scratch artifacts (emitted exports, the five throwaway dbt projects,
  probe scripts) live outside the repo in the session scratchpad.
- **No commits were made by this audit.** Note for the record: commit
  `3050058` ("docs: add research inputs (not implemented); ignore tools venv")
  landed on `audit/state-report` from outside this audit *during* it, adding the
  four research `docs/*.md` files, a root `.gitattributes`, and a `.gitignore`
  entry for `backend/.venv-tools/`. It touches no source and does not affect any
  finding above. `main` remains at `48b83a2`, untouched.
