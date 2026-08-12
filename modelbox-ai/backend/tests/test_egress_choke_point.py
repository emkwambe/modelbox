"""Task 1 structure — the two properties the choke point holds by construction.

D3 as re-specified. The register asked for "a test proves no path bypasses the
ledger", which is a negative over the whole call graph: a test exercising three
call sites says nothing about a fourth added next year. Sampling cannot earn a
universal.

So the claim is converted from behavioural to structural. If no module outside
the gateway can *import* a provider SDK, no module outside the gateway can call
one, and the ledger write inside the choke point is therefore on every path by
construction. That is checkable by scanning imports, and it fails loudly the
day someone adds a sixth provider — the same instinct as `stable_id`: make the
invariant hold by construction rather than by vigilance.

The choke point carries a second property it was not originally designed for.
"Task 5 may make real provider calls; nothing else in this sprint may" is a
statement of intent, not a constraint — nothing enforces it. Putting the opt-in
inside the same choke point makes provider isolation structural too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.egress_ledger import (
    DatabaseEgressLedger,
    EgressLedgerError,
    prompt_digest,
)
from app.services.llm_gateway import (
    LLMGateway,
    LLMRouterError,
    ProviderCallsDisabledError,
)
from tests._egress_doubles import (
    FailingLedger,
    RecordingLedger,
    StubProviderClient,
)

APP = Path(__file__).resolve().parent.parent / "app"
GATEWAY = APP / "services" / "llm_gateway.py"

# The SDKs that can open a socket to a model provider. litellm is included
# because it is the multiplexer: importing it anywhere else would reintroduce
# exactly the bypass this test exists to prevent.
PROVIDER_SDKS = frozenset(
    {
        "litellm",
        "anthropic",
        "openai",
        "mistralai",
        "google.genai",
        "google.generativeai",
        "cohere",
        "instructor",
        "ollama",
    }
)


def _imported_modules(path: Path) -> set[str]:
    """Every module name imported by a file, including inside functions.

    Walks the AST rather than reading the import block, because a deferred
    import inside a method is exactly how a bypass would arrive — the gateway
    itself defers `litellm` to keep it optional, so the pattern is already
    present in this codebase and reads as normal.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _offending(imports: set[str]) -> set[str]:
    return {
        name
        for name in imports
        for sdk in PROVIDER_SDKS
        if name == sdk or name.startswith(f"{sdk}.")
    }


def test_no_module_outside_the_gateway_imports_a_provider_sdk() -> None:
    """The structural form of "no path bypasses the ledger".

    A behavioural test would enumerate call sites and prove each one logs. This
    proves the set of possible call sites is exactly one, which is the claim the
    register actually wants and the only one that survives a new provider being
    added.
    """
    violations: dict[str, set[str]] = {}
    for path in sorted(APP.rglob("*.py")):
        if path == GATEWAY:
            continue
        offending = _offending(_imported_modules(path))
        if offending:
            violations[str(path.relative_to(APP.parent))] = offending

    assert not violations, (
        "these modules can reach a provider without passing the egress choke "
        f"point, so the ledger cannot be complete by construction: {violations}"
    )


def test_the_gateway_itself_does_import_one() -> None:
    """The discriminating half — otherwise the scan proves only that nothing
    anywhere talks to a provider, which would also pass on a codebase with no
    LLM support at all.
    """
    assert _offending(_imported_modules(GATEWAY)), (
        "the gateway imports no provider SDK, so the scan above is vacuous"
    )


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> LLMGateway:
    get_settings.cache_clear()
    monkeypatch.delenv("MODELBOX_ALLOW_PROVIDER_CALLS", raising=False)
    yield LLMGateway()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_provider_call_without_the_opt_in_is_refused(
    gateway: LLMGateway,
) -> None:
    """No provider is reachable unless the deployment has said so.

    Fail-closed, deliberately, for a product whose central claim is that you
    know what leaves your network. It also makes this sprint's own rule
    enforceable rather than aspirational: Task 5 sets the flag on purpose, and
    nothing else can call out by accident.
    """
    from pydantic import BaseModel

    class Trivial(BaseModel):
        value: str

    with pytest.raises(ProviderCallsDisabledError) as exc:
        await gateway.structured_completion("synthesis", "hello", Trivial)
    assert "MODELBOX_ALLOW_PROVIDER_CALLS" in str(exc.value)


