# AML expansion — IR gap analysis and assessment

*Written 2026-08-27 against `sprint/5-governance` at `0c6daf8`. Inputs:
`ModelBox_AML_Analytics_Expansion_Considerations.docx` (§4.1–§4.8),
`02 After the AML expansion.md`, and `backend/app/schemas/data_model.py`.*

Two questions, answered separately because they fail differently: **can the IR
express the AML ontology**, and **is the expansion worth doing**. Code claims
below carry a `file:line`; market claims carry a source link and are labelled as
research rather than repository fact.

---

## Part 1 — The IR as it stands

The complete field inventory, because the gap analysis is only as good as this
list (`backend/app/schemas/data_model.py`).

**`ColumnSchema`** (`:436`) — `name`, `data_type`, `stable_id`,
`is_primary_key`, `is_foreign_key`, `is_pii`, `pii_type`, `description`,
`ordinal_position`, `references`, `is_metric`, `aggregation`, `min_value`,
`max_value`, `regex_pattern`, `is_nullable`, `is_unique`, `default_value`,
`check_expression`.

**`EntitySchema`** (`:544`) — `entity_name`, `entity_type` (TABLE · FACT ·
DIMENSION · HUB · LINK · SATELLITE), `description`, `grain`, `tier`,
`freshness_sla`, `agg_time_column`, canvas position, `columns`.

**`RelationshipSchema`** (`:637`) — `from_ref`, `to_ref`, `cardinality`. Three
fields.

**`SynthesizedModel`** (`:672`) — `paradigm`, `entities`, `relationships`,
`suggested_metrics`. **`SuggestedMetric`** is `name` · `formula` · `group_by`.

`PIIType` (`:408`) has seven members: EMAIL, SSN, PHONE, CREDIT_CARD, IBAN,
NAME, ADDRESS.

### What carries over unchanged

More than the expansion doc credits. The canonical AML schema in §4.1 — party,
account, transaction, counterparty, device, KYC profile — is **ordinary
relational modelling**, and the IR models it today with no change at all:

- **`grain`** is already mandatory-by-lint on facts, which is exactly the
  discipline a transaction or alert fact needs.
- **Quality rules** (`min_value` / `max_value` / `regex_pattern` /
  `check_expression`) express real AML data contracts: amount ≥ 0, ISO-4217
  currency pattern, ISO-3166 country codes.
- **`tier` + `freshness_sla`** map directly onto AML feed criticality — a
  transaction feed is TIER_1 with an intraday SLA, and `MISSING_SLA` already
  lints for it.
- **`stable_id`** is unusually well-suited: detection hits and alerts are
  published as event contracts, and a column identity that is never reused is
  what makes an Avro/Protobuf detection schema safe to depend on (PL-006).
- **DATA_VAULT** with HUB/LINK/SATELLITE is the auditable-history paradigm §5
  asks for, and it already round-trips.
- **PII flags** carry the privacy story the pack needs.

So phase 1 of the doc's sequence — "canonical AML model" — needs **no IR change
whatsoever**. That is the good news, and it is worth saying loudly because it
makes phase 1 cheap and immediately demonstrable.

### The gaps

Ranked by how much of the expansion each one blocks.

| # | AML concept | IR today | Verdict |
|---|---|---|---|
| G1 | Temporal validity — rule versions with effective periods, KYC risk history, as-of back-testing | nothing | **None** |
| G2 | Role-qualified relationships — originator vs beneficiary, both FK to Party | `from_ref`/`to_ref`/`cardinality` only | **None** |
| G3 | Derivation lineage — source → feature → rule → hit → alert | FK edges only | **None** |
| G4 | Versioned definition objects — features and rules with parameters, windows, owner, validation status | `SuggestedMetric`: 3 fields | **Trace** |
| G5 | Windowed aggregation — rolling 7d count, 30d sum | `aggregation` is a scalar (SUM/AVG) | **None** |
| G6 | Immutability — a detection hit is append-only | not expressible | **None** |
| G7 | Enumerations — dispositions, channels, directions | `check_expression` IN-list | **Partial, known-fragile** |
| G8 | Money — amount is meaningless without currency and FX basis | no unit metadata | **None** |
| G9 | Entity resolution — shared device/address clustering | no notion of a resolved cluster | **None** |
| G10 | Data-level graph projection — components, cycles, degree over transactions | NetworkX runs on the *schema* graph | **None** |
| G11 | Ownership, retention, jurisdiction | no `owner` field anywhere in the IR | **None** |
| G12 | KYC identifier taxonomy — DOB, passport, national ID, beneficial ownership | 7 PII types, none of them these | **Partial** |

