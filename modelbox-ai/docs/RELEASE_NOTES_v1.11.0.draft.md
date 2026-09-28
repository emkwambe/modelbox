# ModelBox AI — v1.11.0 Release Notes (draft)

**Status: draft, unreleased.** This file is renamed to `RELEASE_NOTES_v1.11.0.md`
in the same commit that moves the version stamp to 1.11.0. Until then the
version check reads v1.10.0's notes, and this name keeps it out of that check.

v1.11.0 supersedes v1.10.0, which was never tagged.

---

## Upgrading an existing install

1. **Keep your `.env`.** Its secrets protect your existing data (see the
   breaking changes below for what the backend now refuses).
2. **Designate the appliance owner.** An upgraded install has workspace owners
   but no appliance owner, and appliance-wide audit events (sign-ins, SCIM)
   are readable only by one. After starting v1.11.0, choose one existing
   workspace OWNER:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.appliance.yml exec modelbox-backend python -m app.cli designate-appliance-owner --email you@example.com
   ```

   It refuses if an appliance owner already exists, and records
   `APPLIANCE_OWNER_DESIGNATED` in the audit trail. A new install gets its
   appliance owner from `create-owner` instead.

---

## Breaking changes

### The API is served on the UI's port, and the backend publishes no port

The appliance now publishes one port, the UI's (`UI_PORT`, default 3000). The
UI forwards `/api/*` to the backend over the compose network. Postgres, Redis
and Ollama also publish nothing to the host.

| Before | From v1.11.0 |
| :-- | :-- |
| `http://<host>:8000/api/v1/...` | `http://<host>:<UI_PORT>/api/v1/...` |
| `http://<host>:8000/health` | `http://<host>:<UI_PORT>/api/health` |
| `http://<host>:8000/docs` | Only with `docker/docker-compose.debug.yml`, on `127.0.0.1:8000` |

**What to change:** point CI/CD jobs, scripts and agents that call the API with
an `X-API-Key` at the UI port, and point health monitoring at `/api/health`.
`NEXT_PUBLIC_API_URL` is removed and has no effect.

### The appliance will not start without generated secrets

`JWT_SECRET`, `ENCRYPTION_KEY` and `POSTGRES_PASSWORD` have no defaults.
Compose refuses to start without them, and the backend refuses the values that
used to ship in this repository. Run `scripts/init-env.ps1` or
`scripts/init-env.sh` to create `.env` before the first start.

**Upgrading an existing install:** keep your current `.env`. Changing
`ENCRYPTION_KEY` makes stored connection secrets unreadable, and changing
`POSTGRES_PASSWORD` locks the appliance out of its existing database volume. If
your `.env` still holds a shipped default, the backend will now refuse it. Plan
the rotation before upgrading.

### Self-registration is off in production; create-owner makes the first account

`POST /api/v1/auth/register` returns 403 when `ENVIRONMENT=production` (as the
appliance runs) unless `MODELBOX_ALLOW_REGISTRATION=true`. The first account is
created after start-up with:

```bash
docker compose --env-file .env -f docker/docker-compose.appliance.yml exec modelbox-backend python -m app.cli create-owner --email you@example.com
```

It prompts for the password, and refuses once any owner exists.

### No development account or one-click development login

The appliance no longer creates `dev@modelbox.ai`, and the sign-in dialog no
longer offers a development login. The account is created only in development,
on request (`MODELBOX_SEED_DEV_USER=true`).

### Every route has a declared minimum role

Each API route now declares the workspace role it requires, in one table
(`backend/app/api/v1/route_policy.py`), and a test fails if any route lacks an
entry or enforces something else. Callers below a route's role now get 403:

| Role | Can |
| :-- | :-- |
| `VIEWER` | read models, jobs, connections (masked), assignments and the egress ledger; validate; export |
| `MEMBER` | also synthesize, edit or transform a graph, introspect a connection, and work on Trainer assignments |
| `APPROVER` | also record sign-off on a model |
| `ADMIN` | also create or delete connectors, manage API keys, read the audit trail, delete models |

Listings (models, connections, assignments, API keys, egress) return only the
workspaces where the caller holds the listed role; naming another workspace is
a 403. `GET /api/v1/export/status` now requires sign-in.

### API keys are scoped to their workspace and capped; existing keys become VIEWER

A key now acts only in the workspace it was created for (another workspace is
403), and at the lower of its `role_cap` and its creator's current role,
re-read on every request. A key cannot create keys.

`POST /api/v1/auth/api-keys` takes an optional `role_cap` (`VIEWER`, `MEMBER`,
`APPROVER`, `ADMIN`, `OWNER`). It defaults to `VIEWER` and may not exceed the
creator's own role in that workspace.

**Every existing key is set to `VIEWER` by the upgrade** (migration `0020`).
A pipeline that synthesizes, edits or administers with a key will get 403
after upgrading. **Recreate any key that needs more**, passing the `role_cap`
it needs, and revoke the old one.

### Column types, defaults and introspected identifiers are checked before SQL

A column's `data_type` must parse as exactly one SQL type and its
`default_value` as exactly one scalar expression. Anything else is a linter
**error** (`INVALID_DATA_TYPE`, `INVALID_DEFAULT`), and DDL and dbt export
refuse the model (400) rather than emit it. Introspection refuses a schema,
dataset or BigQuery project name that is not a plain identifier (422).

### The audit trail records every declared action, and says where each belongs

Every action in the audit vocabulary is now written by the code path it names:
API-key creation and revocation, model creation (synthesis and introspection),
edits, transforms and deletion, artifact exports, and membership grants,
including the personal workspace created for a new user. `AUTH_LOGOUT`,
`MEMBER_ROLE_CHANGED` and `MEMBER_REMOVED`, which nothing emitted, are removed
from the vocabulary (migration `0021`; it refuses to run if any stored row uses
one).

Each event carries a `scope`: `workspace` with its workspace, or `appliance`
with none (sign-ins, failed sign-ins, SCIM). Appliance events are read by the
appliance owner, the account `create-owner` makes, at
`GET /api/v1/audit/appliance-events` and `GET /api/v1/audit/appliance-export`
(JSONL). A workspace OWNER does not have this access.

### Paradigm transformation refuses two cases

`POST /api/v1/model/{id}/transform-paradigm` now returns **409** when the
model's current version has a recorded approval (sign-off covers the version
signed; any edit lapses it), and **422** with the linter's error codes when the
transformed graph has linter errors. In both cases the stored graph is
unchanged.

### The LiteLLM proxy service is removed

`litellm-proxy` (port 4000), `config/litellm_config.yaml` and `LLM_GATEWAY_URL`
are gone. Nothing called the proxy; the backend's in-process gateway is the only
path to a model provider.
