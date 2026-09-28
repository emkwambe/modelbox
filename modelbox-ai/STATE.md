# ModelBox AI — state

*Regenerated 2026-09-28 on `sprint-7/secure-by-default` at `dd1a079`. This file is rewritten at
every stop, merge, deploy and tag; a figure here is the output of a command run
for it, not a copy from another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `49d268c` | README and home page claims narrowed (#6); `dbt_date` 0.21.0 lock (#7) |
| `sprint/6-product-experience` | `8001975` | Sprints 5, 6 and 6.5; never merged to `main` |
| `sprint-7/secure-by-default` | `dd1a079` | cut from `8001975`, `origin/main` merged in; pushed, CI green through `c7f9129` |

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
It ships as v1.11.0, the first merge to `main` since v1.9.0. Breaking changes
so far are listed in `docs/RELEASE_NOTES_v1.11.0.draft.md`.
