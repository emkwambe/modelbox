"""Prompts for the size x domain experiment — the two cells that did not exist.

## What this experiment is for

`aml-financial-crime` is the only graph where both models produced materially
worse output than the hand-built reference (~+1.1 linter findings per entity,
including a cyclic foreign key and unmarked PII). It is also **both** the
largest graph and the most specialised domain, and nothing run so far separates
those. Two literatures predict opposite causes:

* The domain-modelling line predicts damage concentrated in the **relationship
  layer** regardless of domain — single-prompt association F1 0.119 against
  entity F1 0.534. On that reading AML is not special, merely large enough for
  that layer to fail visibly, and decomposition is the fix.
* The finance and legal benchmarks predict **specialisation** is the driver.
  Spider-DK costs 20-32 points with size held roughly constant; of GPT-4's 44
  errors on BizBench, zero were extraction or syntax and 37 were business and
  financial knowledge. On that reading a *small* AML model is already dirty, and
  domain knowledge is the fix.

They disagree, they point at different sprints, and one run separates them.

## The design

Two factors, two levels each. Two cells already have descriptions in
`conformance_prompts.py` and are reused verbatim rather than rewritten, so the
existing cells are the ones already measured:

|            | commodity domain      | specialised domain    |
| :--        | :--                   | :--                   |
| **small**  | `ecommerce-orders` *  | `aml-small` (new)     |
| **large**  | `retail-supply` (new) | `aml-financial-crime` * |

`*` reused from the D10 description set.

**The prediction is registered here, before the run.** If size drives the
damage, `retail-supply` is dirty and `aml-small` is clean. If specialisation
drives it, `aml-small` is dirty and `retail-supply` is clean. If both cells are
dirty the factors are additive and neither literature is wholly right; if
neither is, the AML result is about that specific domain rather than either
factor, and the next step is a third specialised domain.

## The calibration rule, inherited unchanged

> **State the business domain, each entity's purpose, and the grain of the
> central fact. Do not name entities, columns, or relationships.**

Enforced the same way, by the same check: no snake_case token and no gold entity
name may appear. Business prose contains no snake_case, so the test is cheap and
exact. See `test_experiment_prompts.py`.

**The new descriptions were written to a target entity count, not to a target
answer.** `retail-supply` describes a domain a competent modeller would render
in roughly a dozen tables and `aml-small` one they would render in about four —
that is the factor being manipulated, and it has to be manipulated deliberately
or the cell does not exist. Neither names a table. `aml-small` is a genuine
subset of anti-money-laundering work rather than a simplified caricature,
because a caricature would confound "small" with "easy" and destroy the
contrast the whole design rests on.
"""

from __future__ import annotations

from typing import Final

from scripts.conformance_prompts import DESCRIPTIONS as _D10_DESCRIPTIONS

#: ``cell id -> (paradigm, description, size, domain, target entity count)``.
#: The target count is the design intent, recorded so a reader can check the
#: manipulation worked; nothing scores against it.
CELLS: Final[dict[str, tuple[str, str, str, str, int]]] = {
    "ecommerce-orders": (
        "KIMBALL",
        _D10_DESCRIPTIONS["ecommerce-orders"],
        "small",
        "commodity",
        3,
    ),
    "aml-financial-crime": (
        "KIMBALL",
        _D10_DESCRIPTIONS["aml-financial-crime"],
        "large",
        "specialised",
        12,
    ),
    "retail-supply": (
        "KIMBALL",
        # Large, deliberately ordinary. Everything here is the kind of retail
        # supply chain that appears in every warehousing textbook, so a model
        # that struggles cannot be said to lack domain knowledge — which is
        # exactly what makes it the control for size.
        (
            "A national retail chain analysing how goods move from suppliers to "
            "stores and out to customers. Analytics cover what was bought and from "
            "whom, what was shipped and by which carrier, what is held where, what "
            "sold in which store, which staff member handled the sale, which "
            "promotion applied, and how returns flow back. The business tracks "
            "suppliers and the agreements held with them, the goods themselves and "
            "the categories they belong to, the warehouses and stores that hold "
            "them, the carriers that move them between the two, the staff who work "
            "in each store, the promotional campaigns that run over defined "
            "periods, and the calendar those campaigns and shipments are reported "
            "over. The central measurement is one line of one sale in one store on "
            "one day, carrying quantity, price paid, discount given and margin. A "
            "second measurement records one delivery of one product from one "
            "supplier into one warehouse, carrying quantity received, quantity "
            "rejected and the cost paid."
        ),
        "large",
        "commodity",
        12,
    ),
    "aml-small": (
        "KIMBALL",
        # Small, and genuinely specialised. A real and self-contained slice of
        # AML work — sanctions and politically-exposed-person screening — not a
        # simplified version of the twelve-entity graph. The jargon load per
        # entity is comparable; only the entity count differs.
        (
            "A bank screening the parties it deals with against sanctions lists and "
            "registers of politically exposed persons, as required by its financial "
            "crime obligations. Analytics cover which party was screened against "
            "which list, on what date, how closely the name matched, whether an "
            "analyst confirmed or dismissed the match, and how long confirmation "
            "took. The business tracks the parties it screens and the identifying "
            "details held on them, the watch lists it screens against and who "
            "publishes each one, and the calendar screening is reported over. The "
            "central measurement is one screening of one party against one list on "
            "one day, carrying the match score, the outcome the analyst reached, "
            "and the hours taken to reach it."
        ),
        "small",
        "specialised",
        4,
    ),
}

__all__ = ["CELLS"]
