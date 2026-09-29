# ModelBox AI — state

*Regenerated 2026-09-28 on `sprint-7/secure-by-default` at `ac1e36a`. This file is rewritten at
every stop, merge, deploy and tag; a figure here is the output of a command run
for it, not a copy from another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `49d268c` | README and home page claims narrowed (#6); `dbt_date` 0.21.0 lock (#7) |
| `sprint/6-product-experience` | `8001975` | Sprints 5, 6 and 6.5; never merged to `main` |
| `sprint-7/secure-by-default` | `ac1e36a` | cut from `8001975`, `origin/main` merged in; pushed, CI green at `ac1e36a` (run 36503016248, ten jobs); pull request into `main` not yet opened |

Migration head: `0022_append_only_ledgers`.

## Versions

- Latest tag on the remote: **`v1.9.0`**.
- Version stamp in the code: **1.10.0**. `v1.10.0` was never tagged, and its
  release notes are marked unreleased and superseded.
- Next release: **v1.11.0**, cut only from a green, merged `main`.

## Status

Not for deployment on a shared network before v1.11.0 (README, Status).

## Repository contents

Sprint prompts, sprint plans and research documents moved out of this
repository on 2026-09-28. Git history is unchanged.

## In progress

Hardening, and a black-box acceptance suite that runs against the containers.
It ships as v1.11.0, the first merge to `main` since v1.9.0. Done so far:
secrets and start-up defaults, one published port, a declared minimum role on
every route with API keys scoped to their workspace, a complete audit
vocabulary with an appliance owner, append-only ledgers with a
least-privilege database role, a populated upgrade from 0015 to head with the
ORM checked against the migrated Postgres schema, and a gateway that classifies
provider failures by their cause and records every provider request, schema
re-asks included, as its own ledger attempt, describing a failure without
quoting the model's output in the ledger, the logs or its errors. Audit writes
that fail are logged and reported on `/health`.

A black-box acceptance suite (`tests/blackbox/`) runs in CI against the
containers: the install refusing an unset `.env`, the hardened appliance, an
upgraded database, an air-gapped appliance on a network with no route out, and
a test-only insecure profile against which each check covering a weakness that
profile reintroduces must fail.

The Security FAQ, Proof Log (PL-015 to PL-017 added) and acceptance register
state what these tests prove: G10 and G11 are MET against the running
appliance, D8 is MET, and G8 is re-specified to OIDC and stays NOT MET until
its UI login flow.

CI runs per commit on ubuntu-24.04. A release is published only for a tag
whose commit is on `main` with a green CI run. Breaking changes and upgrade
steps are in `docs/RELEASE_NOTES_v1.11.0.draft.md`.
