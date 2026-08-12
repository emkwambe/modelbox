"""Task 2 — per-task residency (D5) and typed failover (D8).

Two claims that look independent and share a failure mode: **something absent
being read as something permitted.**

D5's version is a task with no residency pin routing anywhere it likes. D8's is
an exception nobody classified being retried as though it were transient. Both
are standard 12 — a comparison against an absent expected value passing
vacuously — and both are asserted here explicitly rather than assumed from the
happy path.

The residency check is enforced **twice on purpose**, and the second one is the
interesting one. Filtering the chain in `resolve_route` proves the chain is
compliant; it does not prove the *request* is, because anything mutating the
chain between resolution and the call would not be seen. So the check is also a
statement inside the one function that reaches the provider, and an AST test
pins it there — the same instrument D3 used, applied to a different claim.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from app.core.config import Settings
from app.models.metadata_store import EGRESS_EVENTS
from app.services.egress_ledger import EgressAttempt
from app.services.llm_gateway import (
    _FAILURE_SIGNATURES,
    _MAY_FAIL_OVER,
    EgressPolicyError,
    EgressResidencyError,
    LLMGateway,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderSchemaError,
    UnclassifiedProviderError,
    classify_provider_failure,
)
from tests._egress_doubles import RecordingLedger, StubProviderClient

GATEWAY = Path(__file__).resolve().parent.parent / "app" / "services" / "llm_gateway.py"
PROMPT = "residency matters"


class Trivial(BaseModel):
    value: str


class _Result:
    pass


# Four providers, one per egress class, so every residency assertion below has
# a discriminating case available rather than only the class it happens to use.
_PROVIDERS = {
    "p_local": {"type": "ollama", "base_url": "http://127.0.0.1:1",
                "default_model": "m", "egress": "local"},
    "p_eu": {"type": "mistral", "default_model": "m", "egress": "cloud_eu"},
    "p_apac": {"type": "openai_compatible", "base_url": "http://127.0.0.1:1/v1",
               "default_model": "m", "egress": "cloud_apac"},
    "p_cloud": {"type": "anthropic", "default_model": "m", "egress": "cloud"},
}

_POLICY = {
    "local": ["local"],
    "cloud_eu": ["local", "cloud_eu"],
    "cloud_apac": ["local", "cloud_apac"],
    "cloud": ["local", "cloud_eu", "cloud_apac", "cloud"],
}

_ROUTER = {
    "providers": _PROVIDERS,
    "egress_policy": _POLICY,
    "task_routing": {
        # The mutation target named in the sprint prompt: a compliant primary
        # with a non-compliant fallback. An implementation that checks only the
        # first provider passes every happy-path test and breaches residency
        # exactly when the primary is down.
        "eu_pinned": {
            "primary": "p_local",
            "fallback": ["p_apac", "p_eu", "p_cloud"],
            "max_egress_class": "cloud_eu",
        },
        "apac_pinned": {
            "primary": "p_local",
            "fallback": ["p_eu", "p_apac"],
            "max_egress_class": "cloud_apac",
        },
        "local_pinned": {
            "primary": "p_local",
            "fallback": ["p_cloud"],
            "max_egress_class": "local",
        },
        "unpinned": {"primary": "p_cloud"},
        "bad_pin": {"primary": "p_cloud", "max_egress_class": "cloud_antarctica"},
        "nowhere": {"primary": "p_cloud", "max_egress_class": "local"},
        "open": {
            "primary": "p_cloud",
            "fallback": ["p_apac"],
            "max_egress_class": "cloud",
        },
    },
}


@pytest.fixture
def router(tmp_path: Path) -> str:
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(_ROUTER), encoding="utf-8")
    return str(path)


def _gateway(router: str, outcomes: list[object] | None = None):
    settings = Settings(  # type: ignore[call-arg]
        model_router_config_path=router, allow_provider_calls=True
    )
    ledger = RecordingLedger()
    gateway = LLMGateway(settings, ledger=ledger)
    client = StubProviderClient(outcomes if outcomes is not None else [_Result()])
    gateway._client = client
    return gateway, client, ledger


# ---------------------------------------------------------------------------
# D5 — residency at resolution
# ---------------------------------------------------------------------------
def test_a_pin_strips_non_compliant_failover_targets(router: str) -> None:
    """The mutation the sprint prompt names, killed.

    `eu_pinned` has a compliant primary and a non-compliant *fallback*. An
    implementation validating `chain[0]` only would return the full chain here
    and this assertion is what tells the two apart.
    """
    gateway, _, _ = _gateway(router)
    assert gateway.resolve_route("eu_pinned") == ["p_local", "p_eu"]


def test_an_eu_pin_does_not_admit_apac_and_an_apac_pin_does_not_admit_eu(
    router: str,
) -> None:
    """Residency is not a scale, and a total order would get one of these wrong.

    `max_egress_class` reads like a scalar on an ordering. If the permitted set
    were computed by comparing positions in such an ordering, one of these two
    assertions would fail whichever way round the ordering put EU and APAC —
    silently, and in the permissive direction. The policy is a declared
    containment map for exactly this reason.
    """
    gateway, _, _ = _gateway(router)
    assert "p_apac" not in gateway.resolve_route("eu_pinned")
    assert "p_eu" not in gateway.resolve_route("apac_pinned")


def test_a_local_pin_admits_only_local(router: str) -> None:
    gateway, _, _ = _gateway(router)
    assert gateway.resolve_route("local_pinned") == ["p_local"]


def test_a_chain_with_nothing_compliant_is_refused_not_emptied(router: str) -> None:
    """Refusing beats returning an empty chain and failing later as "exhausted"."""
    gateway, _, _ = _gateway(router)
    with pytest.raises(EgressResidencyError, match="no provider in its chain"):
        gateway.resolve_route("nowhere")


# ---------------------------------------------------------------------------
# D5 — the standard 12 exposure: absence must not read as permission
# ---------------------------------------------------------------------------
def test_a_task_without_a_pin_is_a_configuration_error(router: str) -> None:
    """The permissive default that was never written.

    The tempting implementation treats a missing `max_egress_class` as "no
    constraint". That is indistinguishable at the call site from a constraint
    that was checked and passed, and it fails open.
    """
    gateway, _, _ = _gateway(router)
    with pytest.raises(EgressPolicyError, match="declares no max_egress_class"):
        gateway.resolve_route("unpinned")


def test_a_pin_naming_an_undeclared_class_is_a_configuration_error(
    router: str,
) -> None:
    """A typo'd pin must not silently admit everything, or nothing."""
    gateway, _, _ = _gateway(router)
    with pytest.raises(EgressPolicyError, match="egress_policy block does not"):
        gateway.resolve_route("bad_pin")


