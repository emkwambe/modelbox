# ModelBox AI — state

*Regenerated 2026-09-29 on `fix/v1.11.1`, branched from `main` at `d5822f1`
(the `v1.11.0` tag). This file is rewritten at every stop, merge, deploy and
tag; a figure here is the output of a command run for it, not a copy from
another document.*

## Where the code is

| Ref | Commit | Notes |
| :-- | :-- | :-- |
| `main` | `d5822f1` | Sprints 5–7 (#9, `d81f569`) and the v1.11.0 release prep (#10); CI green (run 36511210046, ten jobs) |
| `v1.11.0` | `d5822f1` | tagged 2026-09-29 (UTC); published by release run 36511971512; superseded by v1.11.1, and kept |
| `fix/v1.11.1` | from `d5822f1` | a request's transaction commits before its response; black-box report redaction and a read-your-writes check; version 1.11.1; pull request into `main` |
| `sprint-7/close` | from `d5822f1` | the Verify Release workflow; pull request #11, held until v1.11.1 is verified |
| `sprint-7/secure-by-default` | `49191cc` | kept: the Proof Log, register and verification records cite its commits and runs |

Migration head: `0022_append_only_ledgers`.

## Versions

- Latest tag on the remote: **`v1.11.0`**, at `d5822f1`.
- Version stamp in the code on this branch: **1.11.1**
  (`scripts/check_versions.py`: all stamps agree).
- Next: the owner tags **`v1.11.1`** from `main` once CI is green there;
  `release.yml` publishes only a tag whose commit is on `main` with a green run.

## Status

Not for deployment on a shared network before v1.11.0 (README, Status). Use
v1.11.1 once it is published.

## Repository contents

Sprint prompts, sprint plans and research documents moved out of this
repository on 2026-09-28. Git history is unchanged.

## What v1.11.1 ships

Everything in v1.11.0 (`docs/RELEASE_NOTES_v1.11.0.md`), and every API request
that writes now commits, or fails, before its response is sent
(`docs/RELEASE_NOTES_v1.11.1.md`). Index of versions: `CHANGELOG.md`.
