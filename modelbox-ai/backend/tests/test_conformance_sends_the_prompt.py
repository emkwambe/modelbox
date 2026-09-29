"""The conformance harness sends the product's system prompt (D10).

Written after a run that produced a number and published it. The harness called
`structured_completion` without `system_prompt`; the gateway defaults that
argument to `None`, so the call succeeded, six graphs scored, and a report
landed in `docs/marketing/` describing something other than this product.

What it actually measured was a bare model handed a domain description. None of
the modelling instructions reached the provider — not the Kimball rule that a
Fact → Dimension edge must be `N:1`, not the 3NF bridge-table rule, and not the
omission guidance written specifically to stop a model inventing governance
terms it was never given.

The 2026-09-02 numbers show the cost. Relationship F1 came back at **0.013**
with the cardinality rules unsent, and every entity in the `ecommerce-orders`
candidate carried an invented `tier` — the S5-2 defect reproduced in full,
because the paragraph forbidding it was never sent. The report then recorded
`MISSING_SLA` as a *systematic provider behaviour*. It was not a provider
behaviour; it was ours.

**Why an assertion rather than a comment.** The defect was invisible for the
same reason it was easy to make: an omitted keyword argument with a default
leaves no trace at the call site, in the output, or in the report. Nothing was
broken, so nothing failed — the run simply answered a different question and
reported the answer under D10's name. Only a test that reads what is actually
sent can see that.
"""

from __future__ import annotations

import inspect

from app.services.synthesis_engine import _SYSTEM_PROMPT
from scripts import run_provider_conformance


def test_the_harness_passes_a_system_prompt() -> None:
    """Read at the call site, because that is where the argument went missing."""
    source = inspect.getsource(run_provider_conformance.main)
    assert "system_prompt=" in source, (
        "the conformance harness calls structured_completion without a system "
        "prompt, so it scores a bare model rather than this product"
    )


def test_it_is_the_product_prompt_and_not_a_copy() -> None:
    """Imported from `synthesis_engine`, never restated.

    A second copy would drift from the one users actually get, and the run would
    then measure a prompt that ships nowhere — a subtler version of the original
    defect, and one that would keep passing the test above.
    """
    source = inspect.getsource(run_provider_conformance)
    assert "from app.services.synthesis_engine import _SYSTEM_PROMPT" in source
    assert "system_prompt=_SYSTEM_PROMPT" in source


def test_the_product_prompt_carries_the_rules_the_score_depends_on() -> None:
    """Precondition on the prompt itself.

    Sending an empty or gutted prompt would satisfy both tests above while
    restoring the original defect exactly. These four instructions are the ones
    whose absence is visible in the failed run: the cardinality rules that
    relationship F1 measures, and the omission rules whose absence produced
    invented tiers on every entity.
    """
    assert "MANY_TO_ONE" in _SYSTEM_PROMPT
    assert "associative (bridge) table" in _SYSTEM_PROMPT
    assert "tier, freshness_sla" in _SYSTEM_PROMPT
    assert "min_value, max_value" in _SYSTEM_PROMPT
    assert len(_SYSTEM_PROMPT) > 1500, "the system prompt looks truncated"
