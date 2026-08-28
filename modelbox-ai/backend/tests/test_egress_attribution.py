"""Every outbound request is attributable to a person (D4).

Task 1 made the ledger record *what* left and *when*, and D3 made that
structural: nothing outside the gateway can reach a provider, one function
inside it dials, and the attempt row is written before it does. The criterion
D4 asks for is different — an operator answering "what left our network, when,
**to whom**" — and the ledger's `user_id`, `workspace_id` and `model_id`
columns existed from migration 0015 while every call site left them null.

A nullable column nothing populates is the permissive failure again: the schema
says attribution is supported, the rows say nothing, and the gap is invisible
until someone asks the question the criterion exists to answer.

**The load-bearing test here is the structural one.** Checking that the three
known call sites pass an actor says nothing about a fourth added next year, and
this is a codebase that has already been bitten by exactly that reasoning — D3
was re-specified in Sprint 5 for the same flaw, "a test exercising three call
sites says nothing about a fourth". So the assertion is over the AST of every
call into `structured_completion` in the application, whatever its name.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
GATEWAY = APP / "services" / "llm_gateway.py"

# The identity the ledger needs before it can answer "who". `model_id` is
# deliberately absent: synthesis is the call that creates the model, so at the
# moment the prompt leaves there is nothing to name, and requiring it would
# force a call site to invent one.
REQUIRED_KWARGS = ("user_id", "workspace_id")


def _call_sites() -> list[tuple[Path, ast.Call]]:
    """Every `…structured_completion(…)` call in the application."""
    found: list[tuple[Path, ast.Call]] = []
    for path in sorted(APP.rglob("*.py")):
        if path == GATEWAY:
            continue  # the definition, not a call site
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "structured_completion":
                found.append((path, node))
    return found


def test_the_call_sites_are_still_discoverable() -> None:
    """Fixture sanity, and standard 12.

    An AST scan that matches nothing passes every assertion below it. If the
    gateway method is renamed, this fails rather than letting the attribution
    check quietly stop looking.
    """
    sites = _call_sites()
    assert len(sites) >= 3, (
        f"expected the known synthesis / paradigm / trainer call sites, found "
        f"{len(sites)}"
    )


@pytest.mark.parametrize("kwarg", REQUIRED_KWARGS)
def test_every_call_site_attributes_its_request(kwarg: str) -> None:
    """A request that reaches a provider unattributed cannot be accounted for.

    Asserted over the AST rather than by exercising the three services, because
    the claim is universal: *every* path into the gateway names an actor. A
    behavioural test over today's call sites would go on passing the day a
    fourth is added, and the ledger would fill with rows nobody can trace.

    Mutation, 2026-08-28: removing `user_id` and `workspace_id` from the
    Trainer's call fails both parameters of this test, naming
    `app/services/trainer_service.py` and the line — which is what makes the
    failure actionable rather than merely red.
    """
    missing = [
        f"{path.relative_to(APP.parent)}:{node.lineno}"
        for path, node in _call_sites()
        if kwarg not in {kw.arg for kw in node.keywords if kw.arg}
    ]
    assert not missing, (
        f"these calls reach a provider without passing '{kwarg}', so the ledger "
        f"cannot say who caused the egress: {missing}"
    )


def test_the_gateway_still_accepts_what_the_call_sites_pass() -> None:
    """The other half of the pair: a kwarg the gateway drops is worse than none.

    The call sites could all pass an actor into a signature that no longer has
    somewhere to put it — `structured_completion` would raise, but only on a
    path that this suite deliberately never exercises. Reading the signature
    keeps the two halves honest about each other.
    """
    tree = ast.parse(GATEWAY.read_text(encoding="utf-8"))
    signature = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "structured_completion"
    )
    accepted = {arg.arg for arg in signature.args.kwonlyargs + signature.args.args}
    for kwarg in (*REQUIRED_KWARGS, "model_id"):
        assert kwarg in accepted, f"the gateway no longer accepts '{kwarg}'"
