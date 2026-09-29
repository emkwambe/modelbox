# ModelBox AI — the value narrative

*What we say, who we say it to, and the evidence under every sentence.*

**This document obeys register G3 and the Claims rule in `CLAUDE.md`: no public
surface states a capability without a `PL-` id behind it.** Every claim below
carries one. Where we have no entry, the claim is absent — not softened, absent.
That constraint is not a tax on the marketing. It *is* the marketing: this is a
product whose entire proposition is that its output was checked, and a claim
sheet that cannot itself be checked would refute the pitch in the act of making
it.

Two words never appear in a headline: **"AI"**, because SqlDBM's Context Layer
tier now sells AI Copilot, MCP connectivity and an agent framework, and saying it
puts us in a feature comparison against an incumbent with more sales reach; and
**"LLM-agnostic"**, because Cube already ships Bring-Your-Own-LLM at Enterprise
and model choice will be a checkbox everywhere within a year. Neither is a wedge.
Both are true, and both belong on page four.

---

## 1. The sentence

> **Every schema we generate ships with proof it loads — the DDL executed, the
> dbt project parsed, the contract validated by the tools that consume it — and
> an append-only record of every byte that left your network to produce it.**

Its two halves are the two things a data programme has to hand somebody: *the
artifact works*, and *here is what we did to make it*.

---

## 2. Start where the buyer already hurts

Do not open with what the product does. Open with the thing they have already
lived through, and let them recognise it.

**For the consultancy:** *the model was signed off in week three, and week seven
was spent hand-editing the dbt project until it would parse on the client's
warehouse. Nobody billed for week seven.*

**For the bank:** *your risk-data remediation programme has to demonstrate that
the model in the document is the model in the warehouse. Right now that
demonstration is a person, a spreadsheet, and their word.*

Neither sentence mentions us. Both are the shape of the sale. If the room does
not nod at one of them, this is not the buyer, and the correct move is to stop
rather than to demo harder.

---

## 3. Why the obvious alternatives do not close it

The four objections are not obstacles to get past. They are the argument — each
one, answered concretely, is a reason to care.

### "dbt already does this."

It does part of it, and its own documentation states the limits. dbt model
contracts cover SQL models only — not Python models, not materialized views, not
ephemeral. **Sources, seeds and snapshots cannot be contracted at all.** And
enforcement is not uniform: on **Redshift and Snowflake only `not_null` is
enforced, while Postgres enforces every constraint type.**

Say that to a bank running both and watch the room change. It means their
constraint enforcement is silently weaker on two of their platforms, and nothing
told them.

dbt contracts are an internal governance mechanism for models that already
exist. They do not begin from requirements, they do not cross the wire to a
Kafka consumer, and they are not a document a supervisor can read. We emit
Protobuf whose tags come from stable identities, so inserting a column
mid-table does not break a consumer built against yesterday's contract
(**PL-012**), and ODCS v3.1.0 that carries the meaning of each constraint and
not merely its vocabulary (**PL-013**).

### "Why not just use Claude or ChatGPT directly?"

For one table, you should — and we will say so. A frontier model will write you
plausible DDL, a plausible dbt project and a plausible contract.

What it will not tell you is which of the three fails to parse.

Ours are handed to `sqlfluff`, `dbt parse`, `dbt build`, `protoc`, `fastavro`
and a live DuckDB *before you see them* (**PL-001**, **PL-002**, **PL-007**,
**PL-011**, **PL-014**). A chat session also leaves no egress record, no
residency guarantee and no version-to-version diff.

The claim is about the fiftieth artifact and the second version, not the first.

### "Our modellers use erwin and will not switch."

Then don't switch. We are not asking for the canvas — erwin owns that
emotionally and we will lose that fight in every room where we pick it.

We are the stage *after* the model: reverse-engineer the warehouse erwin
forward-engineered into, and emit what erwin does not — the dbt project, the
semantic layer, the contracts, the seed data, the governance lint. The
modeller's model stays the source of truth.

### "We do not trust a language model with our schema."

We will not argue you out of that, because arguing loses. Pick your position and
we will show you the evidence for it.

Fully air-gapped: `AIRGAPPED=true` resolves every task to a local runtime, with
cloud providers stripped at route resolution — and there is a second,
independent stop (**PL-010**). Or governed: every request is written to an
append-only ledger **before it is sent**, and if the ledger cannot be written the
request is not made (**PL-008**). No code outside a single gateway can reach a
provider at all.

That distinction is the whole argument, and it is worth saying in these exact
words: **the ledger is an authorisation record, not a log.** A log tells you what
happened. This decides whether it happens.

---

## 4. What you actually get, and the id under each

| We say | Evidence |
| :-- | :-- |
| Four SQL dialects verified against real dialect grammars, not our own parser | **PL-001** |
| The DDL is executed on a live engine, and the tables that come back are the tables you modelled | **PL-002** |
| The dbt project runs as-is — you supply the warehouse connection, we supply everything else | **PL-007** |
| Semantic layers parsed by dbt and by a JavaScript engine, not eyeballed | **PL-011** |
| Contracts that stay wire-compatible when a column is inserted mid-table | **PL-012** |
| Valid ODCS v3.1.0 that says what the constraint meant | **PL-013** |
| Seed data that satisfies the contract generated beside it, and `dbt build` passes | **PL-014** |
| The same model always produces the same bytes | **PL-005** |
| Column identity never moves and is never reused | **PL-006** |
| Every provider request recorded before it is sent, on a path nothing can bypass | **PL-008** |
| An operator can read what left the network — and what we cannot account for | **PL-009** |
| Two independent ways to stop egress entirely | **PL-010** |

