"""Conformance prompts (D10) — the domain descriptions, and the rule they obey.

**These do not live in the gold fixtures.** The gold graphs are extracted from
`frontend/src/lib/templates.ts` with a drift guard that re-extracts and diffs, so
a `description` field added to the JSON would fail that guard — and the graphs
are a curriculum and marketing asset that must not be edited to suit a harness.
The descriptions are therefore keyed by graph id here.

---

## The calibration rule

Fixed before any description was written, for the same reason the threshold was
fixed before any provider call: a description authored while looking at the gold
entity list drifts toward naming it. Not through bad faith — through proximity.

> **State the business domain, each entity's purpose, and the grain of the
> central fact. Do not name entities, columns, or relationships.**
> Pass `target_paradigm` explicitly, since the product's own API carries it.

Too thin measures prompt poverty; too rich measures transcription. The target is
a description from which a competent data modeller could plausibly arrive at the
gold entity set without being handed it.

The rule is **enforced, not merely stated** —
`test_conformance_prompts.py::test_no_description_leaks_a_schema_identifier`
fails on any snake_case token or any gold entity name appearing verbatim.
Business prose contains no snake_case, so that check is both cheap and exact.

## The paradigm is supplied, not withheld

Four paradigms across five graphs, and the naming conventions differ completely
between them — `hub_`/`lnk_`/`sat_` is Data Vault convention, not a fact about
banking. `SynthesizeRequest` carries `target_paradigm` precisely because it is
not inferable, so withholding it would test something the product never asks a
model to do, and would score the guess rather than the model.

## Well-posedness judgement, recorded before the run

Could a competent data modeller, given only the prompt text **and the
paradigm**, plausibly arrive at the gold entity set?

| Graph | Paradigm | Verdict |
| :-- | :-- | :-- |
| `ecommerce-orders` | KIMBALL | Yes — two descriptive concepts and a per-item sale event is a conventional star |
| `saas-subscription` | KIMBALL | Yes — two descriptive concepts and a monthly snapshot |
| `healthcare-ehr` | 3NF | Yes — four operational concepts, stated as normalised with no central fact |
| `banking-datavault` | DATA_VAULT | Yes, **once the paradigm is given.** Two business concepts, an association between them, and separately-historised descriptive attributes maps onto hub/link/satellite by Data Vault convention |
| `marketing-attribution` | OBT | Yes, **once the paradigm is given.** A single wide interaction row is the OBT answer; without the paradigm the default answer is a star, which is why this was unanswerable before |

**No graph is excluded.** The two previously judged not well-posed —
`banking-datavault` and `marketing-attribution` — become answerable once the
paradigm is supplied, and neither description names an entity to get there. Had
either required naming one, the exclusion rule applies: drop it from conformance
with the reason recorded, rather than include it at a discount, because a graph
scored against a prompt that gave away the answer measures transcription and
averaging it hides that inside a mean.
"""

from __future__ import annotations

from typing import Final

PROMPT_TEMPLATE: Final[str] = (
    "Design a data warehouse schema for the domain below, in the "
    "{paradigm} paradigm.\n\n"
    "{description}\n\n"
    "Return entities with their columns and the relationships between them."
)

DESCRIPTIONS: Final[dict[str, str]] = {
    "ecommerce-orders": (
        "An online retailer selling physical goods, which needs analytics over "
        "what was sold, to whom, and at what value. The business tracks the "
        "people who buy from it, the goods it offers for sale, and the "
        "individual sale events themselves. The grain of the central fact is a "
        "single item on a single purchase — not the purchase as a whole, since "
        "one purchase may contain several different goods, each priced and "
        "counted separately."
    ),
    "saas-subscription": (
        "A subscription software business billing its customers on a monthly "
        "cycle. Analytics cover recurring revenue, the mix of commercial tiers "
        "in use, and attrition. The business tracks the organisations that "
        "subscribe, the commercial tiers they can be placed on, and the billing "
        "outcome for each period. The grain of the central fact is one "
        "subscribing organisation's position in one calendar month — a periodic "
        "snapshot rather than an event, because revenue here is measured per "
        "period rather than per transaction."
    ),
    "healthcare-ehr": (
        "A hospital electronic health record, designed for operational "
        "integrity rather than analytics, so each concept is stored once and "
        "referenced rather than repeated. The system records the people "
        "receiving care, the clinicians delivering it, the clinical visits at "
        "which the two meet, and the conditions identified during those visits. "
        "There is no central fact table in this design, but the grain still "
        "needs stating: one row of the visit concept is a single person "
        "receiving care from a single clinician at a single point in time, and "
        "one row of the condition concept is one condition identified at one "
        "such visit — a visit may yield several."
    ),
    "banking-datavault": (
        "A retail bank's core ledger, modelled for auditability and for "
        "tolerating change in the source systems that feed it. There are two "
        "core business concepts: the people who bank, and the accounts they "
        "hold. Money movement is an association between those concepts and "
        "occurs many times over an account's life. Descriptive attributes of an "
        "account — its type, its status, its balance figures — change "
        "independently of the account's identity and must be historised "
        "separately from it, so that a change of attribute never rewrites the "
        "record of the thing itself. The grain of the association is one "
        "movement of money."
    ),
    "marketing-attribution": (
        "A digital marketing team analysing which channels and campaigns drive "
        "conversions. Every interaction a prospect has with the brand — an ad "
        "impression, a click, an email open, a site visit — is recorded "
        "together with the campaign, channel, device and cost context "
        "surrounding it, and with whether and when that interaction ultimately "
        "led to a conversion. Analysts slice across all of that context at once "
        "and the design deliberately keeps it on one wide row so that no joins "
        "are required. The grain is one interaction by one prospect at one "
        "point in time."
    ),
}


def build_prompt(paradigm: str, description: str) -> str:
    return PROMPT_TEMPLATE.format(paradigm=paradigm, description=description)


__all__ = ["DESCRIPTIONS", "PROMPT_TEMPLATE", "build_prompt"]
