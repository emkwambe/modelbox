# ModelBox AI — state

*Regenerated 2026-09-29 on `sprint-7/close`, branched from `main` at `d5822f1`,
the `v1.11.0` tag. This file is rewritten at every stop, merge, deploy and tag;
a figure here is the output of a command run for it, not a copy from another
document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `d5822f1` | release prep merged (#10) on top of Sprints 5–7 (#9, `d81f569`); CI green (run 36511210046, ten jobs) |
| `v1.11.0` | `d5822f1` | tagged 2026-09-29 (UTC); published by the gated release workflow (run 36511971512: gate, backend and frontend images all green) |
| `sprint-7/secure-by-default` | `49191cc` | kept: the Proof Log, register and verification records cite its commits and runs |
| `sprint-7/close` | from `d5822f1` | the Verify Release workflow and these records; pull request into `main` |

Migration head: `0022_append_only_ledgers`.

## Versions

- Latest tag on the remote: **`v1.11.0`**, at `d5822f1`.
- Version stamp in the code: **1.11.0** (`scripts/check_versions.py`: all
  stamps agree).
- Published images: `ghcr.io/emkwambe/modelbox-backend` and
  `ghcr.io/emkwambe/modelbox-frontend`, `1.11.0` (also `1.11` and `latest`).

## Status

Not for deployment on a shared network before v1.11.0 (README, Status).
v1.11.0 is now released.

## Repository contents

Sprint prompts, sprint plans and research documents moved out of this
repository on 2026-09-28. Git history is unchanged.

## What v1.11.0 ships

Secure by default, proven against the running appliance: secrets required at
start-up, the first account from `create-owner`, no self-registration in
production, one published port, a declared minimum role on every route with API
keys scoped to their workspace, an audit trail with an appliance owner and
failed writes reported on `/health`, append-only ledgers under a
least-privilege database role, and a gateway that records every provider
request and records failures as fields. A black-box acceptance suite
(`tests/blackbox/`) proves these against the containers in CI.

The Security FAQ, the Proof Log (PL-015 to PL-017 added) and the acceptance
register state what those tests prove: G10, G11 and D8 are MET; G8 is
re-specified to OIDC and stays NOT MET until its UI login flow.

Breaking changes and upgrade steps: `docs/RELEASE_NOTES_v1.11.0.md`. Index of
versions: `CHANGELOG.md`.

## Published-image verification

`.github/workflows/verify-release.yml` runs the black-box suite against the
images a release published, pulled on a runner that never built them. It runs
after every successful release, and on demand; v1.11.0's run is dispatched once
this workflow is on `main`, and its result is in that workflow's run history.
