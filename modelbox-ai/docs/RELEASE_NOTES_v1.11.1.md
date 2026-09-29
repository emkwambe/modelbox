# ModelBox AI — v1.11.1 Release Notes

**Tag:** `v1.11.1`, at `e8d9ac1` on `main` (pull request #12), published by
the gated release workflow (run 36516574170)  ·  **Supersedes:** v1.11.0, whose
tag and images remain  ·  **Upgrade:** pull the new images; no migration and no
configuration change.

## A request's transaction completes before its response is sent

Every API request that writes to the database now commits, or fails, before
the appliance sends its response:

- a successful response always describes committed work, so a client that acts
  on it at once, for example by using an API key the appliance has just
  returned, finds the change in place;
- a write that cannot be committed returns an error (HTTP 500), never a
  success.

The two JSONL audit exports, which read from the database while they send
their body, keep a read-only session open until the export has been sent.

**Verified** in-process by the order of the commit and the response on a real
route, a failed commit answered with a 500 and nothing before it, and every
route checked for the declared behaviour, each with a negative control; and
against the running appliance by a check that uses fifty freshly minted keys,
each on the request after it was returned.

## Black-box test reports

The black-box acceptance suite now redacts every token, key and password it
handles from its failure reports, down to eight-character fragments, and a
test enforces it.

## Frontend image build

The frontend image installs its packages with `npm ci --ignore-scripts` and
then runs their install scripts with `npm rebuild`, after every package is in
place. The installed set is unchanged, and the install still refuses an
incomplete lock.

## Breaking changes

None.
