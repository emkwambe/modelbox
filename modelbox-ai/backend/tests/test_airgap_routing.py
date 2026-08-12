"""Task 3 — air-gapped mode that proves itself (D6, D7, Q1).

**D6 is inverted, and that inversion is the whole point.** The criterion used to
read "runs end to end with no cloud keys present", which passes on a box that
simply never had any keys configured — the test would have been green on a
laptop where nobody had exported `ANTHROPIC_API_KEY`, and green for a reason
that has nothing to do with air-gapped mode working. Standard 12 in a new venue:
an absent input read as satisfaction.

So the test **sets every provider key to a sentinel value** and then asserts
that none of them was used, that every route resolved local-only, and that a
route which would have needed one was refused at resolution. Absence is made
loud: the keys are present, usable, and provably untouched.

D7 is checked against the compose file the appliance actually ships. Until this
sprint the air-gapped *primary* was `airgapped_vllm`, whose host
`vllm-server.internal` is a container nothing in this repository creates — the
out-of-the-box air-gap path pointed at infrastructure the appliance neither
ships nor documents. It is now a declared bring-your-own fallback, and a primary
may never be one.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml
from pydantic import BaseModel

from app.core.config import Settings
from app.services.llm_gateway import LLMGateway, LLMRouterError
from tests._egress_doubles import RecordingLedger, StubProviderClient

REPO = Path(__file__).resolve().parents[2]
ROUTER_PATH = REPO / "config" / "model_router.yaml"
COMPOSE_PATH = REPO / "docker" / "docker-compose.appliance.yml"

ROUTER = yaml.safe_load(ROUTER_PATH.read_text(encoding="utf-8"))
COMPOSE = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

# A distinct sentinel per key, so a leak names the provider that leaked rather
# than only proving that something did.
SENTINELS = {
    env: f"sentinel-{env.lower().replace('_', '-')}-must-never-be-used"
    for env in sorted(
        {
            provider["api_key_env"]
            for provider in ROUTER["providers"].values()
            if provider.get("api_key_env")
        }
    )
}

CLOUD_PROVIDERS = {
    name: provider
    for name, provider in ROUTER["providers"].items()
    if provider["egress"] != "local"
}
CLOUD_SENTINELS = {
    SENTINELS[provider["api_key_env"]]
    for provider in CLOUD_PROVIDERS.values()
    if provider.get("api_key_env")
}


class Trivial(BaseModel):
    value: str


class _Result:
    pass


@pytest.fixture
def sentinel_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Every provider credential present and usable — the opposite of absent."""
    for env, value in SENTINELS.items():
        monkeypatch.setenv(env, value)
    return SENTINELS


def _airgapped(**overrides: object) -> tuple[LLMGateway, StubProviderClient, RecordingLedger]:
    settings = Settings(  # type: ignore[call-arg]
        model_router_config_path=str(ROUTER_PATH),
        airgapped=True,
        allow_provider_calls=True,
        **overrides,
    )
    ledger = RecordingLedger()
    gateway = LLMGateway(settings, ledger=ledger)
    client = StubProviderClient([_Result() for _ in range(8)])
    gateway._client = client
    return gateway, client, ledger


# ---------------------------------------------------------------------------
# Fixture sanity — the inversion only means something if the keys are really set
# ---------------------------------------------------------------------------
def test_the_sentinels_are_actually_present(sentinel_keys: dict[str, str]) -> None:
    """Without this, every assertion below could pass on an empty environment.

    Which is exactly the vacuous pass D6 was re-specified to eliminate, so the
    re-specification would have reintroduced its own defect one level up.
    """
    import os

    assert sentinel_keys, "no provider declares an api_key_env; the fixture is empty"
    assert CLOUD_SENTINELS, "no cloud provider has a key to leak"
    for env, value in sentinel_keys.items():
        assert os.environ[env] == value


