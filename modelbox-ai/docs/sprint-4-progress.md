# Sprint 4 — progress and handoff state

**Branch:** `sprint/4-data-security`, cut from `main` at `v1.8.0`.
**Scope:** `docs/sprint-4-scope.md`. **Register:** §B, §C, §D.

**Target was 7 → 0 non-preview. It reached 0.** Thirteen findings closed
against a scope of seven; five were discovered mid-sprint and did not exist
when the target was set.

---

## Status

| Finding | What it was | Commit |
| :-- | :-- | :-- |
| **H1** | Seed generator ignored every declared constraint | `H1: the seed generator reads the IR` |
| **B13** | `dbt build` never ran; only `dbt parse` | `B13: dbt build runs the product's exports` |
| **H11** | dbt `accepted_values` contradicted the model's `CHECK` | same |
| **H12** | `packages.yml` malformed; dbt refused to load the project | same |
| **M14** | dbt_expectations args not nested under `arguments:` | same |
| **M15** | `calogica/dbt_expectations` redirected on dbt Hub | same |
| **C4** | A rename emitted DROP + ADD, destroying data | `C4, C5, M2: the diff engine reads identity` |
| **C5** | Removing a foreign key reported nothing | same |
| **M2** | A changed primary key reported nothing | same |
| **H10** | ODCS quality entries used a `rule` key that does not exist | `H10, M13: the ODCS contract says what the model declared` |
| **M13** | `default_value` and `check_expression` reached no emitter | same |
| **D9** | JWT validated neither `aud` nor `iss` | `D9: a signature is not an authorisation` |
| **M1** | `suggested_metrics` never round-tripped | `M1: suggested metrics survive a save` |

Invariants at close: **0 non-preview xfail** (229 passed), **18 preview**
(unmoved every commit boundary), app suite green, four migration tests green.

---

## The three results that outlast the burn-down

### 1. Cross-artifact contradiction (standard 10)

H11 shipped in v1.8.0 with every gate green. The dbt contract asserted
`ACTIVE/INACTIVE/PENDING`; the seed generator, reading the same model's
`CHECK (status IN ('PENDING','DONE'))` correctly, produced `PENDING` and
`DONE`. **Each artifact was valid against its own consumer.** Every gate in
the suite asked a single-artifact question, and no single-artifact question can
see two outputs disagreeing.

`dbt build` is the first gate where two artifacts meet — the product's seed
rows loaded into DuckDB, the product's models built against them, the product's
tests run over the result. It found this on its first execution.

**Open for Sprint 5:** which other artifact pairs from the same model can
contradict each other, and does any gate check? Two candidates, neither gated:
the ODCS `required` field and the DDL `NOT NULL` clause read the same
nullability through separate code paths; Protobuf optionality and Avro
union-with-null are the same shape as the `NUMERIC` disagreement Sprint 3 found
and fixed between those two emitters — which is evidence the category is
populated rather than hypothetical.

### 2. Fixture breadth must itself be asserted (standard 11)

Four defects (H11, H12, M14, M15) lived in one hole: every dbt gate was
parameterised over the five gold graphs, **no gold graph declares a quality
rule**, so no project dbt had ever been handed contained a `dbt_expectations`
test or a `packages.yml`. The structural repair is parameterising the gates
over the synthetic fixture, not fixing four instances.

`test_seed_fixtures_exercise_every_declared_rule` is the executable guard: it
enumerates the rules the suite asserts and fails when no fixture declares one.
It fails on a **fixture** regression rather than a code regression, a category
the suite previously had no member of.

### 3. Empty expectations, and guards that carry their own defect (12, 13)

Two vacuous comparisons in unrelated code, sharing only their shape: a missing
JWT `aud` claim that python-jose treated as nothing-to-compare, and
`expected = "" if revision == "head"` in the migration read-back, where
`"" in stamped` is unconditionally true.

The second is the more instructive. `_upgrade_to` was written specifically to
stop an exit code being mistaken for arrival — and mistook an exit code for
arrival, in a new disguise, on every migration test in the file. It could not
fail. That is the third remedy in this codebase to carry the defect it was
written to prevent, after the `stable_id` watermark stored on a row its own
persistence deleted and the H4 validator that never fired on an unsupplied
field.

Hence standard 13: **a guard is a claim about behaviour and needs the same
discrimination test as the code it guards.** Point it at something that must
fail and confirm it does.

---

## Ruled this sprint — do not re-litigate

- **Declared IR outranks heuristics**, product-wide, stated once in the
  `exporter_service` module docstring. Violated independently in the seed
  generator (H1) and the dbt exporter (H11), which is what made it a rule.
  Corollaries: declared constraints can conflict with each other, and
  referential integrity outranks a declared UNIQUE.
- **A numeric range is not an ODCS quality rule.** It is
  `logicalTypeOptions.minimum/maximum`. The documented `invalidValues`
  arguments are `validValues` and `pattern`; there is no argument for a numeric
  bound, and inventing one produces a document that validates and communicates
  nothing. Third correction to the ODCS reading after C3 and C7-a, and each one
  came from checking the spec against one specific emitter.
- **The dbt package cache is populated once, out of tree, never vendored.**
  `scripts/refresh_dbt_packages.py` builds it from the *exporter's own*
  `packages.yml` and fails on any deprecation — the only place the redirect
  deprecations are observable, since they fire against the registry.
  `package-lock.yml` is committed and is what the offline test asserts against.
  6.6 MB of vendored third-party SQL would buy hermeticity
  `MODELBOX_FIDELITY_STRICT` already provides.
- **The lock delta for `dbt-duckdb` was a non-event** — one line, nothing moved,
  `pip check` clean. Recorded explicitly in `requirements-dev.txt` because
  negative results decay fastest. dbt-core moving protobuf and pathspec was
  about mixing two dependency sets, not resolver volatility; there is no class.

## Watch items

- **The migration gate failed all four tests once**, immediately after the
  `_upgrade_to` edit, then passed five consecutive runs including the
  discrimination check. Not reproduced. Most likely the prior run's container
  still releasing — the same neighbourhood as the ephemeral-port bug closed in
  Sprint 2. **If it recurs in Sprint 5 it stops being a watch item.** An
  unreproducible failure in a gate matters more than one anywhere else, because
  a flaky gate is eventually ignored.
- **Two unit tests pinned pre-fix behaviour** this sprint —
  `test_quality_rules_propagate_to_exports` asserted the deprecated flat dbt
  argument shape, then the non-existent ODCS `rule` key. The fidelity harness
  asserts against the tool that consumes the artifact; these assert against a
  literal the author expected. When they disagree, the consumer wins.
- **Not this sprint:** sweep for other places the codebase trusts a library's
  default on missing input.

## Deferred

- **DDL `CHECK` clause.** M13's scope was the DEFAULT half; `check_expression`
  now reaches ODCS and dbt, but no `CHECK` constraint is emitted into the DDL.
  That is the honest remaining piece, not a gap in the register line.
- **Role-playing dimensions in MetricFlow**, carried from Sprint 3 and
  untouched: two FKs from one entity to the same parent produce two foreign
  entities with the same name. Needs separate semantic models per role.
