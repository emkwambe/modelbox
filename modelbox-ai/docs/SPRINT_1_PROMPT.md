# Sprint 1 — Credibility and Gates

**Hand this file to Claude Code.** Branch from `main` as `sprint/1-credibility-gates`.
Reference: `docs/PROJECT_STATE_REPORT.md` §9 (finding IDs), Enhancement Blueprint §2 and §7.

**Sprint premise:** fix almost no product defects. Make them visible, permanent, and
impossible to reintroduce, and stop the documentation asserting things that are false.
Every exporter repair is explicitly out of scope and belongs to Sprint 3.

---

## Task 1 — Artifact fidelity harness (the centrepiece)

Create `backend/tests/test_artifact_fidelity.py`. Parameterise across all five gold
graphs in the Requirements Library. For each exporter, generate output and verify it with
its **real toolchain**, not string assertions:

| Exporter | Verification |
|---|---|
| DDL | `sqlglot` re-parse per dialect, plus deployability assertions per dialect |
| dbt | `dbt parse` in a temporary project |
| MetricFlow | `dbt parse` with semantic models present |
| Cube.js | JS parse; assert no measure aggregates a foreign key |
| ODCS | shape assertions; assert `apiVersion` matches the current spec line |
| Avro | `fastavro.parse_schema` |
| Protobuf | `protoc` compile, plus a tag-stability test that inserts a column and asserts no existing tag moves |
| Seed | generated rows validated against the same model's exported contract |

Mark every currently-failing case `@pytest.mark.xfail(reason="<FINDING-ID>: <summary>")`.
Do **not** fix any of them in this sprint. The xfail inventory is the deliverable — it is
how Sprint 3's completion becomes measurable.

Verification toolchain lives in `backend/requirements-dev.txt`, installed into a separate
environment from the app requirements. Installing dbt alongside the app deps downgrades
`protobuf`, `pathspec`, and `mypy` — keep them apart. Locally this is
`backend/.venv-tools`; in CI it is a separate step.

Use context7 to confirm current spec versions where a finding depends on one — ODCS under
Bitol, MetricFlow's required semantic-model keys, dbt constraint support per adapter.
Cite the source in a comment beside the assertion.

## Task 2 — CI (B2)

Create `.github/workflows/ci.yml`, triggered on push and PR:

- backend `pytest` (app venv)
- artifact fidelity harness (tools venv)
- `tsc --noEmit`
- `next build`
- alembic-head check — one head, no divergence
- version-stamp consistency check (Task 5)

Create `.github/workflows/release.yml` implementing the GHCR release flow already
documented at `README.md:112-124`. Pin Python to 3.11 to match the verified environment.

## Task 3 — Dependency reproducibility (H8)

Generate `backend/requirements.lock` from a clean install of `requirements.txt`. Switch
`docker/Dockerfile.backend` to install from the lock. Confirm the resolved set matches
the audit's Appendix A. Keep `requirements.txt` as the declared floor and the lock as the
built truth.

## Task 4 — Make the masking claim honest (B3)

**Decision taken:** masking is retired, not implemented. Rationale in Blueprint §3 (Q2) —
tokenising identifiers while sending the source PRD verbatim leaks the same semantics.
The governance story becomes air-gap plus egress ledger plus BYO endpoint (Sprint 5).

- Fail startup with a clear error when `MASK_METADATA_IN_PROMPTS=true`, stating that
  masking is unimplemented and pointing to air-gapped mode.
- Delete the claim from `README.md:106` and `model_router.yaml:20-21`.
- Remove or clearly mark the `_maybe_mask` stub so it cannot read as functional.
- Add `logging.dictConfig` at app startup so the existing egress `logger.info` at
  `llm_gateway.py:189` actually emits. Verify empirically that a real call produces a log
  line — the audit confirmed it currently does not, because the root logger sits at
  WARNING.

## Task 5 — Version reconciliation (M5)

Single source of truth for version. Reconcile `frontend/package.json` (1.2.0), `/health`,
compose image tags (v1.3.0), and release notes (v1.5.0). Add the CI check that fails on
divergence.

## Task 6 — Documentation reconciliation (M10)

Working from §2 and §8 of the audit, remove or correct every claim the code does not
keep: the CI assertions in README/ROADMAP/release notes (true after Task 2 — update
rather than delete), the `hvac` dependency, DuckDB introspection, the
`topological_order`-orders-DDL claim, the six shipped features listed as gaps, and the
"governance engine" masking language.

Move the four unimplemented research documents into `docs/research/`, each with a
`Status: research input, not implemented` header:
`Data_Engineering_Stakeholder_Cloud_Breakdown.md`, `Data_Quality_Engineering_Breakdown.md`,
`ModelBox_AI_Brand_Design_System.md`, `ModelBox_AI_Marketing_Content_Plan.md`.
The brand and marketing documents are live inputs for Phase II but are not implemented
today, so they must not read as shipped capability.

## Task 7 — Seed the Proof Log

Create `docs/marketing/PROOF_LOG.md` using the entry format in Blueprint §6. Seed with
what this sprint makes true: CI exists and gates merges; the dependency set is
reproducible; artifact fidelity is verified against real toolchains on every push.

---

## Definition of Done

1. CI green on the branch and required for merge into `main`.
2. `pytest` reports a documented xfail count, every xfail carrying a finding ID.
3. Re-reading §2 of the audit against the updated docs surfaces no remaining false claim.
4. A fresh `docker build` resolves to the versions in Appendix A.
5. Startup fails loudly when masking is enabled; a real LLM call produces a log line.
6. Version consistent across all four locations; CI check enforces it.
7. `docs/marketing/PROOF_LOG.md` exists with its first entries.
8. Appliance verified: `docker compose -f docker/docker-compose.appliance.yml up -d`
   plus the smoke path.

## Constraints

- Windows PowerShell, absolute paths, BOM-free UTF-8 writes.
- `backend/.venv` runs the app and pytest. `backend/.venv-tools` runs the fidelity
  toolchain. Never install one into the other.
- No provider API keys. The fidelity harness must run entirely offline.
- Do not fix exporter defects. If a fix is one line and obvious, still do not — record it
  as an xfail and note it in the sprint retro for Sprint 3.
- Report anything found that the audit missed; do not silently absorb it.