Six of these deserve more than a table row.

**G1 — temporal validity is the one that blocks the most.** §4.5's whole
proposition is "change a threshold and see how the population changes", and
§11's reproducibility metric is "same version + parameters → same analytical
result". Both require as-of semantics: which rule version was in force, which
KYC risk rating applied on the transaction date. The IR has exactly one time
concept, `agg_time_column` (`:571`), and it is a *single* axis per entity chosen
for MetricFlow's `defaults.agg_time_dimension`. There is no validity interval,
no event-time/ingestion-time distinction, and no bitemporality. A SATELLITE
entity type exists but carries no load-date or effectivity fields — the
paradigm's shape without its semantics.

**G2 is an open defect being promoted to a requirement.** Two foreign keys from
one entity to the same parent already produce two foreign entities with the same
name, distinguished only by `expr` — logged in Sprint 3, carried untouched
through Sprint 4 (`sprint-4-progress.md:139`), and unhit only because *no gold
graph has two FKs to one parent*. Every AML transaction table has exactly that
shape: originator and beneficiary both point at Party. AML does not encounter
this edge case, it is built on it. The fix the earlier sprints identified —
separate semantic models per role — becomes mandatory.

**G3 and G4 together are the structural finding.** The IR describes **schemas**:
things with tables, columns and keys. §4.3, §4.5 and §4.7 need something the IR
has no category for — **definitions** (a feature with a lookback window and a
version; a rule with parameters, a threshold and an effective period) and
**derivations** (this feature was computed from those fields; this hit was
produced by that rule version over that dataset version). `SuggestedMetric` is
the only definition-shaped object in the IR and it has three fields, no version
and no lineage. Closing this is not "more fields on `ColumnSchema`" — it is a
second object family alongside entities and relationships.

**That is the load-bearing conclusion of this analysis.** It also settles where
the work belongs: a definition/derivation family added to `data_model.py` would
put AML-shaped concepts into the horizontal core, which is precisely the
"domain-pack coupling" risk §13 names. It argues for the pack interface being
built **first**, not in phase 7.

**G6 has a precedent worth copying.** The appliance already runs an append-only
ledger where the write provably precedes the act, with structural tests proving
nothing can bypass it (D3, PL-008). That is exactly the guarantee a detection
hit needs. The pattern exists; it is hand-built in the ORM and not expressible
in the IR.

**G7 is a scar, not a guess.** Sprint 4's H11 found the dbt `accepted_values`
test contradicting the model's own `CHECK` — a valid artifact saying the wrong
thing, and the reason cross-artifact consistency became standard 10. AML
multiplies enumerations (dispositions, channels, directions, escalation
outcomes), so it multiplies that exact failure. Enumerations want to be a first
-class IR construct before the pack, not after.

---

## Part 2 — Assessment

### Relevance: strong, and regulator-driven rather than fashionable

The doc's highest-value claim (§4.5, threshold simulation and back-testing) is
not a nice-to-have. Above-the-line/below-the-line testing is an **examination
expectation**, and third-party BSA/AML monitoring solutions used for detecting
suspicious activity generally constitute a *model* under SR 11-7, pulling them
into model-risk validation. The pain is quantified: rule-based transaction
monitoring runs **85–99% false positives**, institutions spend **$54bn+ a year**
on transaction-monitoring operations of which 60–80% is labour, and global AML
compliance cost is put north of **$274bn**. A tool that lets a team try a
threshold change *before* it reaches production, against a dataset with known
ground truth, is aimed at a real and expensive problem.

Use case 17 in the second document — a reproducible environment for
independently challenging analytical logic — is the sharpest item in either
document, because independent validation is a regulatory requirement with a
budget attached, and validators are structurally short of safe data.

### Market: real, but do not quote the big number

