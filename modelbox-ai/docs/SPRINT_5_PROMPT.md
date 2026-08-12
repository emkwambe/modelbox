# Sprint 5 — Governance That Holds

**Hand this file to Claude Code.** Branch `sprint/5-governance` from `main` at `v1.9.0`.
**Reference:** `docs/PROJECT_STATE_REPORT.md` §5 (LLM gateway & egress),
`ModelBox_AI_Enhancement_Blueprint.md` §3 (Q1, Q2), `ModelBox_AI_Acceptance_Criteria.md`
§D and §G, plus the thirteen verification standards.
**Duration:** 1.5 weeks.

**Sprint premise:** Sprints 1–4 made the product's *outputs* trustworthy. This sprint makes
its *behaviour* trustworthy — what leaves the network, where it goes, and what record
exists that it left. This is the enterprise sale, built.

Two criteria in the register are written in ways that outran their verifiability, the same
error as B6 and B11. Both are re-specified below and the new wording governs.

---

## Task 0 — Verify the scorer, before anything depends on it

**Do this first.** The graph linter now grades in three places: Trainer labs (H2, H3),
provider conformance (Task 5), and adjacent to the cross-artifact gate (Task 4). Three
claims rest on one instrument, and that instrument has never been subjected to a
discrimination test. Standard 13 applies to the measuring device as much as to the code it
measures.

The ordering is the point. Verify the scorer *before* it carries the weight — not after the
conformance numbers come back and someone has to ask whether the model or the tool was at
fault. A linter code that cannot discriminate would silently corrupt the Trainer's grading
and the air-gapped-quality verdict at the same time, in the same direction, and each would
look like corroboration of the other.

**Deliverable.** A mutation pass over the linter itself. For each of the thirteen codes:

- a graph that must trigger it,
- a near-identical graph that must not,
- confirmation the code fires on exactly one of the two.

The negative case is the load-bearing half. A code that fires on everything grades every
lab the same and rates every provider identically, and nothing downstream can tell.

**If any code cannot discriminate, that finding outranks the rest of the sprint.** Report it
before continuing.

Note what this closes. `test_trainer_labs.py` asserts set-equality between lab expectations
and linter output, which proves the labs match the linter — not that the linter is right.
Those are different claims and only one has ever been tested. This is the other one.

## Task 1 — Egress ledger (B3, D3)

Append-only `egress_audit` table: model id, user, workspace, task, provider, egress class,
prompt SHA-256, token counts, timestamp. Written from the gateway choke point.

**D3 re-specified.** The register says "a test proves no path bypasses the ledger." That is
a negative over the whole call graph and cannot be earned by sampling — a test exercising
three paths says nothing about the fourth. Make bypass structurally impossible, then test
the structure:

- Every provider call routes through a single choke point, with the ledger write inside it.
- A test asserts **no module outside the gateway imports a provider SDK directly**
  (`anthropic`, `openai`, `mistralai`, `google.genai`, `litellm`). This is checkable by
  AST or import scan, fails loudly when someone adds a sixth provider, and converts a
  behavioural claim into a structural one.
- A second test asserts the choke point cannot return without having written — construct
  it so the write is not skippable by an early return or an exception path.

D3's evidence in the register updates to cite the import test as primary.

**The choke point also enforces this sprint's own offline rule.** "Task 5 may make real
provider calls; nothing else may" is a statement of intent wearing a constraint's clothing.
The mechanism that makes it enforceable is the one being built here, so build it here: the
choke point **refuses to call any provider unless an explicit opt-in is set**, and a test
asserts the refusal. Task 5 sets it deliberately; everything else is isolated by
construction rather than by everyone remembering.

That the D3 design pays for a second property it was not built for is a good sign about its
shape.

## Task 2 — Per-task residency (D5, D8)

- `max_egress_class` as a per-task constraint enforced in `resolve_route`, not a global
  boolean. A task pinned to an egress class cannot fail over outside it.
- Typed failover: auth failure, rate limit, and schema-validation failure handled
  distinctly rather than by one catch-all. An auth failure should not be retried as though
  it were a 429.

Mutation obligation: the plausible wrong implementation checks the egress class on the
*first* provider and not on failover targets. Show the test kills it.

## Task 3 — Air-gapped mode that proves itself (D6, D7, Q1)

- Repoint `airgapped_overrides` at `local_ollama`; document vLLM as a BYO endpoint
  (Blueprint §3, Q1). The current primary `airgapped_vllm` resolves to a service that does
  not exist in the compose file.
- **D6 re-specified.** "Runs end to end with no cloud keys present" passes vacuously on a
  box that simply had no keys configured — standard 12, in a new venue. Invert it: the test
  **sets every provider key to a sentinel value**, runs air-gapped, and asserts no egress
  occurred and that any route which would have used them was refused at resolution. Absence
  must be loud.

## Task 4 — Cross-artifact consistency gate (standard 10)

Not two pair checks — a gate that takes each model and asserts that **any artifacts derived
from the same IR field agree**. Closes the category, so a pair nobody has thought of yet is
covered the day it is added.

