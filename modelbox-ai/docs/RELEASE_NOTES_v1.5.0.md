# ModelBox AI — v1.5.0 Release Notes

**Tag:** `v1.5.0`  ·  **Cut from:** `main`  ·  **CI:** green

> **Corrected 2026-08-11 (Sprint 1).** This file previously read "(draft)" and
> "(unreleased)" while also asserting CI status, and was superseded before it was
> ever tagged. It is now stamped at its actual state.
>
> The "CI: green" claim was accurate — `.github/workflows/ci.yml` had run 59
> times, green on every `main` push. What it did *not* say is what CI gated at
> the time: `pytest`, `tsc --noEmit` and `next build`, with the backend suite
> asserting exporter output by substring. That is how the defects catalogued in
> `PROJECT_STATE_REPORT.md` §4 reached `main` behind a green run. v1.6.0 adds
> the artifact-fidelity harness, `next lint`, an alembic-head check and a
> version-consistency check, and makes all six required for merge.

Builds on [v1.4.0](RELEASE_NOTES_v1.4.0.md). Headline feature: **programmatic API
key management** for CI/CD pipelines and agents.

---

## Highlights

- **API Key Management** — mint, list, and revoke workspace API keys; authenticate
  requests with an `X-API-Key` header (no interactive login).

---

## API Key Management

Programmatic access for CI/CD and agents, managed at `/settings/api-keys`.

- **Model** — `api_keys` table (migration `0009`), workspace- and creating-user-
  scoped. Only the **SHA-256 hash** and a display **prefix** (`mb_live_XXXX`) are
  stored; the plaintext secret is shown **once** at creation and is unrecoverable.
- **Endpoints:**
  - `POST /api/v1/auth/api-keys` (ADMIN+) — mint a key; returns the secret once.
  - `GET /api/v1/auth/api-keys` — list key metadata (never the secret/hash).
  - `DELETE /api/v1/auth/api-keys/{id}` (ADMIN+) — revoke.
- **Authentication** — `get_current_user` accepts an `X-API-Key` header as an
  alternative to the Bearer JWT. A key authenticates **as its creating user**, so
  it inherits that user's workspace memberships and RBAC. Expired keys are
  rejected; `last_used_at` is stamped on use.
- **UI** — `/settings/api-keys`: generate with a one-time secret reveal + copy,
  and an active-keys table with revoke.

**Verified live:** create → `X-API-Key` auth on real endpoints (no JWT) → list
(no secret leak) → revoke → `401`.

---

## Step 2 (in progress)

- **Phase A — UI polish & enterprise landing page** (canvas density, header/nav,
  landing positioning): _to be documented as it lands._
- **Phase B — User guide & API documentation**: _pending._

---

## Publishing

`release.yml` builds and pushes backend + frontend images to GHCR on the `v*`
tag, tagged `1.5.0`, `1.5`, and `latest`:

```bash
git tag v1.5.0
git push origin v1.5.0
```