Transaction monitoring is roughly **$23bn in 2026 growing ~16% CAGR**. That
figure is not ModelBox's addressable market and should never appear beside its
name: ModelBox does not monitor transactions, and the doc is right that it must
not. The relevant budget is the much smaller design-, prototyping-, validation-
and modernisation-adjacent spend. Quoting the monitoring market as if it were
the opportunity is the exact species of overclaim register rule E2 exists to
prevent.

### Coherence: high internally, with two seams

The expansion reuses what exists rather than duplicating it, and §7's "do not
build" list is disciplined — no SAR filing, no screening, no case management, no
black-box classifier. That restraint is what makes the document credible.

Two seams:

**The pack interface does not exist.** `domain_packs/aml/` would be the first
thing in the repository that is neither `backend/` nor `frontend/`. Phase 7's
exit condition — "installs and runs without altering core platform semantics" —
is an architectural precondition dressed as a final step. Combined with G3/G4 it
is the strongest argument for re-sequencing.

**Two parallel quality regimes.** §11's success metrics are the acceptance
register renamed: "% generated artifacts that parse/execute" *is* the fidelity
harness (B1); "same version + parameters → same result" *is* PL-005; "reference
workflows require no production PII" *is* D6. The pack should extend the
register and the harness, not stand up a second scorecard — otherwise there are
two definitions of done and, by precedent, they will disagree.

### Feasibility: phase-dependent, and the doc's order is backwards

- **Phase 1 (canonical model)** — feasible now, no IR change. Days.
- **Phase 2 (synthetic scenarios)** — the seed generator already reads declared
  constraints and `dbt build` runs on its output (B13). Embedding *typologies*
  with ground-truth labels is new work but sits on a working base.
- **Phases 3–6 (features, detections, graph, tuning)** — blocked on G1, G3, G4,
  G5. This is where the real cost is, and it is not a domain-content cost; it is
  an IR-architecture cost.
- **Phase 7 (productization)** — should be phase 0.

The air-gapped profile the doc leans on as a core AML deployment mode is Sprint
5 work sitting **unmerged**, with D4, D10, G1 and G2 open. It is also the claim
with the best external support: regulated buyers increasingly require deployment
isolation and tamper-evident audit logging of every request, and one source is
blunt that an "on-premise" deployment that phones home is a compliance fiction —
which is exactly the distinction the appliance's structural egress tests already
make. **Finishing Sprint 5 is a prerequisite for the AML pitch, not a parallel
track.**

### Differentiation: three of the headline capabilities are occupied

This is the part the expansion document is weakest on, and it should be faced
squarely.

- **Synthetic AML data is a crowded field.** AMLSim (IBM), SAML-D (28
  typologies), PaySim, SynthAML, AMLWorld, AMLGentex and AMLNet all exist, most
  open-source and academically benchmarked. "We generate synthetic AML data" is
  not a differentiator against that field.
- **Back-testing and shadow mode are table stakes.** Unit21, Hawk AI, Feedzai
  and Napier already ship rule back-testing, shadow mode and sandbox rule
  testing. A "tuning lab" is not a new category.
- **Reference AML data models exist.** Databricks ships an open-source AML
  solution accelerator, partners ship pre-built AML models, and FIBO is a
  2,446-class standardised financial ontology explicitly used for KYC and AML.

What is *not* occupied, and what ModelBox uniquely has:

1. **Artifacts proven to execute by the tool that consumes them.** The fidelity
   harness hands real files to `dbt`, `protoc`, `fastavro`, `sqlfluff` and
   DuckDB. Nobody in the AML accelerator space asserts artifact correctness that
   way.
2. **One domain, four paradigms, generated.** 3NF, Kimball and Data Vault from
   the same declared model, with a semantic diff between versions.
3. **Air-gapped by construction, with structural proof.** Not a deployment
   option — a tested property.
4. **Evidence lineage as a product primitive**, with an append-only ledger
   already proving the pattern.

The vendors do detection at runtime on the institution's real data. ModelBox
does *design and validation before there is production data at all*. That is a
defensible position, and it is the one sentence the positioning should lead
with — §8 gestures at it but buries it under a longer list.

**Recommendation on FIBO:** align the ontology's naming and semantics to FIBO
rather than inventing one. It costs little, it is the vocabulary a bank's data
architects already recognise, and it converts "we made up an AML schema" into
"we generate a FIBO-aligned AML schema across three paradigms". Use it as a
reference for naming and relationships, not as an OWL import — 2,446 classes is
not a dependency to take on.

