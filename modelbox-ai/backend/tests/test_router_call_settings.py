"""The router's ``settings:`` block is honoured, not merely present.

``request_timeout_seconds`` and ``num_retries`` sat in
``config/model_router.yaml`` from the beginning and nothing read them. A grep
for ``timeout`` over ``llm_gateway.py`` returned nothing while the file said 60
seconds, and a live failure logged "Max retries exceeded. Total attempts: 1"
while the file said 3.

That is D2's defect class reaching the appliance through the router file rather
than through the environment: **a configuration that states a behaviour the code
does not implement.** It is worse than a missing feature, because the file is
what an operator reads to find out what the appliance will do, and reading it
gave the wrong answer.

The timeout is the one with consequences. With no per-request deadline anywhere
in the call path, a provider that accepts a connection and then stalls blocks
the failover chain indefinitely: the chain never advances, the task never fails,
and whatever is waiting upstream gives up first. The user sees a client-side
timeout naming no provider, which describes the caller's budget rather than what
happened to the work.

**The load-bearing test here is the third one.** The first two would pass
against an implementation that hard-codes 60 and 3 — exactly the plausible wrong
implementation, and exactly what register standard 1 says a test must be able to
tell apart. Two configs declaring *different* values is what distinguishes
"reads the config" from "happens to agree with it".
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from app.core.config import Settings
from app.services.llm_gateway import LLMGateway
from tests._egress_doubles import RecordingLedger, StubProviderClient

SHIPPED_ROUTER = (
    Path(__file__).resolve().parents[2] / "config" / "model_router.yaml"
)


class Trivial(BaseModel):
    """Minimal response model — this suite never reaches a real provider."""

    ok: bool = True


def _router_file(tmp_path: Path, settings_block: dict | None) -> str:
    spec: dict = {
        "version": "1.0",
        "providers": {
            "p_local": {
                "type": "ollama",
                "default_model": "m",
                "egress": "local",
            }
        },
        "egress_policy": {"local": ["local"]},
        "task_routing": {
            "synthesis": {"primary": "p_local", "max_egress_class": "local"}
        },
    }
    if settings_block is not None:
        spec["settings"] = settings_block
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return str(path)


def _gateway(router: str):
    settings = Settings(  # type: ignore[call-arg]
        model_router_config_path=router, allow_provider_calls=True
    )
    gateway = LLMGateway(settings, ledger=RecordingLedger())
    client = StubProviderClient([Trivial()])
    gateway._client = client
    return gateway, client


async def _call(router: str) -> dict:
    """Run one completion and return the kwargs that reached the client."""
    gateway, client = _gateway(router)
    await gateway.structured_completion("synthesis", "hello", Trivial)
    assert len(client.calls) == 1
    return client.calls[0]


@pytest.mark.asyncio
async def test_the_declared_timeout_reaches_the_provider_call(
    tmp_path: Path,
) -> None:
    kwargs = await _call(
        _router_file(tmp_path, {"request_timeout_seconds": 42, "num_retries": 1})
    )
    assert kwargs["timeout"] == 42.0


@pytest.mark.asyncio
async def test_the_declared_retry_budget_reaches_the_provider_call(
    tmp_path: Path,
) -> None:
    kwargs = await _call(
        _router_file(tmp_path, {"request_timeout_seconds": 42, "num_retries": 5})
    )
    assert kwargs["num_retries"] == 5


@pytest.mark.asyncio
async def test_the_values_are_read_rather_than_restated(tmp_path: Path) -> None:
    """The discriminating case: two configs, two different results.

    An implementation that hard-codes the shipped 60 and 3 passes both tests
    above and fails this one. Without it the suite could not tell "honours the
    configuration" from "carries a copy of the same numbers", which is the
    failure the gateway already had — the file and the behaviour agreed on
    nothing, and no test could see it either way.

    **Mutation run, 2026-08-28.** Replacing the config read in
    ``LLMGateway._call_settings`` with the literal
    ``{"request_timeout_seconds": 60, "num_retries": 3}`` — the shipped values,
    so the deployment's own behaviour is unchanged — fails four of the five
    tests in this module, this one among them. The survivor is
    ``test_the_shipped_router_declares_both_settings``, which reads the YAML
    rather than the code and is not expected to see it.
    """
    first = await _call(
        _router_file(tmp_path / "a", {"request_timeout_seconds": 7, "num_retries": 1})
    )
    second = await _call(
        _router_file(tmp_path / "b", {"request_timeout_seconds": 99, "num_retries": 9})
    )
    assert (first["timeout"], first["num_retries"]) == (7.0, 1)
    assert (second["timeout"], second["num_retries"]) == (99.0, 9)


@pytest.mark.asyncio
async def test_an_undeclared_setting_is_left_to_the_client_default(
    tmp_path: Path,
) -> None:
    """Absent is not zero.

    Substituting an invented default for a setting the deployment did not make
    would be this module's own defect restated: the code deciding a behaviour
    the operator never declared. A key that is not there is not passed.
    """
    kwargs = await _call(_router_file(tmp_path, None))
    assert "timeout" not in kwargs
    assert "num_retries" not in kwargs


def test_the_shipped_router_declares_both_settings() -> None:
    """The other half of the pair, which is what actually rots.

    The honouring code above is invisible when the key disappears from the
    router file — it simply stops applying, silently, in the permissive
    direction. This is the test that fails if the shipped deployment stops
    declaring a per-request deadline.
    """
    spec = yaml.safe_load(SHIPPED_ROUTER.read_text(encoding="utf-8"))
    block = spec.get("settings", {})
    assert isinstance(block.get("request_timeout_seconds"), (int, float))
    assert block["request_timeout_seconds"] > 0
    assert isinstance(block.get("num_retries"), int)
    assert block["num_retries"] >= 0
