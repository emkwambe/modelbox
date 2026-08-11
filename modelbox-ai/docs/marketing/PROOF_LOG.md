# ModelBox AI — Proof Log

**Purpose:** every public claim traces to a named passing test. Marketing copy is
assembled from this file, not written from memory.

**Rule (Blueprint §6, DoD 6):** a sprint appends an entry only when it makes a
claim *demonstrably* true. Entries carry an expiry condition, so a regression
invalidates the copy rather than silently making it false. No claim reaches a
public surface without a `PL-` identifier behind it (register **E2**, **G3**).

**Verifying an entry yourself:**

```bash
cd backend
MODELBOX_FIDELITY_STRICT=1 .venv-tools/Scripts/python -m pytest tests/test_artifact_fidelity.py -v
```

Entries are append-only. When one expires, mark it **EXPIRED** with the date and
reason; do not delete it — the history is the argument.

---

## PL-001 — Certified SQL dialects are certified by two independent grammars

**Claim:** "The four SQL dialects we certify — PostgreSQL, Snowflake, Redshift,
DuckDB — are verified against real dialect grammars on every push, not against
our own parser."

**Evidence:** `test_artifact_fidelity.py::test_ddl_dialect_grammar`, 20/20
certified cases (4 dialects × 5 gold graphs), zero unparsable segments under
`sqlfluff` 4.3.0. The same test marks `bigquery`, `databricks` and `clickhouse`
`@preview`: each rejects the emitted `CREATE TABLE` constraint body, which is why
they are labelled rather than advertised.

**Why it is stronger than it looks:** the certified/preview boundary was
originally an architect's judgement call about which dialects to support.
`sqlfluff` — a second parser with per-dialect grammars, independent of the
`sqlglot` used to *generate* the DDL — reproduces that boundary exactly. The
product line is drawn where the evidence falls, not where convenience put it.

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** on any change to `ExporterService.generate_ddl`, `_entity_create_table`,
the `sqlglot` or `sqlfluff` pin in `requirements.lock`, or the certified-dialect list.
**Usable in:** landing page, export UI dialect labels, enterprise technical review,
"why we advertise four dialects and not seven" post.

---

## PL-002 — Generated DDL executes on a real engine, not just a parser

**Claim:** "Our generated schemas don't just parse — we execute them. Every
release runs all five reference models' DDL against a live DuckDB instance and
asserts the tables that come back are the tables you modelled."

**Evidence:** `test_artifact_fidelity.py::test_ddl_executes_on_duckdb`, 5/5 gold
graphs. Each emits DDL in the `duckdb` dialect, executes it in an in-memory
database, then queries `information_schema.tables` and asserts the created set
equals the model's entity set.

**Why it is stronger than it looks:** every other artifact claim in this file
rests on a *parser* accepting output. This one rests on a database engine
accepting it and reporting back what it built. DuckDB is the only certified
dialect whose engine is embeddable, which is what makes the check possible in
CI with no infrastructure.

**Honest limit:** it proves deployability for DuckDB. PostgreSQL, Snowflake and
Redshift are certified by two grammars (PL-001), not by execution. Do not
generalise this claim to "executes on every certified warehouse."

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** on any change to `generate_ddl`/`_entity_create_table`, the `duckdb`
pin in `requirements.lock`, or the gold graph set.
**Usable in:** landing page hero, technical blog, enterprise security review.

---

## PL-003 — `main` is protected and cannot be merged into on a red build

**Claim:** "Nothing reaches our main branch without six independent checks
passing: backend tests, the artifact fidelity harness, strict TypeScript, a
production build, lint, and a single-migration-head check — plus a version
consistency gate."

**Evidence:** GitHub branch protection on `emkwambe/modelbox@main` with named
required status checks and `strict: true` (branches must be up to date before
merge). Verify with:

```bash
gh api repos/emkwambe/modelbox/branches/main/protection \
  --jq '.required_status_checks | {strict, contexts}'
```

Workflow: `.github/workflows/ci.yml`. Runs on every branch and every pull
request as of v1.6.0; it previously ran only on `main` and PRs into `main`, so
feature branches were unguarded until a PR opened.

**Why it is stronger than it looks:** CI existed before v1.6.0 and had run 59
times, green. It gated `pytest`, `tsc --noEmit` and `next build` — and the
backend suite asserted exporter output by *substring*, so a semantic-layer
exporter that `dbt parse` rejects on 5/5 models passed every one of those 59
runs. The claim worth making is not "we have CI"; it is "our CI checks each
artifact against the tool that consumes it," and the fidelity job is what makes
that true.

**Honest limit:** `enforce_admins` is off and no reviewer approval is required,
so a repository administrator can still bypass. Suitable for "changes are gated,"
not for "changes are impossible to force."

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** if branch protection is relaxed, a required check is removed from the
context list, or the fidelity job stops running with `MODELBOX_FIDELITY_STRICT=1`.
**Usable in:** enterprise procurement questionnaire, engineering-practices page,
"the audit is the test suite" post.

---

## PL-004 — A tagged release publishes an image that pulls and runs clean

**Claim:** "Tag a release and you get container images on GHCR that start,
migrate, and serve on a host that did not build them."

**Evidence:** tag `v1.6.0` triggered `.github/workflows/release.yml`, which built
and pushed `ghcr.io/emkwambe/modelbox-backend:1.6.0` and
`…-frontend:1.6.0`. Neither image existed locally — `docker rmi` reported *No
such image* before the pull, so the artifact tested is the runner's, not a local
build. Pulled, started against the appliance Postgres, and observed:

- Alembic ran to head inside the container.
- The healthcheck went healthy in ~10s.
- `/health` returned `{"status":"ok", … "version":"1.6.0"}` — the same value
  stamped in `backend/app/__version__.py`, `package.json` and the compose tags.
- The retired masking flag still fails startup *in the published image*, exiting
  1 with the error naming `AIRGAPPED=true`.

**Honest limit:** the *images* were never built on this host, but the *host* has
built the project. This proves the published artifact is self-sufficient — it
does not prove a first-run experience on a machine with no toolchain, no build
cache and no prior Docker layers. Register **A9** is satisfied; the stronger
unassisted-install claim is **G1**, Sprint 5.

**Verified:** 2026-08-11 · **Sprint:** 1 · **Version:** 1.6.0
**Expires:** on any change to `docker/Dockerfile.backend`, `release.yml`, or the
container start command.
**Usable in:** install documentation, enterprise evaluation guide, "how we ship"
post.

---

## Claims explicitly NOT yet provable

Recorded so nobody reaches for them early. Each becomes an entry when its test
passes.

| Prospective claim | Blocked on | Sprint |
| :-- | :-- | :-- |
| "Semantic layer exports compile in dbt" | B1 — 24 xfails; MetricFlow parses on 0/5 graphs | 3 |
| "Data contracts are wire-stable" | H6 — Protobuf tags shift when a column is inserted | 3 |
| "Our contracts are valid ODCS" | H2 — stamped v0.9.3, missing required v3.1.0 fields | 3 |
| "Generated test data satisfies the generated contract" | H1 — seed ignores declared lengths and quality rules | 4 |
| "We can show you everything that left your network" | B3 — egress ledger does not exist | 5 |
| "Governed contracts and semantic layers, not just schemas" | B1 + H2 together | 3 |
