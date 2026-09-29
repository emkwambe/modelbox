# AML domain reference

*The vocabulary behind the `aml-financial-crime` reference model. Written for a
data professional who is competent at modelling and new to financial crime —
which is the person this model is for.*

**What this document is not.** It explains terms as they are used in the
industry so that a data model can be read and discussed. It makes no legal or
regulatory determination, states no obligation for any institution, and is not
compliance advice. Jurisdictional requirements differ, change, and are settled by
an institution's compliance function — never by a schema and never by this file.

Two boundaries are worth stating before the vocabulary, because they are what
keep the rest honest:

- **A detection is not a conclusion.** A rule firing means a condition was met.
  It does not mean money was laundered, and the model records the finding and
  its disposition rather than a verdict.
- **Filing is out of scope.** Suspicious activity reporting — a SAR in the US, a
  SAR/STR elsewhere — is a regulated act performed by people through official
  channels. Nothing here produces, prepares or substitutes for one.

---

## The chain this model represents

```
party → account → transaction → detection hit → alert → investigation → disposition
  ↑                                    ↑
KYC profile                     detection rule (versioned)
```

Read left to right, it is the life of a payment that attracted attention. Read
right to left, it is what an investigator must be able to reconstruct: why this
case exists, from which alert, from which rule firing, against which transaction,
on whose account.

That second direction is the harder requirement, and it is why the model keeps
the rule *version* rather than the rule.

---

## Parties and who they are

**Party.** Any person or organisation the institution has a relationship with.
Modelled as `dim_party` rather than "customer" because not every party is a
customer — a beneficial owner or a related director is a party the institution
must know about without holding an account for them.

**KYC — Know Your Customer.** The obligation to establish who a customer is
before and during a relationship. In data terms it is the evidence that identity
was verified, not merely asserted.

**CDD — Customer Due Diligence.** The standard level of that work: identify the
customer, understand the purpose of the relationship, and monitor it over time.

**EDD — Enhanced Due Diligence.** A deeper level applied where risk is higher —
for example a politically exposed person, an unusual ownership structure, or a
higher-risk jurisdiction. `dim_kyc_profile.due_diligence_level` records which
level applies.

**Beneficial owner.** The natural person who ultimately owns or controls a
customer, even where a chain of companies sits in between. The point of the
concept is that a company cannot be the answer to "who is behind this" — a
person must be. Modelled as a flag on `dim_party` because a beneficial owner is
itself a party, related to another party.

**Source of funds / source of wealth.** Where the money in this transaction came
from, and how the customer's overall wealth was accumulated. They are different
questions and institutions record them separately; the reference model carries
source of funds, which is the one that attaches to activity.

**Risk rating.** The institution's own assessment of a customer, usually low /
medium / high, which drives monitoring intensity and review frequency. It is an
opinion the institution owns and must be able to justify — not a fact about the
person.

---

## Activity

**Transaction.** A monetary movement. The reference model's grain is *one row per
transaction leg, per account, per counterparty*, and the direction column says
whether money came in or went out relative to the account. Grain matters more
here than in most domains: a transfer between two customers of the same
institution is one movement of money and two legs, and counting it twice is a
real reporting error.

**Counterparty.** The other side of a transaction. Modelled separately from
`dim_party` because a counterparty is usually *not* a customer of this
institution — the bank knows a name and an institution, not a verified identity.

**Channel.** How the transaction was initiated — card, faster payment, wire,
branch. Channel matters analytically because normal behaviour differs sharply
between them.

**Device and identifier.** The device fingerprint or network address a
transaction was initiated from. Individually unremarkable; the analytical value
is in *sharing* — several nominally unrelated customers transacting from one
device is a linkage signal, and is the basis of mule-network analysis.

---

## Detection and what follows

**Transaction monitoring.** Evaluating activity against defined conditions to
surface what merits review. The reference model treats it as transparent rules
over declared features rather than an opaque classifier, because a detection
nobody can explain is not usable as evidence.

**Detection rule, and why the version matters.** A rule is a condition plus a
threshold plus a period during which it was in force. `dim_detection_rule`
carries `rule_version`, `threshold_value`, `effective_from` and `effective_to`
for one reason: six months later, the question is not "what does this rule say"
but "what did it say *when it fired*". A model that stores only the current
threshold cannot answer that, and cannot be back-tested honestly.

