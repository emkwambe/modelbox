"""The pass threshold for provider conformance (D10) — written before the first call.

**This file exists on its own, and it is committed before any code that can
contact a provider.** That ordering is the point, and it is verifiable from git
history rather than asserted: a threshold set after the first local-model result
would be set to whatever makes that result tolerable, which is the same defect as
a test written to match current behaviour. Every other task this sprint has been
about making a claim provable; this is the one where the temptation runs the
other way, and the evidence would define the claim.

No subjective judgement is involved. The instrument already exists and has been
verified: the graph linter grades against thirteen codes and every one of them
was shown to discriminate in Task 0, *before* three claims were allowed to lean
on it. The gold graphs are the reference answers. `test_trainer_labs.py`
already establishes set-equality against linter output as a grading method, so
providers are scored with the same tool the Trainer grades students with.

---

## What is measured

For each gold graph, a provider is given the same prompt and its synthesised
model is compared with the gold graph on two axes.

**1. Lint burden.** `GraphEngine.validate` over the candidate, counted by code.
The gold graphs are not lint-free, so what matters is the *delta* against the
gold graph's own findings — not the absolute count.

**2. Structural distance.** F1 against the gold graph on three sets, each
compared case-insensitively with underscores stripped:

* entities, by name;
* columns, as `(entity, column)` pairs;
* relationships, as `(from, to, cardinality)` triples.

F1 rather than recall, deliberately. Recall alone rewards a provider that emits
every plausible entity and lets precision collapse — the failure mode of a model
told to produce a warehouse schema is over-generation, not omission.

---

## The threshold

A provider **passes** when, averaged over the gold graphs:

| Measure | Pass requires | Why this number |
| :-- | :-- | :-- |
| Entity F1 | `>= 0.80` | missing or inventing more than one entity in five makes the output a rewrite rather than a starting point |
| Column F1 | `>= 0.70` | columns are more numerous and more forgivable; a user adds a column far more cheaply than they discover a missing table |
| Relationship F1 | `>= 0.60` | the hardest part, and the one degradation is expected to concentrate in. A lower bar acknowledges that while still requiring the majority to be right |
| Lint delta | `<= +2.0` issues per graph | the linter carries thirteen codes; two extra findings is roughly one systematic omission (descriptions on a couple of entities), where a structural failure produces far more |
| New codes | no code absent from the gold graph's own findings on a **majority** of graphs — `NEW_CODE_GRAPH_COUNT`, currently `>= 4` of 6 | a code appearing once is noise; on a majority it is a systematic behaviour |

**"Materially worse than cloud" is a separate, relative test**, applied only when
a cloud provider was also scored in the same run: a drop of more than **0.15**
on any F1 axis, or more than **+2.0** additional lint issues per graph, against
the best cloud provider in that run. A gap of 0.15 is chosen because it is the
size at which a side-by-side comparison of two outputs is visibly different
rather than arguably different.

These numbers are chosen a priori and are **not to be adjusted after seeing a
result.** If a number turns out to be wrong, the honest move is to record the
disagreement, state why the original was wrong on grounds independent of the
result that provoked it, and change it in a commit of its own — not to edit it
in the commit that reports the score.

---

## What the shape of a failure means

Decided in advance, because a remedy chosen after seeing a number is chosen to
suit it:

* **Degradation concentrated in relationships or grain** — relationship F1 fails
  while entity F1 passes — indicates **staged synthesis**: entities first, then
  relationships in a second pass with the entity set fixed.
* **Degradation spread evenly** across all three axes indicates no fix at this
  layer, and the honest move is a **narrower air-gap claim**: state what the
  local path produces well and what it does not.

"Concentrated" is defined numerically to keep it out of the argument:
relationship F1 shortfall accounts for **>= 60%** of total F1 shortfall across
the three axes.

---

## Provenance recorded with every score

A quality verdict is a statement about a specific model at a specific version,
exactly as a fidelity verdict is a statement about a resolved dependency set.
Without provenance the result is not reproducible three months from now, and an
unreproducible number in a marketing claim is the thing the Proof Log exists to
prevent.

Every scored row records: provider name, egress class, model identifier, model
version as reported by the provider, the prompt's SHA-256, the gold graph id,
the linter code set, and the run timestamp. A run missing any of these is
**invalid rather than partial** — see `REQUIRED_PROVENANCE`.
"""