Known candidates: ODCS `required` vs DDL `NOT NULL` (both now derive from `is_nullable`, so
agreement should be provable rather than assumed); Protobuf optionality vs Avro
union-with-null — the same emitter pair that already disagreed on NUMERIC in Sprint 3, so
the category has a track record.

Both sides already exist; nothing new is emitted. This is comparison, not generation.

## Task 5 — Provider conformance harness (D10)

The five gold graphs synthesised through each configured provider, scored by the linter,
emitted as a report. Makes "LLM-agnostic" measurable rather than architectural, and gives
regulated buyers a defensible answer about local-model quality.

**This is the sprint's only genuine unknown.** Nobody has run the gold graphs through a
local model and seen what comes back. If air-gapped quality is materially worse than cloud,
that is a product finding worth its own decision — report it, do not absorb it.

Requires provider keys, so it runs as an opt-in script rather than in the offline harness.
Keep it out of the CI gate set.

### Threshold before output

Define "materially worse" **before** running any provider. A threshold set after the first
local-model result will be set to whatever makes that result tolerable — the same failure
as a test written to match current behaviour.

No subjective judgement is needed. The instrument already exists: the graph linter scores
against thirteen codes, the five gold graphs are the reference answers, and
`test_trainer_labs.py` establishes set-equality against linter output as a grading method.
Score local-vs-cloud synthesis with the same tool the Trainer grades students with — same
prompt, same gold requirements, compare linter findings and structural distance from the
gold graph.

**State the pass threshold in writing, in the script, before the first call.**

The shape of the failure decides the remedy:

- degradation concentrated on relationships or grain → staged synthesis is indicated
- degradation spread evenly → the honest move is a narrower air-gap claim

Record provider, model identifier, and model version with every score. A quality verdict is
a statement about a specific model at a specific version, exactly as a fidelity verdict is a
statement about a resolved dependency set. Without it the result is not reproducible three
months from now.

This is the programme's first provider call. Every sprint since the audit has held a hard
zero-LLM-calls constraint. Breaking it here is deliberate, but the script must be
unmistakably opt-in, outside the CI gate set, and **incapable of running as a side effect of
any test invocation** — or the offline guarantee the whole harness rests on becomes
conditional on nobody running the wrong thing by accident.

## Task 6 — Security FAQ (G2)

G2 and Task 4 are the same deliverable viewed twice: "what leaves, where it goes, how to
stop it" is the egress half; "do your artifacts agree with each other" is the next question
from the same reviewer in the same meeting. Write the FAQ and build the gate in one pass.

Answerable from documentation alone, without engineering help. State the limits plainly —
admin override on branch protection, whatever the conformance harness finds.

## Task 7 — Unassisted install (G1)

An evaluator installs the appliance and exports a working artifact without assistance.
Needs a person who has not seen it; Eddy arranges. Deliverable here is the install path and
whatever documentation the attempt proves necessary.

## Task 8 — One Trainer lab (H4, pulled forward)

Nearly free and worth taking now. Thirteen findings have full narratives; the seed
generator overriding a declared `CHECK` is the best candidate — a student sees the model,
sees the generated data, sees them disagree, and learns the ordering rule better than any
exposition would teach it.

Also update the curriculum's linter-code count: `PATTERN_EXCEEDS_LENGTH` was added in
Sprint 4 and nothing teaches it. Thirteen codes now, not twelve.

---

## Definition of Done

0. Every one of the thirteen linter codes fires on a graph that must trigger it and stays
   silent on a near-identical graph that must not. The scorer is verified before anything
   depends on it.
1. Every outbound request appears in the ledger; the import test proves no module outside
   the gateway can make one. **A provider call without the explicit opt-in is refused,
   proven by test.**
2. A task pinned to an egress class cannot fail over outside it, proven by mutation.
3. Air-gapped mode runs end to end **with sentinel keys set**, and refuses any route that
   would use them.
4. Cross-artifact gate asserts agreement generically, not pair-by-pair.
5. A conformance report exists comparing at least one local and one cloud provider.
6. Security FAQ answers a reviewer's standard questions from documentation alone.
7. Standing DoD (Blueprint §7): CI green, docs updated in-PR, Proof Log updated, appliance
   smoke, tag from green `main`.

Register criteria closed: D3, D4, D5, D6, D7, D8, D10, G2, G4, H4. G1 pending the
evaluator.

## Constraints

- Windows PowerShell, absolute paths, BOM-free UTF-8.
- No Python-source edits through bash heredocs; no regex-driven multi-site edits.
- Check the downstream effect, not the exit code.
- Verification standards 1–13 apply. Standard 12 governs Task 3 specifically: an absent
  input read as satisfaction is the failure mode this sprint is most exposed to.
- **The migration-gate flake escalates here.** If it recurs, stop and investigate rather
  than re-running. A flaky gate that gets re-run is a gate being ignored.
- Task 5 may make real provider calls; nothing else in this sprint may.
- Report anything that contradicts this prompt.