### Portfolio relevance

Demand is real and the listed skills — SQL, data analysis, UAT, regulatory
awareness, ML familiarity — are what the pack would demonstrate end to end. The
doc's §12 framing (demonstrate competence, do not claim investigative
experience) is the right and honest one.

---

## What I would change in the plan

1. **Make the pack interface phase 0.** G3/G4 need a new object family; without
   a seam it lands in `data_model.py` and contaminates the horizontal core —
   the risk §13 already names.
2. **Ship phase 1 immediately and separately.** It needs no IR change, it is
   days of work, and it makes the whole direction concrete and inspectable.
3. **Finish Sprint 5 before pitching the air-gap story.** It is the best-
   supported claim in the document and it is not on `main`.
4. **Fix G2 as its own piece of work.** It is already an open defect; AML just
   removes the option of continuing to ignore it.
5. **Extend the register and the fidelity harness. Do not write a second
   scorecard.**
6. **Cut the first release below §10.** One canonical schema, two paradigms from
   it, one typology end-to-end with ground truth, one graph finding that links
   back to source transactions, one threshold comparison. Five typologies and
   five detections is a second release.
7. **Lead the positioning with pre-production design and validation**, and drop
   any framing that implies a share of the monitoring market.

---

## Sources

Research claims above, in order of use. Repository claims are cited inline by
`file:line` instead.

- [Mordor Intelligence — Transaction Monitoring Market Size & Drivers 2026–2031](https://www.mordorintelligence.com/industry-reports/transaction-monitoring-market)
- [FFIEC BSA/AML Examination Manual](https://bsaaml.ffiec.gov/manual)
- [Axle — Transaction Monitoring Rules Tuning: A Practical Guide (ATL/BTL)](https://www.axleruns.com/post/transaction-monitoring-rules-tuning)
- [Carr, Riggs & Ingram — BSA/AML Model Validation: Understanding Expectations](https://www.criadv.com/insight/bsa-aml-model-validation-risk-management/)
- [RSM — How independent validations enhance your AML system](https://rsmus.com/insights/services/risk-fraud-cybersecurity/how-independent-validations-enhance-the-beauty-of-your-aml-syste.html)
- [Facctum — AML False Positive Rates 2026 Report](https://www.facctum.com/blog/aml-false-positive-report)
- [Yahoo Finance — The hidden cost of AML: how 95% false positives hurt banks](https://finance.yahoo.com/news/hidden-cost-aml-95-false-134601048.html)
- [IBM AMLSim — Overview](https://github.com/IBM/AMLSim/wiki/Overview)
- [Bournemouth — Development of a Synthetic Transaction Monitoring Dataset (SAML-D)](https://eprints.bournemouth.ac.uk/40982/1/Full_IEEE_Dataset_Conference_Paper%20(4).pdf)
- [AMLgentex — Mobilizing Data-Driven Research to Combat Money Laundering](https://arxiv.org/pdf/2506.13989)
- [Unit21 — AML Transaction Monitoring (shadow mode, back-testing)](https://www.unit21.ai/products/aml-transaction-monitoring)
- [cside — The 10 best transaction monitoring software platforms in 2026](https://cside.com/blog/best-transaction-monitoring-software)
- [Databricks — AML Solutions at Scale Using the Lakehouse Platform](https://www.databricks.com/blog/2021/07/16/aml-solutions-at-scale-using-databricks-lakehouse-platform.html)
- [Databricks Industry Solutions — anti-money-laundering accelerator](https://github.com/databricks-industry-solutions/anti-money-laundering)
- [EDM Council — FIBO](https://edmcouncil.org/frameworks/industry-models/fibo/)
- [FIBO on GitHub](https://github.com/edmcouncil/fibo)
- [Maxim — Best LLM Gateways for Healthcare, Financial Services and Government in 2026](https://www.getmaxim.ai/articles/best-llm-gateways-for-healthcare-financial-services-and-government-in-2026/)
- [ZipRecruiter — AML Data Analyst jobs, August 2026](https://www.ziprecruiter.com/Jobs/Aml-Data-Analyst)
- [Fintech Careers — Entry-level AML analyst jobs: skills employers expect in 2026](https://www.fintechcareers.com/blog/entry-level-aml-analyst-jobs-skills-employers-expect-in-2026/)
