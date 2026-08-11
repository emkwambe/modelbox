# Sprint 4 — scope carried forward

**Branch from `main` at `v1.8.0`.** Written at the end of Sprint 3 so nothing
below needs re-deriving. `docs/sprint-3-progress.md` has the preceding state.

**Baseline:** 3 non-preview xfails, 18 preview. 367 app tests pass. Six CI jobs
green including the populated-database migration gate.

---

## The framing that should drive the sprint

**H1 is not two isolated fixes.** It is *teach the seed generator to read the IR
Sprint 2 built.* `SyntheticSeedGenerator._value` reads only `col.name` and
`col.data_type` — it has no constraint awareness at all. `min_value`,
`max_value`, `regex_pattern`, declared `VARCHAR(n)` length, `is_nullable`,
`is_unique`, `check_expression` and `default_value` are all present in the IR
and all ignored.

That matters because of what it blocks. **Register B13 — `dbt build` succeeds on
generated seed data — is the last claim standing between "our exports parse" and
"our exports run."** Today the product emits seed rows that fail the dbt tests
exported from the same model: `score = 6301.38` against a declared
`max_value: 5.0`, `'icd10_code_1'` (12 chars) into a `VARCHAR(10)`. Shipping
both artifacts together fails on the product's own fixtures.

`dbt parse` proves a project resolves. `dbt build` proves it runs. That is the
whole distance left.

## The three open defects

| ID | Defect | Test |
| :-- | :-- | :-- |
| **H1** | Seed ignores declared column lengths | `test_seed_respects_declared_length[healthcare-ehr]` |
| **H1** | Seed ignores declared quality rules | `test_seed_respects_quality_rules` |
| **H10** | ODCS quality entries use a `rule` key that does not exist in v3.1.0 | `test_odcs_quality_entries_use_v3_vocabulary` |

H10 is small and well-specified: a v3.1.0 property-level entry is
`{id, metric, mustBe*, arguments, unit, description}` with an optional
`type: library|sql|custom`. Verified via context7 on 2026-08-11. Re-verify
before writing — that document has been the source of two corrections already
(C3, then C7-a).

## Carried forward from earlier sprints

| ID | Item | Notes |
| :-- | :-- | :-- |
| **C4** | A renamed column reports as a rename, not drop-plus-add | Unblocked by `stable_id`; the diff engine does not read it yet |
| **C5** | Removing a foreign key produces a breaking change | Currently yields zero — the diff engine ignores relationships entirely |
| **M1** | `suggested_metrics` never round-trips, so `DiffEngine._semantic_breaks`' formula branch is unreachable through the API | Persist it, or delete the dead branch |
| **M2** | Diff covers columns only — no PK, FK, or governance changes | Same code path as C4/C5 |
| **D9** | JWT validates neither `aud` nor `iss` | An RS256 token minted for another audience is accepted |

C4, C5 and M2 are one piece of work in `diff_engine.py`, not three.

**M12 landed** in Sprint 3 —
`test_export_ui_offers_exactly_the_dialects_the_backend_supports` compares
`ExportPanel.tsx` against the harness and `_SQLGLOT_DIALECTS`. Nothing carried.

---

## Posture, not process

Six of the register's nine verification standards were discovered by something
going wrong rather than specified in advance. One of them invalidated a
criterion the register itself named — B6's proof of Protobuf wire stability
certified a defective implementation, and survived only because the sprint
asked for the mutant a competent implementer would actually write.

The working assumption should therefore be that **the register is wrong in ways
nobody has found yet**, and each discovery is evidence about the *category*
rather than the instance. Concretely, before trusting any green test added this
sprint:

1. Does a fixture exist that exercises the feature at all? *(standard 8)*
2. Would the plausible wrong implementation fail it? *(standard 1)*
3. Is the assertion the property, or a consequence the wrong implementation also
   satisfies? *(standard 9)*
4. Does the path under test repair its own input in transit? *(standard 5)*

H1 is exposed to (1) and (2) in particular: no gold graph declares a quality
rule, so everything about quality-rule handling is reachable only through
`backend/tests/fixtures/synthetic/quality_rules.json`.

## Operational notes

- **"Check the downstream effect" is the rule.** "Be careful with shell
  chaining" never was. A masked exit code has now silently swallowed a test run,
  a batch edit and a `git push` — in three separate venues, each caught by
  noticing the effect was missing rather than by care. Verify the effect, not
  the command.
- **No source edits through bash heredocs, and no regex spanning multiple
  constructs.** Hard constraint in `CLAUDE.md`. Four incidents in Sprint 3, one
  of which deleted 161 lines including two test sections.
- **A cold appliance rebuild now runs past ten minutes.** The frontend image is
  the slow part, and the UI service may need `docker compose up -d modelbox-ui`
  separately after a timeout. Budget for it rather than being surprised under
  time pressure.
- `backend/.venv` for the app and pytest; `backend/.venv-tools` for the fidelity
  toolchain. Never install one into the other.

## Invariants at every commit boundary

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m "not preview" -q   # falls only
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -m preview -q         # 18, always
.venv/Scripts/python -m pytest -q
```

Every fix removes its `xfail` marker; `strict=True` turns a fix without marker
removal into a red XPASS. Preview dialects and LookML stay labelled, not
repaired — the preview count holding at 18 is the evidence that scope held, and
it only means something if it is never broken for convenience.