@pytest.mark.asyncio
async def test_the_refusal_precedes_any_network_attempt(
    gateway: LLMGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusing after dialling out is not refusing.

    Asserts the gate sits before the client is even constructed — a check that
    fired after `self.client` had been touched would already have loaded the SDK
    and, on some providers, opened a connection.

    **Do not "simplify" this into the refusal test above.** They look
    redundant and are not: moving the gate below `self.client` leaves that one
    green and only this one fails. The measured evidence that the ordering does
    real work is timing — with the gate correctly placed this file runs in
    ~1.3s; with the gate moved one line down it takes ~55s, because constructing
    the client genuinely imports litellm and instructor. A 40x difference is
    not a stylistic preference.
    """
    from pydantic import BaseModel

    class Trivial(BaseModel):
        value: str

    def _explode(*_: object, **__: object) -> None:
        raise AssertionError("the gateway built a client despite the opt-in being off")

    monkeypatch.setattr(type(gateway), "client", property(_explode))
    with pytest.raises(ProviderCallsDisabledError):
        await gateway.structured_completion("synthesis", "hello", Trivial)


# ---------------------------------------------------------------------------
# The ledger write, proven structurally
# ---------------------------------------------------------------------------
# The register asked for "a test proves no path bypasses the ledger". The two
# tests below are the half of that answer the import scan cannot give. The scan
# proves no *module* outside the gateway can reach a provider; these prove that
# inside the gateway there is exactly one function that reaches one, and that it
# records before it dials. Together the negative is earned rather than sampled.


def _function_named(path: Path, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path.name} has no function named {name!r}")


def _touches_client(node: ast.AST) -> bool:
    """True if this subtree reads ``self.client``.

    Matches the attribute access specifically, not the name ``client``, so the
    lazily-built ``self._client`` backing field does not count — it is the
    public property that constructs the SDK and opens the socket.
    """
    return any(
        isinstance(child, ast.Attribute)
        and child.attr == "client"
        and isinstance(child.value, ast.Name)
        and child.value.id == "self"
        for child in ast.walk(node)
    )


def test_only_one_function_reaches_the_provider_client() -> None:
    """The set of possible call sites is one, and it is the recorded one.

    A behavioural test would show that the paths it happens to exercise write to
    the ledger, and say nothing about a path added next year. This says there is
    nowhere else for such a path to be.
    """
    tree = ast.parse(GATEWAY.read_text(encoding="utf-8"), filename=str(GATEWAY))
    reaching = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _touches_client(node)
    }
    assert reaching == {"_call_provider"}, (
        "exactly one function may reach the provider client, and it must be the "
        f"one that writes the ledger; found {sorted(reaching)}"
    )


def test_the_attempt_write_precedes_every_client_statement() -> None:
    """The record is unskippable, not merely present.

    Asserts the attempt write is a statement in the function body *itself* —
    not nested inside a branch, loop or handler that could be arranged not to
    run — and that it comes before any statement reaching the client. A write
    that were conditional would pass a behavioural test on the branch the test
    happened to take.
    """
    func = _function_named(GATEWAY, "_call_provider")

    write_at = [
        i
        for i, stmt in enumerate(func.body)
        if any(
            isinstance(child, ast.Attribute) and child.attr == "record_attempt"
            for child in ast.walk(stmt)
        )
    ]
    assert len(write_at) == 1, (
        f"expected exactly one top-level attempt write, found {len(write_at)}"
    )

    client_at = [i for i, stmt in enumerate(func.body) if _touches_client(stmt)]
    assert client_at, "fixture sanity: _call_provider does not reach the client"
    assert write_at[0] < client_at[0], (
        "the ledger write must precede every statement that reaches the provider; "
        f"write at body index {write_at[0]}, client first reached at {client_at[0]}"
    )


def test_the_default_gateway_writes_to_the_database() -> None:
    """An unconfigured gateway gets the real sink.

    This is what stops the injectable ledger becoming a hole. Every test below
    passes an in-memory double, and all of them would still pass if the default
    were that double — with the appliance keeping its audit trail in RAM.
    """
    gateway = LLMGateway()
    assert isinstance(gateway._ledger, DatabaseEgressLedger)


# ---------------------------------------------------------------------------
# The ledger write, behaviour
# ---------------------------------------------------------------------------
_ROUTER = {
    "providers": {
        "cloud_primary": {
            "type": "anthropic",
            "default_model": "unreachable",
            "egress": "cloud",
        },
        "local_fallback": {
            "type": "ollama",
            "base_url": "http://127.0.0.1:1",
            "default_model": "unreachable",
            "egress": "local",
        },
    },
    "egress_policy": {
        "local": ["local"],
        "cloud": ["local", "cloud"],
    },
    "task_routing": {
        "one_provider": {"primary": "cloud_primary", "max_egress_class": "cloud"},
        "two_providers": {
            "primary": "cloud_primary",
            "fallback": ["local_fallback"],
            "max_egress_class": "cloud",
        },
    },
}

PROMPT = "the ledger must record this"


class Trivial(BaseModel):
    value: str


class _Usage:
    prompt_tokens = 11
    completion_tokens = 22


class _Raw:
    usage = _Usage()


class _Result:
    """Stands in for an Instructor result carrying its raw response."""

    _raw_response = _Raw()


@pytest.fixture
def router_config(tmp_path: Path) -> str:
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(_ROUTER), encoding="utf-8")
    return str(path)


def _wired(
    router_config: str, outcomes: list[object], ledger: object
) -> tuple[LLMGateway, StubProviderClient]:
    settings = Settings(  # type: ignore[call-arg]
        model_router_config_path=router_config,
        allow_provider_calls=True,
    )
    gateway = LLMGateway(settings, ledger=ledger)  # type: ignore[arg-type]
    client = StubProviderClient(outcomes)
    gateway._client = client
    return gateway, client


async def test_a_successful_call_writes_attempt_then_success(
    router_config: str,
) -> None:
    """Two rows, in order, and the outcome is a new row rather than an edit."""
    ledger = RecordingLedger()
    gateway, client = _wired(router_config, [_Result()], ledger)

    await gateway.structured_completion("one_provider", PROMPT, Trivial)

    assert len(client.calls) == 1
    assert ledger.events() == ["ATTEMPT", "SUCCESS"]
    attempt, success = ledger.rows
    assert attempt["attempt_id"] == success["attempt_id"], (
        "the outcome must correlate with its attempt"
    )
    assert attempt["provider"] == "cloud_primary"
    assert attempt["egress_class"] == "cloud"
    assert attempt["prompt_sha256"] == prompt_digest(PROMPT)
    assert attempt["prompt_chars"] == len(PROMPT)
    assert success["prompt_tokens"] == 11
    assert success["completion_tokens"] == 22


async def test_the_ledger_does_not_store_the_prompt(router_config: str) -> None:
    """A governance ledger must not become a second copy of what it governs."""
    ledger = RecordingLedger()
    gateway, _ = _wired(router_config, [_Result()], ledger)

    await gateway.structured_completion("one_provider", PROMPT, Trivial)

    serialised = repr(ledger.rows)
    assert PROMPT not in serialised
    assert prompt_digest(PROMPT) in serialised


async def test_a_failed_call_writes_attempt_then_failure(router_config: str) -> None:
    """A request that left and then failed is still a request that left."""
    ledger = RecordingLedger()
    gateway, _ = _wired(router_config, [RuntimeError("provider exploded")], ledger)

    with pytest.raises(LLMRouterError):
        await gateway.structured_completion("one_provider", PROMPT, Trivial)

    assert ledger.events() == ["ATTEMPT", "FAILURE"]
    assert "provider exploded" in str(ledger.rows[1]["error"])


async def test_failover_records_each_provider_as_its_own_request(
    router_config: str,
) -> None:
    """Two providers contacted is two requests that left, and two attempts.

    The plausible wrong implementation writes one row per *call* to
    `structured_completion` rather than one per provider, which would record a
    failover to a cloud provider as though only the first had been contacted —
    understating egress in exactly the direction that flatters the product.
    """
    ledger = RecordingLedger()
    # A *classified* transient failure. Since Task 2 an unrecognised exception
    # abandons the chain rather than failing over, so a bare RuntimeError here
    # would test the abort path while claiming to test failover.
    class RateLimitError(Exception):
        pass

    gateway, client = _wired(
        router_config, [RateLimitError("primary throttled"), _Result()], ledger
    )

    await gateway.structured_completion("two_providers", PROMPT, Trivial)

    assert len(client.calls) == 2
    assert ledger.events() == ["ATTEMPT", "FAILURE", "ATTEMPT", "SUCCESS"]

    attempts = ledger.attempts()
    assert [a["provider"] for a in attempts] == ["cloud_primary", "local_fallback"]
    assert [a["egress_class"] for a in attempts] == ["cloud", "local"]
    assert attempts[0]["attempt_id"] != attempts[1]["attempt_id"], (
        "each request needs its own correlation id or the two cannot be told apart"
    )
    assert attempts[0]["prompt_sha256"] == attempts[1]["prompt_sha256"], (
        "the same prompt sent twice must carry one digest across both rows"
    )


async def test_a_ledger_that_cannot_write_stops_the_request(
    router_config: str,
) -> None:
    """Fail closed: no record, no request.

    The discriminating assertion is `client.calls == []`. Without it this test
    would pass on an implementation that made the call and *then* failed to
    record it — which is precisely the behaviour that would make D3 false while
    looking, from the outside, like a working ledger.
    """
    gateway, client = _wired(router_config, [_Result()], FailingLedger())

    with pytest.raises(EgressLedgerError):
        await gateway.structured_completion("one_provider", PROMPT, Trivial)

    assert client.calls == [], "a request left the network without being recorded"


async def test_a_ledger_failure_is_not_failed_over(router_config: str) -> None:
    """An unrecordable request is unrecordable on every provider.

    If the ledger error were caught by the failover loop it would be retried
    against the fallback, so a broken ledger would produce a chain of unrecorded
    requests and then an exhausted-providers error — the loudest possible
    symptom of the quietest possible failure, reported as the wrong thing.
    """
    gateway, client = _wired(
        router_config, [_Result(), _Result()], FailingLedger()
    )

    with pytest.raises(EgressLedgerError):
        await gateway.structured_completion("two_providers", PROMPT, Trivial)

    assert client.calls == []