---

## 5. What we do not claim

This section is not a disclaimer. It is the most persuasive part of the
document, because it is the part a competitor's deck does not have — and a buyer
who has been sold to before knows exactly what its absence means.

- **BigQuery, Databricks and ClickHouse DDL are Preview and do not work.** They
  are labelled in the export picker before you choose one, not in a footnote
  afterwards. LookML is Preview too, with a known defect: it emits `SUM()` over
  a foreign key.
- **We do not have SSO, SCIM, RBAC or audit-log export yet.** They are scheduled
  (Sprint 6.5, criteria G8–G12). Until they ship, the honest first engagement in
  a bank is a non-production enclave, and we will say so before you ask.
- **Single node.** There is no HA story yet, only a stated availability position.
- **`dbt parse` proves a project resolves, not that its SQL returns what you
  expect.** No test we run knows your business.
- **PL-009's "everything that left" is workspace-scoped** — everything in the
  workspaces you belong to, plus a count of what could not be attributed. We
  publish the count rather than quietly dropping the rows.

Every one of those is in our Proof Log or our register already. You will find
them whether or not we volunteer them; volunteering them is cheaper and it is
the same instinct that makes the rest of the document trustworthy.

---

## 6. The demo that closes it

The weakness of a correctness claim is that its value is counterfactual: it
shows up as the absence of a failure, which is invisible in thirty minutes.

So do not present the Proof Log. **Break something in front of them.**

1. Take their own requirements — a page of prose from a real programme.
2. Generate. Show the DDL executing on DuckDB and the dbt project parsing.
3. Now edit one column type by hand, the way a hurried engineer would, and
   re-run. Watch the harness turn red and name the artifact that broke.
4. Then run the same prose through a frontier chat model with no harness, feed
   *that* output into the same harness, and show what fails.

Step four is the entire sale, and it is the one artefact worth building before
any landing page: a published, dated, re-runnable comparison. Re-run it on each
new model release with the expiry condition stated, exactly as a `PL-` entry
requires.

Correctness you can watch fail is persuasive. Correctness asserted in a document
is not.

---

## 7. The two buyers, in their own language

### The boutique data consultancy (5–200 people)

Economic buyer and champion are the same person, which is why this closes in
weeks. They compete on delivery speed against firms ten times their size and
cannot fund internal tooling.

Lead with the consequence, never the mechanism:

> **Your deliverable lands at the client without a hand-edit — and you can show
> the client why.**

Twenty consultant-days removed from one engagement is roughly £10,800 of
recovered margin at the UK median contract rate. The licence pays for itself
inside a single project. The Proof Log's job in this room is narrow and real: it
converts a sales assertion into something their technical lead can check.

### The bank or insurer, in regulatory remediation

The budget line is not "data modeling tools". It is **MRA remediation**,
**consent-order remediation**, **SREP finding remediation**, **RDARR programme**.
That distinction is the whole difference between a three-year commitment and a
one-year pilot that quietly dies.

Here the evidence *is* the product:

> **The model, the artifacts it produced, and the record of how they were
> produced — as one thing a reviewer can follow end to end.**

The pressure is real and continuous. State it accurately: the ECB's supervisory
priorities for 2026–2028 place risk-data aggregation under Priority 2 and say
banks should remedy material weaknesses in those frameworks in an effective and
timely manner. **Do not imply a deadline or an escalation procedure — that page
names neither.** Their compliance function will know, and the credibility loss
would be total, on precisely the axis we are selling.

---

## 8. What must never be said

- Anything with no `PL-` id.
- Any implication that BCBS 239 or the AI Act imposes a dated cliff that we
  relieve. The EU AI Act's high-risk obligations begin in December 2027 and
  August 2028; a 2026 urgency claim is false.
- That our Trainer certificate is evidence a supervisor requires. BCBS 239 ¶29(a)
  asks for expertise in the people validating risk data. It does not ask for a
  vendor's certificate, and no supervisory text we have found requests one. It
  is supporting material for a self-assessment pack. Anything stronger needs a
  `PL-` entry we have not earned.
- "The only tool that can run air-gapped." Air-gap does not win a segment —
  most buyers who say they cannot use a cloud model are describing a default,
  not a policy. What air-gap wins is **the security review becoming a no-op**.
  Sell that instead; it is true in every segment rather than rare in one.

---

## 9. The shortest version

Three sentences, in this order, and stop talking:

> Your model is a document until its artifacts load.
>
> We generate the model from your requirements and hand every artifact to the
> tool that consumes it — the DDL executed, the dbt project parsed, the contract
> validated — before you see any of it.
>
> And every byte that left your network to do it is on an append-only record,
> written before the request was sent.