# ---------------------------------------------------------------------------
# D6 — air-gapped with every key set
# ---------------------------------------------------------------------------
def test_every_task_resolves_local_only_with_all_keys_set(
    sentinel_keys: dict[str, str],
) -> None:
    gateway, _, _ = _airgapped()
    local = {
        name for name, p in ROUTER["providers"].items() if p["egress"] == "local"
    }
    for task in ROUTER["task_routing"]:
        chain = gateway.resolve_route(task)
        assert chain, f"task '{task}' has no air-gapped route"
        assert set(chain) <= local, f"task '{task}' routed to cloud: {chain}"


async def test_an_airgapped_run_sends_no_cloud_key(
    sentinel_keys: dict[str, str],
) -> None:
    """The load-bearing assertion: the keys were there and went unused.

    Checks what was actually handed to the provider call, not what the router
    intended — a resolution-only assertion cannot see a credential injected
    later by `_litellm_kwargs`, which is where keys are in fact attached.
    """
    gateway, client, ledger = _airgapped()

    for task in ROUTER["task_routing"]:
        await gateway.structured_completion(task, f"prompt for {task}", Trivial)

    assert len(client.calls) == len(ROUTER["task_routing"])

    sent = repr(client.calls)
    leaked = sorted(s for s in CLOUD_SENTINELS if s in sent)
    assert not leaked, f"a cloud credential was sent under air-gapped mode: {leaked}"

    # And the ledger agrees — the artifact a buyer is shown must say the same
    # thing as the wire did.
    classes = {str(row["egress_class"]) for row in ledger.attempts()}
    assert classes == {"local"}, f"the ledger records non-local egress: {classes}"


async def test_stripping_is_what_makes_a_fall_through_task_local(
    sentinel_keys: dict[str, str], tmp_path: Path
) -> None:
    """The discriminating case the production config cannot provide.

    Found by mutation, and worth stating plainly: every task in
    `airgapped_overrides` already lists local providers only, so disabling
    air-gap stripping altogether changes nothing for them. The two assertions
    above would pass on a gateway with no air-gap enforcement at all — standard
    8, a fixture that does not exercise the feature it names.

    A task with **no** override falls through to `task_routing`, and there the
    stripping is the only thing standing between a cloud provider and a
    sentinel key. That is the case this supplies.
    """
    router = dict(ROUTER)
    router["task_routing"] = {
        "fall_through": {
            "primary": "anthropic_cloud",
            "fallback": ["openai_cloud", "local_ollama"],
            "max_egress_class": "cloud",
        }
    }
    router["airgapped_overrides"] = {}
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(router), encoding="utf-8")

    settings = Settings(  # type: ignore[call-arg]
        model_router_config_path=str(path),
        airgapped=True,
        allow_provider_calls=True,
    )
    ledger = RecordingLedger()
    gateway = LLMGateway(settings, ledger=ledger)
    gateway._client = StubProviderClient([_Result()])

    assert gateway.resolve_route("fall_through") == ["local_ollama"], (
        "air-gap stripping did not remove the cloud providers this task lists"
    )

    await gateway.structured_completion("fall_through", "x", Trivial)
    sent = repr(gateway._client.calls)
    leaked = sorted(s for s in CLOUD_SENTINELS if s in sent)
    assert not leaked, f"a cloud credential was sent under air-gapped mode: {leaked}"
    assert {str(r["egress_class"]) for r in ledger.attempts()} == {"local"}


async def test_a_route_that_would_use_a_cloud_key_is_refused_at_resolution(
    sentinel_keys: dict[str, str],
) -> None:
    """"Refused", not "quietly rerouted".

    An explicit override naming a cloud provider is the sharpest form of the
    question: the operator has asked for egress by name, with a valid-looking
    credential available. Air-gapped mode must refuse rather than silently
    substitute a local provider, because a silent substitution answers a
    different question than the one asked and nothing tells the caller.
    """
    gateway, client, _ = _airgapped()
    for name in CLOUD_PROVIDERS:
        with pytest.raises(LLMRouterError, match="no local provider"):
            await gateway.structured_completion(
                "ddl_code_generation", "x", Trivial, llm_override=name
            )
    assert client.calls == [], "a refused override still reached a provider"


