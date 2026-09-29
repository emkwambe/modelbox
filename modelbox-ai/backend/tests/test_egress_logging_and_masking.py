"""Governance guards for Sprint 1 (finding B3).

Two properties, both previously untested and both previously false:

1. Setting ``MASK_METADATA_IN_PROMPTS=true`` fails startup. Masking was
   documented but never implemented — ``_maybe_mask`` returned its argument —
   so an operator could enable a compliance control that did nothing. It is
   retired rather than built (Blueprint §3, Q2), and the flag is now a tripwire.

2. Routing a task emits a log line. The application configured no logging, so
   under uvicorn's defaults the root logger sat at ``WARNING`` and the gateway's
   ``logger.info`` never reached a handler: there was no runtime record that a
   prompt had left the box.

**No provider is contacted.** The gateway is pointed at a local provider on a
port nothing listens to. The routing line is emitted *before* the network call,
so the connection failure is irrelevant to what is asserted — which also makes
this a test of the logging configuration rather than of provider behaviour.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging_config import configure_logging
from app.schemas.data_model import SocraticStepResponse
from app.services.llm_gateway import LLMGateway, LLMRouterError
from tests._egress_doubles import RecordingLedger

_ROUTER_CONFIG = "../config/model_router.yaml"

# Two local providers on a port nothing listens to. Connection is refused
# immediately, where an unresolvable hostname would spend ~30s in DNS. Nothing
# is contacted and no credential exists for either.
_DEAD_ROUTER = {
    "providers": {
        "local_ollama": {
            "type": "ollama",
            "base_url": "http://127.0.0.1:1",
            "default_model": "unreachable",
            "egress": "local",
        },
        "airgapped_vllm": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:1/v1",
            "default_model": "unreachable",
            "egress": "local",
        },
        "anthropic_cloud": {
            "type": "anthropic",
            "default_model": "unreachable",
            "egress": "cloud",
        },
        "kimi_cloud": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:1/v1",
            "default_model": "unreachable",
            "egress": "cloud_apac",
        },
    },
    "egress_policy": {
        "local": ["local"],
        "cloud_apac": ["local", "cloud_apac"],
        "cloud": ["local", "cloud_eu", "cloud_apac", "cloud"],
    },
    "task_routing": {
        "socratic_tutoring": {
            "primary": "anthropic_cloud",
            "fallback": ["local_ollama"],
            "max_egress_class": "cloud",
        },
        "unstructured_doc_parsing": {
            "primary": "anthropic_cloud",
            "fallback": ["kimi_cloud", "airgapped_vllm"],
            "max_egress_class": "cloud",
        },
    },
}


def _settings(**overrides: object) -> Settings:
    overrides.setdefault("model_router_config_path", _ROUTER_CONFIG)
    # This file is the one place that deliberately drives the gateway past its
    # fail-closed gate (D3): it asserts what the *routing* records, and the
    # router it uses points at dead endpoints, so nothing leaves the machine.
    # Opting in explicitly is the point of the flag — a test that exercises the
    # egress path has to say so, rather than inheriting permission.
    overrides.setdefault("allow_provider_calls", True)
    return Settings(**overrides)  # type: ignore[arg-type]


@pytest.fixture
def dead_router(tmp_path: Path) -> str:
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(_DEAD_ROUTER), encoding="utf-8")
    return str(path)


class _Capture(logging.Handler):
    """Collect records straight off the `app` logger.

    `caplog` attaches to the root logger, but `configure_logging` sets
    `propagate: False` on `app` to avoid duplicate output — so caplog sees
    nothing even when the configuration is correct. Capturing at the source
    tests the real wiring instead of the propagation path.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


# ---------------------------------------------------------------------------
# 1. The retired masking flag refuses to start
# ---------------------------------------------------------------------------
def test_masking_flag_fails_startup() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _settings(mask_metadata_in_prompts=True)
    message = str(excinfo.value)
    assert "not implemented" in message
    assert "retired" in message.lower()
    assert "AIRGAPPED=true" in message, "the error must name the real control"


def test_masking_flag_absent_or_false_is_fine() -> None:
    assert _settings().mask_metadata_in_prompts is False
    assert _settings(mask_metadata_in_prompts=False).mask_metadata_in_prompts is False


