# ModelBox AI — v1.9.0 Release Notes

**Tag:** `v1.9.0`  ·  **Cut from:** `main`  ·  **CI:** green

**This is the release where the core claim is fully true.** Every certified
artifact parses in the toolchain that consumes it. The emitted DDL executes on a
real engine. Contracts are wire-stable across a schema change. And a generated
dbt project now **builds end to end** — the product's own seed data loaded into
a warehouse, the product's models built against it, the product's tests run over
the result, green.

v1.8.0 could say "our exports parse". This one says "our exports run", and a
test proves it on every push.

**No known defect remains outside the labelled Preview set.**

---

## What changed

### Exports that run, not just parse

`dbt parse` proves a project resolves. `dbt build` executes it. Running that for
the first time found four defects the parse gates could not see, all of them
shipped in v1.8.0 with green checks:

- The emitted `packages.yml` was malformed badly enough that **dbt refused to
  load the project at all**. Nothing caught it because no project the harness
  had ever parsed carried a `packages.yml`.
- The dbt tests the exporter emitted **contradicted the seed data the generator
  produced from the same model**. A column declaring
  `CHECK (status IN ('PENDING','DONE'))` got a test demanding
  `ACTIVE/INACTIVE/PENDING`, from a hard-coded vocabulary that outranked the
  model's own declaration.
- Generic-test arguments used a deprecated form, and the declared dependency
  named a package that dbt Hub has redirected.

The second is the one worth understanding, because it is a category rather than
a bug. **Both artifacts were valid.** The contract was valid dbt; the seed data
was valid against the model. Each satisfied its own consumer while asserting the
opposite of the other, and no check that examines one artifact at a time can
notice. Shipping them together failed on the first run.

### Generated data that satisfies its own contract

The seed generator read only column names and types. Everything the model
declared — length, range, pattern, precision and scale, uniqueness,
nullability, enumerated checks — was ignored, so the product emitted rows that
failed the tests it exported alongside them: `6332.15` into a
`NUMERIC(5,2)` bounded `0.0–5.0`, a twelve-character value into a `VARCHAR(10)`.

Generated data now honours every declared constraint. The governing rule is
stated once for the whole product: **anything the model declares outranks any
heuristic guess.** A guess that overrides a contract is worse than no guess,
because it looks deliberate.

Where two declared constraints genuinely conflict — a pattern that cannot fit
its column's declared length — the generator refuses to silently satisfy
neither, and the model linter reports it as `PATTERN_EXCEEDS_LENGTH`.

### Migrations that report what actually changed

The schema diff matched columns by name and never read relationships at all.
Three consequences, all fixed:

- **A renamed column was reported as a drop plus an add** — and running the
  emitted DDL destroyed the data. Renames are now detected by column identity,
  and the rename *replaces* the drop and add rather than accompanying them.
- **Removing a foreign key reported nothing.** The diff called the two models
  identical.
- **Changing a primary key reported nothing.**

Adding a relationship is still not a breaking change, because tightening a
guarantee breaks nothing downstream — a diff that flags every difference is a
diff people learn to ignore.

Suggested metrics now survive a save, which makes the semantic half of the diff
reachable for the first time: *this metric's formula references a column you
just dropped*.

### Contracts that say what the model declared

ODCS quality blocks used a `rule` key that appears nowhere in the standard.
Fixing it turned up a distinction worth stating: a **bound** on a column's
values is `logicalTypeOptions` (`minimum`, `maximum`, `pattern`), while a
**measured assertion** is a `quality` entry with a metric and a threshold. A
numeric range is the first, not the second, and forcing it into a quality rule
would have required inventing an argument the standard does not define —
producing a document that validates perfectly and communicates nothing.

Declared defaults now reach SQL `DEFAULT`, and an enumerated `CHECK` reaches
both the contract and the dbt tests.

### Tokens addressed to this service

JWT verification checked the signature and nothing else. A signature proves a
key holder minted the token; it does not prove the token was minted for *you*.
An identity provider signing for a dozen applications signs them all with one
key, so an access token issued to any other tenant verified here perfectly.

`aud` and `iss` are now verified. Under RS256 — tokens from an external provider,
which is exactly where the gap is exploitable — they are **mandatory**, and a
deployment without them is refused rather than served.

---

## Known open items

**Zero non-preview defects.** The expected-failure inventory outside the Preview
set is empty for the first time since the programme began.

**18 expected failures remain marked `@preview`** — the three Preview dialects
(`bigquery`, `databricks`, `clickhouse`) and the LookML emitter. These are
labelled rather than scheduled, and are not counted as debt. That count has not
moved in two releases, which is the evidence that scope held.

Inspect either with:

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 pytest tests/test_artifact_fidelity.py -m "not preview" -q
MODELBOX_FIDELITY_STRICT=1 pytest tests/test_artifact_fidelity.py -m preview -q
```

## Limits

- **`dbt build` runs against DuckDB**, in-process and offline. It proves the
  project executes and its tests pass on real data. It does not prove behaviour
  on Snowflake or BigQuery.
- **No `CHECK` constraint is emitted into the DDL.** A declared
  `check_expression` reaches the ODCS contract and the dbt tests; the SQL
  constraint clause is not yet generated.
- **The dbt package cache is populated by a setup step**, not vendored:
  `backend/scripts/refresh_dbt_packages.py`. It needs network once. The test
  run itself remains offline, and `MODELBOX_FIDELITY_STRICT` turns a missing
  cache into a hard failure rather than a skip.
- LookML has no offline parser and is structurally asserted only.
- No ODCS schema validator is installed. Conformance is asserted against the
  specification's documented constructs, read for what this emitter produces —
  a scoped check, not an audit of the standard. That reading has now been
  corrected three times.
- An administrator can still bypass the required CI checks; `enforce_admins`
  is deliberately off.

## Upgrade notes

- **Database migration `0014_add_suggested_metrics`.** Additive and nullable,
  no backfill, no destructive step. Verified against a populated database.
- **ODCS documents change shape.** Numeric ranges move from `quality` to
  `logicalTypeOptions`; quality entries now use `metric`/`mustBe` rather than
  the non-standard `rule` key. Anything parsing the old output needs updating.
- **dbt projects declare `metaplane/dbt_expectations`** rather than the
  redirected `calogica/` name, and generic-test arguments nest under
  `arguments:`. Regenerate any committed project.
- **Diff output gains statements and breaking changes it did not emit before** —
  `RENAME COLUMN`, removed foreign keys, primary-key changes. Anything
  consuming the diff programmatically should expect new entries.
- **RS256 deployments must set `JWT_AUDIENCE` and `JWT_ISSUER`** or token
  verification is refused. HS256 deployments are unaffected; pinning is opt-in
  there.
- Container image tags move to `v1.9.0`.
