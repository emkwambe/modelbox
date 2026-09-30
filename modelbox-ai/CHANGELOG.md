# Changelog

One entry per version. Each release's full notes, breaking changes and upgrade
steps are in `docs/RELEASE_NOTES_v<version>.md`; this file is the index.

## Unreleased (for v1.12.0)

Recorded as changes land; the release notes are written from this list. Draft
notes: [`docs/RELEASE_NOTES_v1.12.0-draft.md`](docs/RELEASE_NOTES_v1.12.0-draft.md).
Sprint 8, pull requests #14 to #24; migrations 0023 to 0027, run by the migrate
service on start.

- **DDL import:** an exported DDL file becomes a model at `/import`, read on the appliance.
  Oracle and SQL Server are certified on genuine exports and PostgreSQL on a genuine
  `pg_dump`; Snowflake is documentation-derived and not certified. Every import is
  reconciled against the file by an independent counter, and saved reconciled or
  unreconciled with its report.
- **Keys and constraints:** composite primary and foreign keys and multi-column UNIQUE and
  CHECK constraints are held in the model and stated in DDL export, with what a dialect
  cannot express named as an export gap; exported PostgreSQL DDL is applied to a real
  PostgreSQL in CI. Saved models open at `/canvas/<id>` and are listed at `/models`.
- **Repair:** models stored with an enumeration's name instead of its value, which could
  not be reopened in v1.11.x, are repaired by migration 0025 and listed.
- **Data dictionary:** Markdown, HTML, JSON and CSV; person-supplied fields, a
  classification scale per workspace, and a status per field. A field is verified only
  under stated conditions, and lapses to pending when its value changes. Dictionary
  review with a Verify control on the canvas.
- **Drift report:** a saved model against a DDL export of the deployed schema, classified
  by nineteen published rules, in the API and on the canvas.
- **Migration diff:** the migration diff no longer pairs columns across separately saved models by internal id.
  Every statement that drops data says so, in the SQL and in the diff panel.
- **Semantic export:** MetricFlow composite keys, and keys it cannot join, are named export gaps.
- **Members:** workspace owners and admins add members, change roles and remove members,
  through the API and `/settings/members`.
- **Rollback:** a tested downgrade to v1.11.1, with what it loses listed in the notes.

## v1.11.1

Tagged 2026-09-29 (UTC) at `e8d9ac1` on `main` (pull request #12), and
published by the gated release workflow (run 36516574170) as
`ghcr.io/emkwambe/modelbox-backend` and `modelbox-frontend`, `1.11.1`. Full
notes: [`docs/RELEASE_NOTES_v1.11.1.md`](docs/RELEASE_NOTES_v1.11.1.md).
Supersedes v1.11.0; upgrade by pulling the new images, with no migration and no
configuration change.

- **Transactions:** every API request that writes commits, or fails, before its response is
  sent, so a success always describes committed work and a failed commit is a
  500. The JSONL audit exports read through a read-only session that stays
  open while they stream.
- **Black-box reports:** the acceptance suite redacts every credential it handles from its
  failure reports, enforced by a test, and checks read-your-writes against the
  running appliance fifty times over.
- **Frontend image build:** package install scripts run after every package is
  installed (`npm ci --ignore-scripts && npm rebuild`); the installed set is
  unchanged.

## v1.11.0

**Superseded by v1.11.1.** Tagged 2026-09-29 (UTC) at `d5822f1` on `main`,
published by the gated release workflow (run 36511971512); the tag and its
images remain. The merge that carries the work is `d81f569` (pull request #9).
Full notes: [`docs/RELEASE_NOTES_v1.11.0.md`](docs/RELEASE_NOTES_v1.11.0.md).

Secure by default, and proven against the running appliance. It carries Sprints
5, 6, 6.5 and 7, the first merge to `main` since v1.9.0.

- **Installation:** the appliance starts only with generated secrets, creates its first account
  with `create-owner` (or `designate-appliance-owner` after an upgrade), and
  offers no self-registration in production.
- **Network:** one published port, the web UI's; the API is served at `/api` on that port.
- **Access:** every route declares its minimum role (VIEWER, MEMBER, APPROVER, ADMIN,
  OWNER). API keys act within their own workspace, capped at a role no higher
  than their creator's.
- **Audit:** sign-ins and SCIM events reach an appliance owner's JSONL export, and
  `/health` reports any failed audit write.
- **Ledgers:** the egress ledger and audit trail are append-only, and the
  application uses a least-privilege database role.
- **Gateway:** one ledger row per provider request, failures classified by cause and
  recorded as structured fields, never the model's output.
- **Enterprise access (Sprint 6.5):** OIDC verification with key rotation, SCIM provisioning and
  de-provisioning, a tested restore.
- **Governance (Sprint 5):** per-task residency pins, typed failover, and
  air-gapped mode tested with every provider key present.
- **CI:** a black-box acceptance suite runs against the containers; Ruff, mypy
  and a leak guard are required; a release is published only from a green
  `main`.

**Breaking:** the API's port, a fourth generated secret, registration closed in
production, existing API keys reduced to VIEWER, the `/health` body, and the
ledger's failure text. See the release notes' upgrade steps before upgrading.

## v1.10.0

Never tagged; superseded by v1.11.0, which ships its changes.
[`docs/RELEASE_NOTES_v1.10.0.md`](docs/RELEASE_NOTES_v1.10.0.md)

## Earlier versions

| Version | Notes |
| :-- | :-- |
| v1.9.0 | [`docs/RELEASE_NOTES_v1.9.0.md`](docs/RELEASE_NOTES_v1.9.0.md) |
| v1.8.0 | [`docs/RELEASE_NOTES_v1.8.0.md`](docs/RELEASE_NOTES_v1.8.0.md) |
| v1.7.0 | [`docs/RELEASE_NOTES_v1.7.0.md`](docs/RELEASE_NOTES_v1.7.0.md) |
| v1.6.0 | [`docs/RELEASE_NOTES_v1.6.0.md`](docs/RELEASE_NOTES_v1.6.0.md) |
| v1.5.0 | [`docs/RELEASE_NOTES_v1.5.0.md`](docs/RELEASE_NOTES_v1.5.0.md) |
| v1.4.0 | [`docs/RELEASE_NOTES_v1.4.0.md`](docs/RELEASE_NOTES_v1.4.0.md) |
| v1.3.0 | [`docs/RELEASE_NOTES_v1.3.0.md`](docs/RELEASE_NOTES_v1.3.0.md) |
