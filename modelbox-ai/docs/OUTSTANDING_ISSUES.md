# Outstanding issues

**As of 2026-09-30, `main` at `d38d6ec` (Sprint 8 merged through pull request
#26), release v1.12.0**, tagged at `d38d6ec`, published by the gated release
run 36659993511 and verified on the published images by Verify Release run
36660321337. Companion to
`BUILD_EVIDENCE_REVIEW.md`, which argues the evidence; this one is the list.
The previous edition was written on 2026-09-03 on `sprint/6-product-experience`;
entries that have not been re-measured since say so rather than being carried
forward as current.

Every entry names where it is recorded in the tree, so nothing here depends on
remembering a conversation. Ordered by kind, not priority.

---

## 1. Register criteria not met

| id | state | what is missing |
|---|---|---|
| **D10** | **open, two ways** | The cloud half **ran and failed** (2026-09-03, 12 calls, both models FAIL on all three F1 axes). The **local half has never been attempted**. Since 2026-09-28 (decision 4) no surface makes a quality claim for generated models: they are a first draft a modeller reviews, the 0.80 / 0.70 / 0.60 gate is retired as uncalibrated, and THRESHOLD_VERSION 2 is a tracked metric with no pass/fail claim. A new gate is set only against a cited, published baseline. |
| **G8** | **NOT MET** | Re-specified 2026-09-28 to OIDC end to end (decision 5). Server verification is done and tested; the UI login flow is not built (scheduled for Sprint 9), so a SCIM-provisioned user without a local password cannot sign in. SAML 2.0 is added on a pilot's demand. |
| **F1** | **partial** | Last measured 2026-09-03: colour **22 literals remaining of 332**, type **253 of 254 remaining**, blocked on the type-ramp weights decision (§3). Not re-measured since. |
| **F2** | **4 screens of 8** | Last assessed 2026-09-03: four screens still hand-roll state. Not re-assessed since. |
| **F4** | **no evidence of any kind** | Last assessed 2026-09-03: no test, no 500-entity fixture, no benchmark. Not re-assessed since. |
| **F6** | **MET at a stated breadth** | Token layer only. The remaining colour literals sit outside every contrast assertion by construction, so the WCAG claim does not cover rendered screens. Listed so the limit is not forgotten. |
| **H1, H3** | **deferred, no date** | Trainer work is deferred (2026-09-29); the register's sprint column says so. |

Met and not at issue: D8 (failover classification, through the real
Instructor client), F3, F5, F7, G9 (SCIM), G10 (RBAC) and G11 (audit export),
both MET 2026-09-28 against black-box evidence, and G12 (tested restore).

---

## 2. Open defects with a failing test behind them

These are strict `xfail`s — they turn the suite **red** the moment they are
fixed and the marker is not removed, so the inventory cannot silently overstate
progress.

| where | defect |
|---|---|
| `test_conformance_metric.py` | **A total rename scores 0.000.** A model identical to gold in every entity, type, key and relationship, differing only in vocabulary, is scored as having produced nothing. |
| `test_metric_negative_controls.py` | **F1 is insensitive to deletion on large graphs.** Dropping 2 of 12 entities from the AML model scores entity F1 **0.909**; the same proportional loss on a three-entity graph scores 0.500. |

**The fidelity harness's non-preview burn-down is empty.** On `main`'s CI run
36519786048 the harness reported 276 passed, 5 skipped, 22 xfailed, and every
one of the 22 is marked `preview`: 18 are the BigQuery, ClickHouse and
Databricks grammar cases (H3/Q4, labelled Preview and not scheduled for repair)
and 4 are LookML (M3). B6, H11, H12 and M14, open on 2026-09-03, no longer
appear.

---

## 3. Decisions blocking work

Each of these is a judgement call, not a task. Nothing proceeds on them without
an answer. Unchanged since 2026-09-03 except where marked.

| decision | blocks | the tension |
|---|---|---|
| **Type-ramp weights** | 253 F1 conversions | The ramp has to be settled before 20 files can be converted mechanically. |
| **Violet palette entry** | the last 16 colour literals | They are a brand colour with no token. Either the palette gains an entry or the criterion narrows. |
| **Playwright, or a narrowed F4** | all of F4 | A 500-table benchmark needs a browser harness; the alternative is stating the measured ceiling. **Changed 2026-09-29:** the harness now exists (`e2e/`, Playwright in the required Engagement Journey check), so the benchmark could be built on it; no benchmark is built, and the choice between the two remains open. |
| ~~**SAML for G8**~~ | — | **Decided 2026-09-28** (decision 5): G8 is OIDC end to end; SAML on a pilot's demand. |
| **Severity-ordered repair gate** | nothing; it is a live behaviour question | Ordering on `(errors, warnings)` would accept trading a `DANGLING_REF` for two `MISSING_PK`s. It also makes the gate **more permissive**, and `test_a_repair_that_trades_one_defect_for_two_is_discarded` exists because the opposite was decided deliberately. See `synthesis_engine.py`. |
| **Normalising the lint gate** | nothing yet | `lint_delta_per_entity` is reported; the **gate still uses the raw count**. Switching it is a `THRESHOLD_VERSION` change, and it would move the score in the flattering direction, so it must be argued on its own terms. |
| **Scaling `MIN_ENTITY_F1`** | the xfail in §2 | Fixing deletion-insensitivity means changing a threshold that was fixed before the first provider call. |
| **Embeddings for the matcher** | closing the total-rename defect | The cheap structural alternative was built, measured and rejected. Identifier normalisation, IDF weighting and Hungarian assignment need no embeddings and should be tried first. |

---

## 4. Known-wrong things not yet fixed

| issue | why it matters |
|---|---|
| **The conformance harness bypasses the product.** `run_provider_conformance.py` calls the gateway directly; `SynthesisEngine.synthesize()` runs four steps and the harness runs one. The next D10 measurement runs through the product pipeline (`build_graph`). | Every existing D10 number describes a bare model with a good prompt, not this product. |
| **`test_conformance_sends_the_prompt.py` is too narrow.** It asserts an argument at a call site; the call site itself is not the product's entry point. | The guard written to stop this class of error did not stop the next instance of it. |
| ~~**Our thresholds were never calibrated.**~~ | **Resolved 2026-09-28** (decision 4): the gate is retired; a new one is set only against a cited baseline. |
| **`aml-financial-crime` produces substantive errors.** +1.1 findings per entity on both models, including `CYCLIC_FK` and unmarked `PII_EXPOSURE`. | Unmarked PII in an AML schema is the most expensive thing this product can get wrong. |
| ~~**Three pre-existing lint errors** in `backend/scripts/refresh_dbt_packages.py`.~~ | **Resolved:** Ruff runs over the whole backend as a required check, green on `main` (run 36519786048). |
| **The repair pass never fires.** Across 48 draws, zero of its six target codes occurred. | It addresses failures this model does not make. |
| **`PII_EXPOSURE` is unaddressed and recurring.** 18 of 48 draws, 10 of 10 on AML. | A **flagging** pass that surfaces suspected PII for a human to confirm is not ruled out by the argument that classification is the user's decision. |
| **`agg_time_column` is discarded on nearly every fact table.** The model points it at an INTEGER surrogate date key; the schema requires a date/time type. | The semantic-layer export loses its time dimension. |
| **The reference-free instrument is severity-blind.** `findings_per_entity` weights a missing description equal to unmarked PII. | The same defect as the raw-count problem, one level up. |
| ~~**`EntitySchema.entity_type` defaults to the enum member, not its value.** A model whose entities omit the field is persisted as `"EntityType.TABLE"` and fails to reload.~~ | **Resolved in Sprint 8 Step 3** (PR #19): the default is validated into its value, the repository stores enum values, and migration 0025 repairs rows stored as enum names and lists each (`test_a_provider_response_without_entity_type_saves_and_reopens`). |
| **`users.email` has a redundant index.** Migration 0002 created both `uq_users_email` and a plain `ix_users_email`. | Harmless but wasteful; removing it needs a new migration. |
| ~~**The migration diff can report a rename that did not happen.** `POST /model/diff` paired columns by `stable_id` before name, but each saved model numbers its columns from 1, so two separately saved models of one table shared ids on different columns.~~ | **Resolved in Sprint 8 Step 6:** columns are paired by internal id only between versions of the same model and by name otherwise; an uncertain rename is a removal plus an addition, and the migration and the diff panel say what data each drop destroys (`test_the_diff_endpoint_never_renames_across_separately_saved_models`). |
| **Snowflake import is not certified.** Its only fixture is written from Snowflake's `GET_DDL` documentation, and it fails by name on a HYBRID TABLE; while that stands, a test keeps Snowflake import uncertified on every surface (`test_nothing_calls_snowflake_import_certified_while_its_fixture_is_documentation_derived`). | A client on Snowflake gets an import that is tested against documentation, not against the tool's real output. A genuine export is needed. |
| **Conversion findings are not shown on the canvas.** Migration 0025 lists, per model, what it could not convert exactly, and the API returns it with the model (`conversion_findings`); the canvas does not display it. | An owner upgrading from v1.11.x must read it from the API or the database (the v1.12.0 notes give the query). |
| **A rollback to v1.11.1 loses this release's data.** The downgrade is tested (`test_rollback.py`), and what it deletes is listed in the v1.12.0 notes: composite keys beyond the first pair, multi-column constraints, dictionary fields and every field status. | Stated so a rollback is a decision taken knowing the cost, after a backup. |
| **Three computed columns are not exported.** A PostgreSQL DDL export writes a SQL Server computed column as a generated column where its expression translates. Seven of AdventureWorks' ten are written that way (`test_generated_columns`, `test_generated_columns_on_postgres`), each labelled as stored in the target. The other three are named export gaps that quote their expressions: two call the `hierarchyid` method `GetLevel()`, and one calls a user function (`dbo.ufnLeadingZeros`) that the model does not hold. Other targets name every computed column as a gap. | Those three columns' definitions are not in the export, and a column that SQL Server computes on read is stored in PostgreSQL. |

---

## 5. Never run

- **The local half of D10.** No accuracy evidence of any kind for local
  inference.
- **Relationship normalisation, measured.** Whether it moves relationship F1 is
  still unknown.
- ~~**The whole backend suite against PostgreSQL.** CI runs the full suite on
  SQLite; only the migration and ledger modules run against a real PostgreSQL.~~
  **Struck 2026-09-29:** the required Backend Pytest (Postgres) job runs the whole
  suite on a real PostgreSQL (`tests/_test_db.py`; `test_test_database.py` fails
  on a module that builds its own SQLite engine). On `main` at `4ea57f7`, run
  36644605175: 1,573 passed, 73 skipped, 24 xfailed.

Struck on 2026-09-03, recorded rather than deleted:

- ~~The repair pass against a real provider.~~ Run — 28 pipeline draws, and it
  never fired.
- ~~A size-versus-domain experiment.~~ Run — 48 draws. Size drives finding
  *volume*, the domain drives *severity*. `BUILD_EVIDENCE_REVIEW.md` §12.

---

## 6. Unvalidated assumptions (the uncertainty register)

- **2026-09-28: Sprint 9's D10 re-measure must pin the linter version.** D10's
  instrument is the product's own linter, and its code set changed from 13 to 15
  in Sprint 7 (`INVALID_DATA_TYPE` and `INVALID_DEFAULT`, both errors). The run
  records the linter's code set and version beside its numbers. Not critical:
  nothing is claimed from D10 (decision 4).
- **H2 is load-bearing and rests on one engineer's reading.** The claim that
  `saas-subscription`'s 0.000 is a good model badly scored has never been checked
  by anyone who did not build this. The negative-control suite does **not** test
  it. If that reading is wrong, several conclusions in `BUILD_EVIDENCE_REVIEW.md`
  go with it.
- **No benchmark exists** for dimensional, Data Vault or OBT model generation;
  no AML data-modelling evidence of any kind; no validated result on grounding
  in a financial reference ontology. Confirmed by three literature reviews.
- The reviews hit their search budget and worked by direct fetch, so non-arXiv
  venues — OAEI in particular — are thinner than ideal.

---

## 7. What to do next

Priorities are set sprint by sprint. The 2026-09-03 ordering, which put the D10
measurement work first, is superseded by decision 4: generated models carry no
quality claim, and the D10 re-measure is planned through the product pipeline
with the linter version pinned. The judgement calls in §3 and the defects in
§2 and §4 remain the backlog they came from.
