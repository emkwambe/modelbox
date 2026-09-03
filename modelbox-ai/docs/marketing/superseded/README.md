# Superseded evidence

Artifacts kept for provenance that **must not be read as current**, and must
never be cited on a public surface.

## `conformance-report-v1.0-invalidated.json`

The first provider conformance run, 2026-08-13. One cloud provider
(`claude-sonnet-4-5-20250929`), **five** gold graphs, five real provider calls.

It reports entity F1 0.288, column F1 0.074, relationship F1 0.200, and
`passed: false`. **Those numbers do not mean what they appear to mean, and the
run itself is what established that** — see `sprint-5-progress.md:684-935`. The
metric was measuring name agreement and prompt poverty rather than schema
quality: `ecommerce-orders` scored 0.857 on entities and `saas-subscription`
0.000 on two near-identical Kimball tasks, which is one model naming things
differently, not a model that comprehends one domain and fails completely at the
other. `marketing-attribution` scored a free 1.000 on a relationship axis with
nothing on either side to judge, averaged in beside graphs that were actually
judged.

Three things have changed since, any one of which makes a comparison invalid:

* **The metric was rewritten** (`8c54a71`) to match entities by column-vocabulary
  overlap rather than by name, and to exclude an inapplicable axis rather than
  score it 1.0.
* **The prompts were rewritten** (`6fb04e1`) to carry `target_paradigm` and a
  domain description per graph. The old run measured, in part, how well a model
  guesses a paradigm it was never told.
* **The threshold changed** (`8ba4f9a`): `NEW_CODE_GRAPH_COUNT` 3 → 4, restoring
  the majority rule the sixth gold graph had silently turned into a minority.
  `THRESHOLD_VERSION` is now **1.1**; this file is stamped **1.0**.

It moved out of `docs/marketing/` on 2026-09-01 because that directory is
reserved for public claims, and a file holding invalidated numbers in it is the
exact failure `PROOF_LOG.md` exists to prevent, pointing the other way. The
version stamp makes a bad comparison *detectable*; moving it makes one unlikely.

**Do not delete it.** D10's whole method is that the threshold was fixed before
the first call, and this is the record of that first call.

## `conformance-report-2026-09-02-no-system-prompt.json`

The first run to complete. Six gold graphs, `claude-sonnet-5`, six successful
provider calls, and a clean FAIL on every axis — entity F1 0.230, column F1
0.069, relationship F1 0.013, lint delta +5.17 per graph.

**It does not describe this product, and the numbers are worse than the truth.**
The harness called `structured_completion` without `system_prompt`. That
argument defaults to `None`, so the call succeeded and nothing looked wrong —
but none of the product's instructions reached the model: not the Kimball rule
that a Fact → Dimension edge must be `N:1`, not the 3NF bridge-table rule, and
not the omission guidance that exists to stop a model inventing governance terms.

The output shows it plainly. Relationship F1 of 0.013 is what happens when the
cardinality rules are never sent, and **every entity in the `ecommerce-orders`
candidate carries an invented `tier`** — the S5-2 defect reproduced in full,
because the paragraph forbidding it was not in the request. The report then
recorded `MISSING_SLA` as a systematic *provider* behaviour. It was not the
provider's behaviour; it was ours.

What it measured is a bare model handed a domain description. That is a
legitimate thing to measure and it is not what D10 asks for.

Kept, not deleted, for two reasons. It is the record of a real run against a
real provider — the candidates file holds all six graphs verbatim — and it is
the *baseline without a system prompt*, which makes the difference the prompt
makes measurable rather than assumed. Do not cite it as a conformance verdict.

`test_conformance_sends_the_prompt.py` now fails if the harness stops sending
the prompt again.
