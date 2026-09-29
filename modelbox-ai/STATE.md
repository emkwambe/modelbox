# ModelBox AI — state

*Regenerated 2026-09-29 on `release/v1.11.0`, branched from `main` at `d81f569`.
This file is rewritten at every stop, merge, deploy and tag; a figure here is
the output of a command run for it, not a copy from another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `d81f569` | Sprints 5, 6, 6.5 and 7 merged from `sprint-7/secure-by-default` by pull request #9, as a merge commit; CI green (run 36508539613, ten jobs) |
| `sprint-7/secure-by-default` | `49191cc` | kept after the merge: the Proof Log, register and verification records cite its commits and runs |
| `release/v1.11.0` | from `d81f569` | version stamps to 1.11.0, final release notes, CHANGELOG; pull request into `main` |

Migration head: `0022_append_only_ledgers`.

## Versions

- Latest tag on the remote: **`v1.9.0`**.
- Version stamp in the code on this branch: **1.11.0**
  (`scripts/check_versions.py`: all stamps agree). `v1.10.0` was never tagged
  and is superseded by v1.11.0.
- Next: the owner tags **`v1.11.0`** from `main` after the release-prep merge,
  and `release.yml` publishes it only if that commit is on `main` with a green
  CI run.

## Status

Not for deployment on a shared network before v1.11.0 (README, Status).

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

## After the tag

The black-box suite runs against the images `release.yml` publishes, pulled on
a clean machine.