def test_the_production_router_pins_every_task() -> None:
    """The real config, not a fixture — standard 11.

    A gate is only as broad as what it is parameterised over. Every assertion
    above runs against a synthetic router; this one runs against the file the
    appliance actually ships, so a task added without a pin fails here rather
    than at a customer's first request.
    """
    config = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "config" / "model_router.yaml")
        .read_text(encoding="utf-8")
    )
    policy = config["egress_policy"]
    unpinned = [
        task for task, route in config["task_routing"].items()
        if not route.get("max_egress_class")
    ]
    assert not unpinned, f"tasks with no residency pin: {unpinned}"

    undeclared = [
        task for task, route in config["task_routing"].items()
        if route["max_egress_class"] not in policy
    ]
    assert not undeclared, f"tasks pinning an undeclared class: {undeclared}"

    # Every class a provider can carry must be admissible by something, or a
    # provider exists that no task can ever reach — a silent dead entry.
    provider_classes = {p["egress"] for p in config["providers"].values()}
    assert provider_classes <= set(policy), (
        f"provider egress classes absent from egress_policy: "
        f"{provider_classes - set(policy)}"
    )


# ---------------------------------------------------------------------------
# D5 — the check at the moment of the call
# ---------------------------------------------------------------------------
def test_the_residency_check_lives_in_the_calling_function() -> None:
    """Structural, because "checked upstream" is not a property of the call.

    Same instrument as D3's ordering test. A residency check that lives only in
    `resolve_route` is defeated by anything that mutates the chain in between,
    and nothing at the call site can distinguish "validated" from "never
    validated". So the check must be a statement of the function that reaches
    the provider — and it must come before the statement that reaches it.
    """
    tree = ast.parse(GATEWAY.read_text(encoding="utf-8"), filename=str(GATEWAY))
    func = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_call_provider"
    )

    def _mentions(stmt: ast.AST, name: str) -> bool:
        return any(
            isinstance(child, ast.Name) and child.id == name
            for child in ast.walk(stmt)
        )

    check_at = [
        i for i, stmt in enumerate(func.body) if _mentions(stmt, "permitted_egress")
    ]
    client_at = [
        i for i, stmt in enumerate(func.body)
        if any(
            isinstance(child, ast.Attribute)
            and child.attr == "client"
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
            for child in ast.walk(stmt)
        )
    ]
    assert check_at, "_call_provider does not check the permitted egress set"
    assert client_at, "fixture sanity: _call_provider does not reach the client"
    assert check_at[0] < client_at[0], (
        "the residency check must precede the statement that reaches the provider"
    )