from __future__ import annotations

from typing import Final

# --- pass thresholds, absolute -----------------------------------------------
MIN_ENTITY_F1: Final[float] = 0.80
MIN_COLUMN_F1: Final[float] = 0.70
MIN_RELATIONSHIP_F1: Final[float] = 0.60
MAX_LINT_DELTA_PER_GRAPH: Final[float] = 2.0
# **Raised 3 -> 4 on 2026-09-01, before any run under this version.**
#
# This is the one threshold whose *meaning* depended on the size of the gold
# set. It was banked in `b6a3e1a` as ">= 3 of 5" and its published rationale was
# "on three of five it is a systematic behaviour" — a majority. `aml-financial-
# crime` made the gold set six, and 3 of 6 is not a majority; the constant did
# not move, so the gate silently loosened from "most graphs" to "half".
#
# This satisfies the a-priori rule above rather than breaking it. The ground is
# the denominator, not a score: no run has been made under the rewritten metric,
# so there is no result this could have been fitted to, and the direction is
# stricter. `THRESHOLD_VERSION` is bumped with it so a report cannot be compared
# across the change by accident.
#
# It is a count rather than a computed majority deliberately. Deriving it from
# `len(GOLD_IDS)` would make it move on its own the next time a graph lands,
# which is the property this file exists to deny a threshold — the number is
# supposed to require a decision.
NEW_CODE_GRAPH_COUNT: Final[int] = 4

# --- entity matching, structural ---------------------------------------------
# How much of two entities' column vocabulary must coincide before they are
# treated as the same table under different names. Jaccard over canonicalised
# column names, so 0.50 means "more shared columns than not".
#
# **Provenance, stated plainly because it differs from every other number in
# this file.** The pass thresholds above were fixed in `b6a3e1a`, into a tree
# containing no code able to contact a provider, and that ordering is a property
# of git history. This constant cannot claim that: it was added after the first
# run, because the first run showed the metric those thresholds were feeding was
# measuring name agreement rather than schema quality.
#
# What it can claim is that it was not tuned to a result. It is set on a stated
# principle — a table sharing more than half its columns with another is the
# same table renamed, and one sharing fewer is not — and its behaviour is pinned
# by known-answer tests over constructed graphs, not by the live report.
#
# There is also an accidental guarantee, and it is worth naming because it is
# stronger than the intention: the first run discarded every candidate graph and
# kept only scores, so there is no preserved output to tune against. The number
# could not have been fitted to that run even deliberately. The runner now
# persists candidates precisely so that a future metric change can be re-applied
# to the same outputs — which will remove this accidental protection, and makes
# the stated principle the only thing holding.
ENTITY_MATCH_FLOOR: Final[float] = 0.50

# --- "materially worse than cloud", relative ---------------------------------
MAX_F1_DROP_VS_CLOUD: Final[float] = 0.15
MAX_LINT_DELTA_VS_CLOUD: Final[float] = 2.0

# --- remedy selection --------------------------------------------------------
CONCENTRATION_SHARE: Final[float] = 0.60

# --- provenance --------------------------------------------------------------
REQUIRED_PROVENANCE: Final[tuple[str, ...]] = (
    "provider",
    "egress_class",
    "model_identifier",
    "model_version",
    "prompt_sha256",
    "gold_graph_id",
    "run_started_at",
)

# Set once, here, so the report cannot claim a threshold it did not apply.
THRESHOLD_VERSION: Final[str] = "1.1"

__all__ = [
    "CONCENTRATION_SHARE",
    "MAX_F1_DROP_VS_CLOUD",
    "MAX_LINT_DELTA_PER_GRAPH",
    "MAX_LINT_DELTA_VS_CLOUD",
    "MIN_COLUMN_F1",
    "MIN_ENTITY_F1",
    "MIN_RELATIONSHIP_F1",
    "NEW_CODE_GRAPH_COUNT",
    "REQUIRED_PROVENANCE",
    "THRESHOLD_VERSION",
]
