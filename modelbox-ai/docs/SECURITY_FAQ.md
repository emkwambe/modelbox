# ModelBox AI — Security FAQ

*For security reviewers, data-protection officers and platform teams assessing
the appliance. Last reviewed 2026-09-28 against `sprint-7/secure-by-default`,
including a black-box suite run against the installed appliance.*

**Every capability statement below carries a `PL-` identifier** pointing at
[`marketing/PROOF_LOG.md`](marketing/PROOF_LOG.md), where the claim is written
out with the named tests that make it true, why it is stronger than it looks,
and its honest limits. A statement here without such an identifier is describing
architecture, not asserting a guarantee. That rule is not decoration: it is
register criterion **E2**, and `test_security_faq_cites_real_proof.py` fails if
this document cites an entry that does not exist.

Where the answer is "no" or "not yet", it says so. A reviewer who finds one
overstatement is right to discount everything else, so nothing here is stated
past its evidence.

---

## 1. What leaves the network?

**By design, one kind of thing: a prompt sent to a language-model provider.** No
other feature is built to reach outside. ModelBox is a data *modelling* tool —
it works on schemas, not on your rows.

**Configuration C proves the appliance needs no outbound connection to start or
run (PL-010).** Our CI installs it with every service except the web UI on a
Docker network that has no gateway, first proving the backend cannot open an
outbound connection, and then shows that it starts, serves its API through the
UI, refuses a request routed to a cloud provider, and records no outbound
attempt.

**On a network that allows outbound traffic, the way to guarantee nothing else
leaves is air-gapped mode on a network without a route** (`AIRGAPPED=true`,
§3). The design sends nothing else; that configuration is what makes it a
guarantee rather than a design statement.

Four features send a prompt: synthesising a model from requirements,
transforming a model between paradigms, enriching a data dictionary, and the
Trainer's Socratic tutor. Everything else — linting, diffing, DDL and dbt
generation, contract and semantic-layer export, synthetic seed data — is
deterministic local computation and reaches no network at all.

**What a prompt contains** is your requirements text plus, for a transform, the
schema being transformed: entity names, column names, types, and the
descriptions you wrote. **It does not contain your data**, because the appliance
never holds your data. Reverse-engineering an existing warehouse reads
`INFORMATION_SCHEMA`, not table contents.

> **Nothing reaches a provider without being recorded first (PL-008).** This is
> structural, not a matter of remembering to log: no module outside the gateway
> can import a provider SDK, exactly one function inside it reaches the client,
> and the ledger write precedes every statement in that function that does. All
> three are asserted by tests, so a fourth call site added later fails the build
> rather than escaping the record. **Each HTTP request is its own row**, a
> retry after an invalid response included.

**The ledger stores a prompt's SHA-256 and its length, never its text**
(`test_the_ledger_does_not_store_the_prompt`). You can prove two requests
carried the same prompt; you cannot read either from the audit trail. **Nor
does it store what the model said:** a failed request is recorded by provider,
model, error class, HTTP status, the provider's error type or code, and
retry-after seconds, as validated fields, never as the model's output or free
text (PL-008).

---

## 2. Where does it go?

To whichever provider the router resolves for that task, and to nowhere else.
Routing is declared in `config/model_router.yaml`, which you can read and change
before first start.

Providers are grouped by **egress class** — `local`, `cloud_eu`, `cloud_apac`,
`cloud` — and each task declares which classes it may reach:

```yaml
egress_policy:
  local:      ["local"]
  cloud_eu:   ["local", "cloud_eu"]
  cloud_apac: ["local", "cloud_apac"]
  cloud:      ["local", "cloud_eu", "cloud_apac", "cloud"]
```

**The permitted set is declared, never inferred from an ordering.** This matters
more than it looks. Any ranking of those four names asserts either
`cloud_eu ≤ cloud_apac` or the reverse, and both are false as residency
controls: an EU-pinned task must not fail over to APAC, and an APAC-pinned task
must not fail over to the EU. A scalar comparison gets exactly one of the two
wrong, silently, in the permissive direction. So the policy is a map, the
residency check runs again inside the function that reaches the provider, and a
task with no pin is a configuration error at load rather than an implicit
allowance.

**A failover is a second request, to a second provider, and the ledger shows it
as one.** If a call to a US provider fails and the chain moves to an EU one,
that is two requests that left your network and two rows.

---

## 3. How do we stop it?

> **Two independent controls, both tested (PL-010).**
>
> **`AIRGAPPED=true`** — every task resolves to a local runtime, with cloud
> providers stripped at route resolution rather than declined later. The test
> suite runs this path with **every provider key present and populated**, then
> asserts none is sent; a test with the keys removed would prove nothing.
>
> **`MODELBOX_ALLOW_PROVIDER_CALLS=0`** — the gateway refuses before it
> constructs a client at all. A refusal issued after the SDK has opened a
> connection is not a refusal.

They are independent on purpose, so you can verify one without trusting the
other, and they are not the same switch renamed: one is a residency control, the
other a fail-closed library gate.

Air-gapped mode needs a local engine to be useful — the appliance ships one
(`ollama-engine`, compose profile `airgap`). With `AIRGAPPED=true` and no local
engine running, tasks resolve local-only and then fail. That is the correct
behaviour: it fails rather than quietly reaching for a cloud provider.

**You do not have to delete your API keys to turn egress off**, which is what
makes the control auditable — a system that only stops calling out because it
has no credentials has not demonstrated a control.

---

## 4. What is recorded, and who can see it?

