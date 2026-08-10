# ModelBox AI — v1.5.0 Release Notes (draft)

**Tag:** `v1.5.0` (unreleased)  ·  **Cut from:** `main`  ·  **CI:** green

Builds on [v1.4.0](RELEASE_NOTES_v1.4.0.md). Headline feature: **programmatic API
key management** for CI/CD pipelines and agents. Further Step 2 work (docs & UI
polish) is appended here as it lands.

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