**Detection hit.** One firing of one rule version against one transaction. It is
immutable by intent — a hit records what was true when the rule ran, and
recalculating it later would destroy the evidence it exists to be.
`observed_value` stores what the rule actually saw, so a reviewer can compare it
against the threshold without re-running anything.

**Alert.** The unit of analyst work, created by grouping one or more hits.
Grouping exists because ten hits on one customer in one day is one thing to look
at, not ten. Alert volume is the operational currency of a financial crime team.

**Investigation / case.** The work performed on an alert: gathering context,
reviewing history, forming a view.

**Disposition.** How the investigation ended. Codes are configurable per
institution, and typically include a false positive, activity explained by the
customer's known profile, or escalation for further action. The reference model
records the decision and the stated reason — it does not make the decision and
does not model what happens after an escalation.

**False positive rate, and why it dominates everything.** Rule-based monitoring
is widely reported to produce very high false-positive rates, so most alerts are
resolved without further action. This is the central operational fact of the
domain: tuning a threshold is not a tidiness exercise, it changes how many people
spend how many hours on work that finds nothing. It is also why disposition data
is analytically precious — it is the only ground truth most institutions have.

---

## Typologies — the patterns rules look for

Named here because the vocabulary recurs, and because a data modeller is often
asked to support them without being told what they mean.

| Typology | What it looks like in data |
| :-- | :-- |
| **Structuring / smurfing** | Many transactions individually below a reporting threshold that together exceed it |
| **Rapid movement / pass-through** | Funds arriving and leaving quickly, with little balance retained |
| **Fan-in / fan-out** | Many sources paying one account, or one account paying many — a concentration pattern |
| **Dormant reactivation** | An account with little history suddenly transacting at volume |
| **Circular flow** | Funds returning to their origin through intermediaries — a cycle in the transaction graph |
| **Shared-identifier clusters** | Separate customers linked by a common device, address or contact detail |

Each is a *hypothesis about behaviour*, not a definition of crime. All of them
have innocent explanations, which is exactly why the chain ends in a human
disposition rather than a score.

---

## Governance vocabulary

**Model risk management.** Monitoring systems are typically treated as models
under supervisory expectations, which brings requirements for documentation,
independent validation and ongoing monitoring. The practical consequence for a
data team: the lineage from source record to feature to rule output has to be
reconstructable by someone who did not build it.

**Tuning, and above/below-the-line testing.** Adjusting thresholds and testing
the effect: sampling alerts just above the threshold to see whether they were
productive, and activity just below it to see what would have been missed.
Sampling below the line is the half that tells you what you are not catching.

**Auditability.** The ability to show what the system did and why, after the
fact. In this model it is served by three deliberate choices — versioned rules,
immutable hits, and a recorded disposition with a reason.

---

## How this maps to the reference model

| Concept | Entity |
| :-- | :-- |
| Party, beneficial owner | `dim_party` |
| KYC / CDD / EDD profile | `dim_kyc_profile` |
| Account and product | `dim_account` |
| Counterparty | `dim_counterparty` |
| Device / identifier | `dim_device` |
| Transaction | `fact_transaction` |
| Detection rule and version | `dim_detection_rule` |
| Detection hit | `fact_detection_hit` |
| Alert | `dim_alert` |
| Investigation / case | `dim_investigation` |
| Disposition | `dim_disposition` |

Two modelling choices in that table are worth defending, because they are the
ones a reviewer will question.

**Alert, investigation and disposition are dimensions, not facts.** The
measurable event is the detection hit; the alert and the case are the
descriptive context it is grouped into. Modelling them as facts would put
fact-to-fact joins through the middle of the star — the chasm trap, which
inflates any measure aggregated across the join, and which this appliance's
`FAN_OUT_RISK` lint exists to catch.

**`fact_detection_hit` points at its transaction by reference, not by foreign
key.** `transaction_reference` is a degenerate dimension for the same reason. The
evidence link is preserved; the join that would corrupt the arithmetic is not.

---

## What this model does not attempt

Consistent with the expansion document's boundaries, and worth stating where a
reader will look for it:

- No sanctions or PEP screening list, and no screening logic.
- No suspicious activity report, in any jurisdiction's format.
- No case-management workflow — the model records that work happened and how it
  ended, not the queues, assignments and approvals that constitute a case system.
- No claim that these detections satisfy any institution's obligations. A
  reference model is a starting point for a conversation with compliance, not a
  substitute for one.
- No requirement for real customer data. The model is designed to be exercised
  with synthetic data, which is what makes it safe to share and to teach from.