# ---------------------------------------------------------------------------
# D7 — the air-gapped route resolves to something that exists
# ---------------------------------------------------------------------------
def _compose_services() -> set[str]:
    return set(COMPOSE.get("services", {}))


def _host_of(provider: dict) -> str | None:
    url = provider.get("base_url")
    return urlparse(url).hostname if url else None


def test_every_airgapped_provider_exists_or_is_declared_byo() -> None:
    """The defect this closes: a default pointing at a container we do not ship.

    A provider reachable under air-gapped routing must either resolve to a
    service in the appliance's own compose file, or be explicitly marked
    ``byo: true`` — operator-supplied infrastructure. What is not allowed is the
    third state this config was in: neither shipped nor declared, so the route
    simply failed at runtime with a DNS error.
    """
    services = _compose_services()
    assert services, "fixture sanity: the compose file declares no services"

    reachable = {
        name
        for route in ROUTER["airgapped_overrides"].values()
        for name in [route["primary"], *route.get("fallback", [])]
    }
    assert reachable, "fixture sanity: no air-gapped providers to check"

    for name in sorted(reachable):
        provider = ROUTER["providers"][name]
        if provider.get("byo"):
            continue
        host = _host_of(provider)
        assert host in services, (
            f"air-gapped provider '{name}' points at host '{host}', which is "
            f"not a service in {COMPOSE_PATH.name} and is not marked byo. "
            f"Known services: {sorted(services)}"
        )


def test_no_airgapped_primary_is_bring_your_own() -> None:
    """A default that depends on infrastructure we do not ship is not a default.

    The discriminating half of the test above: marking every provider ``byo``
    would satisfy it while leaving the appliance exactly as broken.
    """
    offenders = [
        (task, route["primary"])
        for task, route in ROUTER["airgapped_overrides"].items()
        if ROUTER["providers"][route["primary"]].get("byo")
    ]
    assert not offenders, (
        f"air-gapped primaries requiring operator-supplied infrastructure: "
        f"{offenders}"
    )


def test_the_shipped_local_runtime_is_reachable_from_the_backend() -> None:
    """The compose service exists *and* the backend can address it.

    A service can be present and unreachable — a different network, or a
    profile the backend does not join. Asserting the name alone would pass on
    that, which is standard 9: the name is a consequence of reachability, not
    the property.
    """
    services = COMPOSE["services"]
    ollama = services.get("ollama-engine")
    assert ollama is not None, "the appliance ships no local inference service"

    host = _host_of(ROUTER["providers"]["local_ollama"])
    assert host == "ollama-engine", (
        f"local_ollama addresses '{host}', not the shipped service name"
    )

    # Reachability, stated as a property rather than skipped when it happens to
    # be trivially true. Compose puts every service on one implicit default
    # network *unless* some service declares its own, so "neither declares" is
    # a real guarantee and is asserted as one. Writing this as `if networks:
    # assert ...` would silently verify nothing today and keep verifying nothing
    # on the day someone adds a network to one service only — standard 8.
    backend_networks = set(services["modelbox-backend"].get("networks") or [])
    ollama_networks = set(ollama.get("networks") or [])
    both_on_default = not backend_networks and not ollama_networks
    assert both_on_default or (backend_networks & ollama_networks), (
        f"the backend cannot reach ollama-engine: backend networks "
        f"{backend_networks or '{default}'} vs ollama-engine networks "
        f"{ollama_networks or '{default}'}"
    )


def test_the_local_runtime_is_in_the_airgap_profile() -> None:
    """It must start with the air-gap profile, or air-gapped mode has no engine."""
    profiles = COMPOSE["services"]["ollama-engine"].get("profiles") or []
    assert "airgap" in profiles, (
        f"ollama-engine profiles {profiles} do not include 'airgap'"
    )
