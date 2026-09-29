"""Provider-declared headers reach the call, or the call is refused (D9-adjacent).

Written after a real failure. The first genuine D10 conformance attempt with a
valid credential was rejected by every request:

    anthropic-workspace-id is required when authenticating with an
    identity-linked API key; send the id of the workspace this request acts in.

Anthropic's identity-linked keys refuse any request that does not name the
workspace it acts in, and the gateway had no way to send one. A customer holding
that kind of key could configure the provider correctly and watch every call
fail with an error that reads like a bad key — the appliance would look broken
and the credential would look wrong, and neither would be true.

Two properties, and the second is the one worth having a test for.

**A declared header reaches the provider call.** Asserted on the kwargs actually
handed to the client, not on the config — the same reason
`test_airgap_routing.py` checks what was passed rather than what was resolved.

**A declared header with no value is refused at load, not sent empty.** The
tempting alternative is to skip the header and let the request go. It would then
fail at the provider, several layers from the line that caused it, with a
vendor's error message about its own API. Declared-and-unset is a configuration
error, which is the ruling `max_egress_class` already gets: absence is not an
implicit "send nothing".
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.llm_gateway import LLMGateway, LLMRouterError


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch, tmp_path) -> LLMGateway:
    router = tmp_path / "router.yaml"
    router.write_text(
        """
providers:
  headered_cloud:
    type: "anthropic"
    api_key_env: "TEST_PROVIDER_KEY"
    default_model: "claude-sonnet-4-5-20250929"
    headers:
      anthropic-workspace-id: TEST_WORKSPACE_ID
    egress: "cloud"
  plain_cloud:
    type: "anthropic"
    api_key_env: "TEST_PROVIDER_KEY"
    default_model: "claude-sonnet-4-5-20250929"
    egress: "cloud"
egress_policy:
  local: ["local"]
  cloud: ["local", "cloud"]
task_routing:
  unstructured_doc_parsing:
    primary: "headered_cloud"
    max_egress_class: "cloud"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_PROVIDER_KEY", "key-value")
    settings = Settings(model_router_config_path=str(router))  # type: ignore[call-arg]
    return LLMGateway(settings)


def test_a_declared_header_reaches_the_call(
    gateway: LLMGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_WORKSPACE_ID", "ws-12345")
    kwargs = gateway._litellm_kwargs("headered_cloud")
    assert kwargs["extra_headers"] == {"anthropic-workspace-id": "ws-12345"}


def test_a_declared_header_with_no_value_is_refused(
    gateway: LLMGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loud at load rather than rejected at the provider.

    This is the assertion that matters. Skipping the header and sending anyway
    is the easy path, and it converts a one-line configuration mistake into a
    vendor error message three layers away.
    """
    monkeypatch.delenv("TEST_WORKSPACE_ID", raising=False)
    with pytest.raises(LLMRouterError) as exc:
        gateway._litellm_kwargs("headered_cloud")

    message = str(exc.value)
    assert "anthropic-workspace-id" in message
    assert "TEST_WORKSPACE_ID" in message, "the error must name the variable to set"


def test_a_provider_that_declares_no_headers_sends_none(
    gateway: LLMGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discriminating half.

    An implementation that always attached `extra_headers` — empty, or copied
    from another provider — would satisfy the first test and quietly change what
    every other provider receives.
    """
    monkeypatch.setenv("TEST_WORKSPACE_ID", "ws-12345")
    kwargs = gateway._litellm_kwargs("plain_cloud")
    assert "extra_headers" not in kwargs


def test_the_shipped_router_declares_the_anthropic_workspace_header() -> None:
    """The config that produced the failure now carries the fix.

    Asserted against the real `model_router.yaml` rather than a fixture,
    because the defect was in the shipped configuration and a test over a
    fabricated one would have passed throughout.
    """
    from pathlib import Path

    import yaml

    repo = Path(__file__).resolve().parents[2]
    router = yaml.safe_load(
        (repo / "config" / "model_router.yaml").read_text(encoding="utf-8")
    )
    headers = router["providers"]["anthropic_cloud"].get("headers") or {}
    assert headers.get("anthropic-workspace-id") == "ANTHROPIC_WORKSPACE_ID"
