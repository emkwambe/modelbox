# ModelBox AI — v1.11.0 Release Notes (draft)

**Status: draft, unreleased.** This file is renamed to `RELEASE_NOTES_v1.11.0.md`
in the same commit that moves the version stamp to 1.11.0. Until then the
version check reads v1.10.0's notes, and this name keeps it out of that check.

v1.11.0 supersedes v1.10.0, which was never tagged.

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

### The LiteLLM proxy service is removed

`litellm-proxy` (port 4000), `config/litellm_config.yaml` and `LLM_GATEWAY_URL`
are gone. Nothing called the proxy; the backend's in-process gateway is the only
path to a model provider.