def test_gateway_has_no_masking_hook() -> None:
    """The stub is gone, not merely disabled — it must not read as functional."""
    assert not hasattr(LLMGateway, "_maybe_mask")


# ---------------------------------------------------------------------------
# 2. Routing produces a record
# ---------------------------------------------------------------------------
def test_configure_logging_lets_gateway_info_through() -> None:
    """After configure_logging, an INFO record from the gateway is handled.

    Asserted against the resolved logger configuration rather than caplog, which
    installs its own handler and would pass even with the application logging
    unconfigured — exactly the false negative this test exists to avoid.
    """
    configure_logging(_settings())
    gateway_logger = logging.getLogger("app.services.llm_gateway")
    assert gateway_logger.isEnabledFor(logging.INFO), (
        "the gateway's egress line would be dropped before reaching a handler"
    )
    assert gateway_logger.getEffectiveLevel() <= logging.INFO
    handlers = gateway_logger.handlers or logging.getLogger("app").handlers
    assert handlers, "no handler is attached to the app logger tree"


def _gateway(**overrides: object) -> tuple[LLMGateway, RecordingLedger]:
    """A gateway wired to an in-memory ledger.

    Needed since Sprint 5: the choke point records before it dials and refuses
    the request if it cannot, so a gateway with the default database ledger
    fails here with `EgressLedgerError` — there is no database in this suite —
    rather than reaching the routing code these tests assert on. Supplying a
    real sink keeps the failure that matters (routing) visible instead of being
    masked by the one that does not (no database).
    """
    ledger = RecordingLedger()
    return LLMGateway(_settings(**overrides), ledger=ledger), ledger


async def _route_and_capture(gateway: LLMGateway, task: str) -> list[str]:
    """Attempt one routed completion and return what the app logger recorded."""
    capture = _Capture()
    app_logger = logging.getLogger("app")
    app_logger.addHandler(capture)
    try:
        with pytest.raises(LLMRouterError):
            await gateway.structured_completion(
                task=task,
                prompt="fidelity harness — this must never reach a provider",
                response_model=SocraticStepResponse,
                max_retries=0,
            )
    finally:
        app_logger.removeHandler(capture)
    return capture.messages


async def test_routing_a_task_emits_an_egress_record(dead_router: str) -> None:
    """Routing emits the provider it selected, before any network call."""
    configure_logging(_settings())
    gateway, ledger = _gateway(airgapped=True, model_router_config_path=dead_router)

    messages = await _route_and_capture(gateway, "socratic_tutoring")
    routed = [m for m in messages if "Routing task" in m]

    assert routed, "no egress record was emitted for a routed task"
    assert "socratic_tutoring" in routed[0]
    assert "local_ollama" in routed[0], (
        "air-gapped routing must select a local provider"
    )
    # The log line was the Sprint 1 record. The ledger is the Sprint 5 one, and
    # it must agree with it: a log a human might read and a row an auditor can
    # query should never disagree about where a prompt went.
    assert [row["provider"] for row in ledger.attempts()] == ["local_ollama"]


async def test_airgapped_routing_never_records_a_cloud_provider(
    dead_router: str,
) -> None:
    """Whatever the Sprint 5 ledger records, it must not name a cloud provider.

    Written in Sprint 1 against the log line, because the ledger did not exist.
    It does now, so the same claim is made against the ledger itself — the
    artifact a regulated buyer is actually shown.
    """
    configure_logging(_settings())
    gateway, ledger = _gateway(airgapped=True, model_router_config_path=dead_router)
    cloud = {
        name
        for name, provider in gateway.providers.items()
        if provider.get("egress") != "local"
    }
    assert cloud, "fixture sanity: the router must define cloud providers"

    messages = " ".join(await _route_and_capture(gateway, "unstructured_doc_parsing"))
    leaked = sorted(name for name in cloud if name in messages)
    assert not leaked, f"air-gapped run routed to cloud providers: {leaked}"

    assert ledger.attempts(), (
        "nothing was recorded, so this test would pass on a gateway that made "
        "no request at all"
    )
    recorded = {str(row["provider"]) for row in ledger.attempts()}
    assert not recorded & cloud, f"the ledger records cloud egress: {recorded & cloud}"
    assert {str(row["egress_class"]) for row in ledger.attempts()} == {"local"}