async def test_the_call_is_refused_even_when_resolution_was_bypassed(
    router: str,
) -> None:
    """The behavioural half: `_call_provider` refuses on its own authority.

    Calls the choke point directly with a non-compliant class — the state the
    world would be in if the chain were mutated after resolution. The
    discriminating assertions are that the client was never touched and the
    ledger recorded nothing: a refusal that happened after either would not be
    a refusal.
    """
    gateway, client, ledger = _gateway(router)
    attempt = EgressAttempt(
        attempt_id=uuid.uuid4(), task="eu_pinned", provider="p_apac",
        egress_class="cloud_apac", prompt_sha256="0" * 64, prompt_chars=4,
    )
    with pytest.raises(EgressResidencyError, match="not in the permitted set"):
        await gateway._call_provider(
            attempt=attempt,
            permitted_egress=frozenset({"local", "cloud_eu"}),
            response_model=Trivial,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0.0,
            max_retries=0,
            call_kwargs={"model": "anthropic/m"},
        )
    assert client.calls == []
    assert ledger.rows == [], "a refused request must not appear as egress"


async def test_a_residency_refusal_is_not_failed_over(router: str) -> None:
    """A refusal is not a provider being down.

    If `EgressResidencyError` were caught by the failover loop, a pinned task
    would quietly walk down its chain looking for someone to take the request —
    which is the breach the pin exists to prevent, performed by the enforcement
    mechanism itself.
    """
    gateway, client, _ = _gateway(router)
    with pytest.raises(EgressResidencyError):
        await gateway._call_provider(
            attempt=EgressAttempt(
                attempt_id=uuid.uuid4(), task="local_pinned", provider="p_cloud",
                egress_class="cloud", prompt_sha256="0" * 64, prompt_chars=4,
            ),
            permitted_egress=frozenset({"local"}),
            response_model=Trivial,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0.0,
            max_retries=0,
            call_kwargs={"model": "anthropic/m"},
        )
    assert client.calls == []


# ---------------------------------------------------------------------------
# D8 — typed failover
# ---------------------------------------------------------------------------
class AuthenticationError(Exception):
    """Named to match litellm's, since classification is by class name."""


class RateLimitError(Exception):
    pass


class ValidationError(Exception):
    pass


class SomethingNobodyMapped(Exception):
    pass


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (AuthenticationError(), ProviderAuthError),
        (RateLimitError(), ProviderRateLimitError),
        (ValidationError(), ProviderSchemaError),
        (SomethingNobodyMapped(), UnclassifiedProviderError),
    ],
)
def test_failures_classify_distinctly(exc: Exception, expected: type) -> None:
    """Four inputs, four different outputs — the discrimination D8 asks for.

    A classifier that returned one type for everything would satisfy "typed
    failover" structurally and change nothing, which is the failure mode a
    catch-all has in the first place.
    """
    assert classify_provider_failure(exc) is expected


