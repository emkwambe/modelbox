# ModelBox AI — v1.10.0 Release Notes

**Tag:** `v1.10.0`  ·  **Sprint:** 5 — governance that holds

**This is the release where the appliance can be asked what it did.** v1.9.0
could say "our exports run". This one says: nothing reaches a model provider
without being recorded first, every recorded request names who caused it, an
operator can read that record from the UI, and there are two independent ways to
stop egress that are tested with the credentials present rather than removed.

It is also the release where the product's own install stopped working in a way
nobody had noticed, and was fixed.

---

## Governance

### Nothing leaves unrecorded, and now it says who

The egress ledger (v1.9.0 groundwork, `PL-008`) records an `ATTEMPT` before a
request is sent and its outcome after. The guarantee is structural rather than
diligent: no module outside the gateway can import a provider SDK, exactly one
function inside it reaches the client, and the ledger write precedes every
statement in that function that does — so a fourth call site added next year
fails the build rather than escaping the record.

What it could not do was answer *who*. The `user_id`, `workspace_id` and
`model_id` columns existed from migration 0015 and **every call site left them
null** — a nullable column nothing populates, invisible until someone asks the
question the ledger exists to answer. All three call sites now thread the actor,
including the Celery worker, which owes the same attribution as the HTTP route
or an operator learns that "the worker" caused the egress.

### An operator can read it without SQL — `PL-009`

`/settings/egress`, reachable from the Studio nav: when, which provider, which
residency class, success or failure, token cost, and which user and workspace
caused it. Metadata only — the ledger stores a prompt's SHA-256 and length,
never its text, and the view does not widen that.

**The view reports what it cannot show.** It is workspace-scoped like every
other listing, so rows written before attribution existed belong to nobody and
are returned to nobody. Omitting them silently would let an operator read "one
request left the network" from a ledger holding five. They are counted, and the
page says so.

### Two ways to stop egress, both tested with the keys present — `PL-010`

`AIRGAPPED=true` strips cloud providers at route resolution;
`MODELBOX_ALLOW_PROVIDER_CALLS=0` refuses before a client is constructed. They
are independent, so a reviewer can verify one without trusting the other.

The air-gap suite runs with **every provider key populated**, because a test with
the credentials removed proves nothing — a run with no keys cannot reach a
provider whatever the routing does.

### A security reviewer can answer their own questions

`docs/SECURITY_FAQ.md`: what leaves, where it goes, how to stop it, what is
recorded, and what the product does not claim. Every capability statement carries
a `PL-` identifier, and a test fails if the document cites an entry that does not
exist or if an answer section states capabilities citing nothing.

---

## The install was broken, and the docs said otherwise

**Every provider key reached the containers empty.** They were written as
`${ANTHROPIC_API_KEY:-}`, and Compose resolves interpolation from its *project
directory* — the folder holding the compose file, not the folder holding `.env`.
The documented quickstart put `.env` one level up, so a documented install
produced an appliance with no credentials that failed at the first synthesis with
the whole provider chain exhausted in 23 seconds.

Keys now arrive through `env_file:`, whose paths resolve relative to the compose
file. **That fixes credentials and nothing else**, and the README now says so:
every `${VAR}` elsewhere — `UI_PORT`, `POSTGRES_PASSWORD`, `ENCRYPTION_KEY`,
`AIRGAPPED` — still needs `--env-file .env`, and three of those four fail
silently.

Also fixed: a retired Gemini model identifier that returned 404 and read exactly
like a bad credential, and a `request_timeout_seconds` / `num_retries` pair that
had been in the router config from the beginning and was **read by nothing**.

---

## Conformance: the metric was wrong, not the model

The first provider conformance run scored entity F1 0.288 against a threshold of
0.80 — and the conclusion was that the instrument was broken, because the
threshold had been committed *before* any code could call a provider and could
not be quietly moved to suit the result.

The evidence was in the report: `ecommerce-orders` 0.857 and `saas-subscription`
0.000, same model, two near-identical Kimball tasks. A model does not comprehend
e-commerce warehousing and then fail completely on subscription warehousing.

Entities are now matched by column-vocabulary overlap rather than by name, an
axis that does not apply to a graph is excluded from its average instead of
scoring a free 1.0, and the runner persists candidate graphs so a future metric
change can be re-applied without paying for a new run.

**The pass thresholds are unchanged.** The one new number states plainly that it
cannot claim the threshold-before-output property the others have.

---

## Product

Three defects found by driving the running appliance rather than the test suite:
the workspace badge covered the canvas toolbar and made **"Export artifacts"
unclickable at every viewport**; a library template loaded onto the canvas left
every action disabled with nothing explaining why; and a job that never started
was reported as a timeout while its status said otherwise.

A new Trainer lab, `m4_lab2_integration_review`, teaches the four linter codes no
lab covered — and its headline flaw is this programme's own history, the
`VARCHAR(6)` column carrying an eight-character pattern that produced the
`PATTERN_EXCEEDS_LENGTH` check.

---

## Known open items

Listed rather than omitted (register **E4**).

| Item | State |
| :-- | :-- |
| **D10** — provider conformance report | **Open.** The harness is built and isolated, and the metric is fixed, but no report exists under the corrected metric. D10's evidence is the report, not the script: a harness that has never produced a number proves the method, not the claim. Needs a cloud re-run plus a local run |
| **G1** — unassisted install | **Open.** The blocker above is fixed, but the criterion's evidence is a transcript from someone who has never seen the appliance, and no such evaluation has happened |
| `NEXT_PUBLIC_API_URL` is inert | Next.js inlines `NEXT_PUBLIC_*` at build time and `Dockerfile.frontend` takes no build arg, so the compose value is never applied. It works only because the code default matches. Third instance of configuration the code does not read |
| Four Proof Log claims unusable | Earned by passing tests in Sprints 3–4 but named by no `PL-` entry, so rule E2 blocks them from any public surface |
| No appliance-wide ledger role | The egress view is workspace-scoped; a complete read still needs SQL for anyone not in every workspace |
| DDL `CHECK` clause | Carried from Sprint 4: `check_expression` reaches ODCS and dbt but no `CHECK` is emitted into the DDL |
| Role-playing dimensions | Carried from Sprint 3: two foreign keys from one entity to the same parent produce duplicate MetricFlow entity names |
| Preview dialects | Three SQL dialects and LookML remain labelled Preview and outside the fidelity burn-down (18 xfail, unmoved) |

---

## Verification at this tag

```
app suite            622 passed, 36 skipped, 18 xfailed
fidelity, non-preview 229 passed, 0 xfail
fidelity, preview     18 xfailed, 2 passed
ruff (app + tests)    69, all pre-existing
```

Criteria met this sprint: **D3, D4, D5, D6, D7, D8, D9, G2, H2, H4.**