> **An operator can see what left the network, and what we cannot account for
> (PL-009).** `/settings/egress` shows every recorded request: when, which
> provider, which egress class, whether it succeeded, its token cost, and which
> user and workspace caused it.

Each request produces an `ATTEMPT` row before it is sent and a `SUCCESS` or
`FAILURE` row after. A lone `ATTEMPT` means "we tried and cannot say what
happened" — never "this did not happen". The table is append-only.

The view is **scoped by workspace membership**, like every other listing. Rows
that carry no workspace — written before attribution existed — are **counted and
reported as unshowable rather than omitted**, because "this is what left" and
"this is what left that we can attribute" are different answers and only one is
true.

Two consequences a reviewer should weigh:

- There is **no appliance-wide "see everything" role**. Someone who is not a
  member of every workspace cannot read the whole ledger from the UI. For a
  complete picture today, query `egress_audit` directly.
- Rows written before 2026-08-29 carry no actor, permanently. No backfill can
  invent who caused them.

---

## 5. Authentication, secrets and multi-tenancy

- **One organisation per appliance.** Workspaces are teams within a single
  organisation; two organisations need two appliances. Two things are
  appliance-wide by design as a result: the SCIM token, and the sign-in events
  only the appliance owner reads.
- **The installed appliance refuses the credentials this repository publishes
  (PL-015).** It will not start until its four secrets are set, and names the
  one that is missing. It has no default account and no open registration; the
  first owner is created on the command line (`python -m app.cli
  create-owner`). A token signed with the development secret is refused. Each
  of these is checked against the running appliance, and each check has been
  seen to fail against a test-only profile that puts the weakness back.
- **One port is published: the web UI's (PL-015).** The API, the database, the
  cache and the local model runtime are unreachable from the host. The UI port
  is plain HTTP, so terminate TLS in front of it.
- **Authentication** is JWT, and tokens are validated for audience and issuer,
  not merely for signature (register D9).
- **Roles are enforced by the API (PL-016).** Every route declares its minimum
  role (VIEWER, MEMBER, APPROVER, ADMIN or OWNER). An API key acts only in the
  workspace it was minted in, at no more than the role its creator gave it and
  still holds, and a key cannot mint another key. There is no API or UI to add
  workspace members or change their roles yet.
- **Sign-ins are audited (PL-017).** Sign-ins, failed sign-ins and SCIM changes
  reach the appliance owner's JSONL export. A failed audit write is logged as an
  error, and `/health` reports the appliance as degraded.
- **Provider credentials** are supplied by environment file and are never
  written to the ledger, the database, or any exported artifact.
- **Connection strings** for reverse-engineering are encrypted at rest with
  `ENCRYPTION_KEY`. The compose file has no default for it, and the appliance
  refuses to start while it is unset or equal to the development value in this
  repository, because a default encryption key is not encryption.

---

## 6. What we do not claim

Stated plainly, because a security document that only lists strengths is not a
security document.

- **No prompt masking.** An earlier version of this product advertised it; the
  implementation was an identity function and has been deleted along with the
  claim (register D1). Use `AIRGAPPED` if metadata must not leave.
- **No host hardening claim.** The egress controls govern what the application
  does. An operator with shell access can make network calls the appliance did
  not, and nothing here is a sandbox.
- **What append-only means here, and where it stops.** Three statements, each
  exact:
  - *The application cannot rewrite the ledgers.* The backend and worker
    connect as `modelbox_app`, which may read and add rows in `audit_event` and
    `egress_audit` and may not update, delete or truncate them, or switch
    triggers off. This holds for anyone using the application's credentials.
  - *Changing a ledger needs the database owner, as a deliberate schema
    change.* A trigger refuses updates, deletes and truncation for every role,
    the owner included. Altering a ledger means dropping or replacing that
    trigger, which is a schema change the owner must make on purpose, and
    which the appliance only ships as a migration, recorded in its migration
    history.
  - *Root on the host is out of scope.* Someone with root on the host can read
    `.env`, act as the database superuser, or edit the data files directly,
    and none of the above stops them. Protecting the host is the operator's
    responsibility.
- **No transport-security claim beyond TLS to the provider.** These controls
  decide whether a request is made, not what an observer sees.
- **No formal certification.** No SOC 2, ISO 27001 or comparable audit has been
  performed. This document describes tested engineering controls, which is a
  different thing and should not be read as a substitute.
- **No claim about provider-side retention.** Where your prompt goes after it
  reaches a provider is governed by that provider's terms. The
  `enforce_zero_retention` setting in the router config records an intent and
  is read by no code in this appliance; it is **not** something this appliance
  can enforce or verify, and it must not be read as a guarantee about a third
  party.
- **Preview dialects are labelled, not certified.** Three SQL dialects and
  LookML are marked Preview in the export UI and excluded from the artifact
  fidelity burn-down.

---

## 7. How to verify any of this yourself

Every claim above is reproducible without taking our word for it:

```bash
# The egress controls, the ledger, and the choke point
cd backend
.venv/Scripts/python -m pytest tests/test_egress_choke_point.py \
  tests/test_airgap_routing.py tests/test_egress_residency_and_failover.py \
  tests/test_egress_attribution.py tests/test_egress_ledger_view.py -v

# The ledger against a real PostgreSQL, by raw SQL rather than through the ORM
.venv/Scripts/python -m pytest tests/test_migration_0015_egress_audit.py -v
```

The Proof Log entry for each claim names its tests, its expiry condition, and
what it may not be used to say. If a test named there no longer exists, treat the
claim as withdrawn.