def test_a_subclass_classifies_with_its_parent() -> None:
    class SpecificRateLimit(RateLimitError):
        pass

    assert classify_provider_failure(SpecificRateLimit()) is ProviderRateLimitError


def test_every_classification_has_a_declared_failover_decision() -> None:
    """No classification may inherit a default (standard 11, on the taxonomy).

    Adding a signature without deciding whether it fails over is the way this
    grows a permissive hole. The lookup in the loop is by subscript for the same
    reason: an undecided class raises there rather than defaulting to retry.
    """
    declared = set(_FAILURE_SIGNATURES.values()) | {UnclassifiedProviderError}
    assert declared <= set(_MAY_FAIL_OVER), (
        f"classifications with no failover decision: {declared - set(_MAY_FAIL_OVER)}"
    )


async def test_an_unmapped_failure_abandons_the_chain(router: str) -> None:
    """The standard 12 exposure in D8, asserted explicitly.

    An unrecognised exception falling to a default of "retry" is absence read
    as permission. The discriminating assertion is `len(client.calls) == 1`:
    without it this passes on an implementation that failed over and then
    happened to raise.
    """
    gateway, client, _ = _gateway(
        router, [SomethingNobodyMapped("what even is this"), _Result()]
    )
    with pytest.raises(UnclassifiedProviderError, match="does not recognise"):
        await gateway.structured_completion("open", PROMPT, Trivial)
    assert len(client.calls) == 1, "an unclassified failure was failed over"


async def test_a_classified_transient_failure_does_fail_over(router: str) -> None:
    """The other half — otherwise the abort above could be "never fails over"."""
    gateway, client, _ = _gateway(router, [RateLimitError("429"), _Result()])
    await gateway.structured_completion("open", PROMPT, Trivial)
    assert len(client.calls) == 2


async def test_an_auth_failure_is_reported_ahead_of_a_rate_limit(
    router: str,
) -> None:
    """The concrete harm D8 names: an auth failure handled as though it were a 429.

    Both providers fail, auth first. Reporting the *last* error would send an
    operator to a quota dashboard for a problem that is in their environment
    file.
    """
    gateway, _, _ = _gateway(
        router, [AuthenticationError("bad key"), RateLimitError("429")]
    )
    with pytest.raises(ProviderAuthError) as exc:
        await gateway.structured_completion("open", PROMPT, Trivial)
    assert "ProviderAuthError" in str(exc.value)
    assert "ProviderRateLimitError" in str(exc.value), (
        "the report must still name every failure, not only the winning one"
    )


async def test_the_ledger_records_the_classification(router: str) -> None:
    """"Which provider failed and why" is an operator question the ledger answers."""
    gateway, _, ledger = _gateway(router, [AuthenticationError("bad key"), _Result()])
    await gateway.structured_completion("open", PROMPT, Trivial)

    failures = [row for row in ledger.rows if row["event"] == "FAILURE"]
    assert len(failures) == 1
    assert "ProviderAuthError" in str(failures[0]["error"])


# ---------------------------------------------------------------------------
# The event vocabulary has one home
# ---------------------------------------------------------------------------
def test_the_migration_check_matches_the_declared_vocabulary() -> None:
    """Migration 0015's CHECK is frozen; this is what keeps it honest.

    A migration must not import application code — it is a historical record,
    and code it imported would change under it. So the literal stays, and the
    agreement is asserted instead. Without this the vocabulary has two homes
    again, which is the shape the three `_is_temporal_type` predicates had when
    they disagreed.
    """
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "0015_add_egress_audit.py"
    ).read_text(encoding="utf-8")
    rendered = ", ".join(f"'{event}'" for event in EGRESS_EVENTS)
    assert f"event IN ({rendered})" in migration, (
        f"migration 0015's CHECK constraint does not match EGRESS_EVENTS "
        f"({EGRESS_EVENTS}); the vocabulary has drifted"
    )
