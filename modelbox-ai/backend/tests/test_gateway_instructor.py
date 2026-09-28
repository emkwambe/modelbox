"""The gateway under real Instructor wrapping (Sprint 7 Step 4).

The stub client in `_egress_doubles` raises and returns *below* the Instructor
layer, so it cannot show what Instructor does to either. These tests build the
real client, `instructor.from_litellm`, over a fake `acompletion`: every byte
between the gateway and the fake is the installed Instructor, and nothing
leaves the process.

**Classification.** Instructor raises every failure of a structured call,
a provider's `AuthenticationError` included, as `InstructorRetryException`
chained from the original. `classify_provider_failure` walks that chain, so an
auth failure is `ProviderAuthError` and not a schema error.

**One ledger attempt per request.** Instructor runs with `max_retries=0`, and
the gateway re-asks after a schema failure itself, so each HTTP request is its
own ATTEMPT with its own outcome. Invalid JSON twice and then valid JSON is
three requests, and three attempt rows.

Negative controls (Amendment 2), each disabling exactly the fix in-process:
without the chain walk the same exception classifies as a schema error; with
Instructor allowed to retry internally, three requests leave under one row.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import instructor
import litellm
import pytest
import yaml
from pydantic import BaseModel

from app.core.config import Settings
from app.services import llm_gateway
from app.services.llm_gateway import (
    LLMGateway,
    ProviderAuthError,
    ProviderSchemaError,
    classify_provider_failure,
)
from tests._egress_doubles import RecordingLedger

PROMPT = "classify this"


class Trivial(BaseModel):
    value: str


_ROUTER = {
    "providers": {"p": {"type": "anthropic", "default_model": "m", "egress": "cloud"}},
    "egress_policy": {"cloud": ["cloud"]},
    "task_routing": {"t": {"primary": "p", "max_egress_class": "cloud"}},
}


@pytest.fixture
def router(tmp_path: Path) -> str:
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(_ROUTER), encoding="utf-8")
    return str(path)


def _tool_call_response(arguments: str) -> litellm.ModelResponse:
    """A provider response carrying one tool call, as Instructor's TOOLS mode reads it."""
    return litellm.ModelResponse(
        choices=[{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "Trivial", "arguments": arguments},
                }],
            },
        }],
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    )


class FakeCompletion:
    """Stands in for `litellm.acompletion`: records each request, then raises
    or returns the next scripted outcome.

    Instructor picks its async path with `inspect.iscoroutinefunction`, which is
    false for an object with an async `__call__`, so the fake it is given is
    `self.acompletion`, a real coroutine function.
    """

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[dict[str, Any]] = []

        async def acompletion(**kwargs: Any) -> object:
            # A snapshot: Instructor extends the message list it passed here
            # when it builds a re-ask, so a reference would show later state.
            self.requests.append(copy.deepcopy(kwargs))
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        self.acompletion = acompletion


def _auth_error() -> litellm.AuthenticationError:
    return litellm.AuthenticationError(message="bad key", llm_provider="anthropic", model="m")


def _gateway(router: str, fake: FakeCompletion) -> tuple[LLMGateway, RecordingLedger]:
    settings = Settings(  # type: ignore[call-arg]
        model_router_config_path=router, allow_provider_calls=True
    )
    ledger = RecordingLedger()
    gateway = LLMGateway(settings, ledger=ledger)
    gateway._client = instructor.from_litellm(fake.acompletion)
    return gateway, ledger


async def _wrapped_auth_failure() -> BaseException:
    """What the real Instructor client raises when the provider refuses the key."""
    fake = FakeCompletion([_auth_error()])
    client = instructor.from_litellm(fake.acompletion)
    with pytest.raises(Exception) as info:
        await client.chat.completions.create(
            model="anthropic/m",
            response_model=Trivial,
            messages=[{"role": "user", "content": PROMPT}],
            max_retries=0,
        )
    # Preconditions: the wrapper is really there, around the provider's error.
    assert type(info.value).__name__ == "InstructorRetryException"
    assert isinstance(info.value.__cause__, litellm.AuthenticationError)
    return info.value


def _check_classified_as_auth(exc: BaseException) -> None:
    """The check, shared by the test and its negative control."""
    classification = classify_provider_failure(exc)
    assert classification is ProviderAuthError, (
        f"an auth failure under Instructor classified as {classification.__name__}"
    )


def _check_one_attempt_per_request(ledger: RecordingLedger, fake: FakeCompletion) -> None:
    """The check, shared by the test and its negative control."""
    attempts = ledger.attempts()
    assert len(attempts) == len(fake.requests), (
        f"{len(fake.requests)} requests left, the ledger shows {len(attempts)}"
    )
    assert len({row["attempt_id"] for row in attempts}) == len(attempts)


# --- Classification ----------------------------------------------------------


async def test_an_auth_failure_under_real_instructor_is_provider_auth() -> None:
    _check_classified_as_auth(await _wrapped_auth_failure())


async def test_the_gateway_reports_and_records_it_as_auth(router: str) -> None:
    fake = FakeCompletion([_auth_error()])
    gateway, ledger = _gateway(router, fake)
    with pytest.raises(ProviderAuthError):
        await gateway.structured_completion("t", PROMPT, Trivial, max_retries=2)
    assert len(fake.requests) == 1, "an auth failure was re-asked as a schema failure"
    assert ledger.events() == ["ATTEMPT", "FAILURE"]
    assert str(ledger.rows[1]["error"]).startswith(
        "ProviderAuthError/InstructorRetryException"
    )


def test_the_innermost_recognised_cause_wins() -> None:
    """A transport error under the provider's own exception, under the wrapper:
    the provider's exception decides, not the wrapper and not the unmapped root."""

    class ConnectError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class InstructorRetryException(Exception):
        pass

    try:
        try:
            try:
                raise ConnectError("socket")
            except ConnectError as root:
                raise RateLimitError("429") from root
        except RateLimitError as provider:
            raise InstructorRetryException("wrapped") from provider
    except InstructorRetryException as wrapped:
        assert classify_provider_failure(wrapped) is llm_gateway.ProviderRateLimitError


def test_a_suppressed_context_is_not_followed() -> None:
    """`raise X from None` hides the context on purpose; the walk respects it."""

    class ValidationError(Exception):
        pass

    class SomethingNobodyMapped(Exception):
        pass

    try:
        try:
            raise ValidationError("hidden")
        except ValidationError:
            raise SomethingNobodyMapped("outer") from None
    except SomethingNobodyMapped as exc:
        assert classify_provider_failure(exc) is llm_gateway.UnclassifiedProviderError


# --- One ledger attempt per request ------------------------------------------


async def test_invalid_json_twice_then_valid_is_three_attempt_rows(router: str) -> None:
    fake = FakeCompletion([
        _tool_call_response("{not json"),
        _tool_call_response("{not json"),
        _tool_call_response('{"value": "ok"}'),
    ])
    gateway, ledger = _gateway(router, fake)

    result = await gateway.structured_completion("t", PROMPT, Trivial, max_retries=2)

    assert result.value == "ok"
    assert len(fake.requests) == 3
    assert len(ledger.attempts()) == 3
    assert ledger.events() == ["ATTEMPT", "FAILURE", "ATTEMPT", "FAILURE", "ATTEMPT", "SUCCESS"]
    _check_one_attempt_per_request(ledger, fake)
    for row in ledger.rows:
        if row["event"] == "FAILURE":
            assert str(row["error"]).startswith("ProviderSchemaError/")
    # Each re-ask carries what Instructor's own retry sent: the conversation so
    # far plus the invalid response and its validation error, two messages per
    # failed request, after the original prompt.
    assert [len(r["messages"]) for r in fake.requests] == [1, 3, 5]
    for request in fake.requests:
        assert request["messages"][0] == {"role": "user", "content": PROMPT}


async def test_exhausted_re_asks_record_every_request(router: str) -> None:
    fake = FakeCompletion([_tool_call_response("{not json")] * 3)
    gateway, ledger = _gateway(router, fake)
    with pytest.raises(ProviderSchemaError):
        await gateway.structured_completion("t", PROMPT, Trivial, max_retries=2)
    assert ledger.events() == ["ATTEMPT", "FAILURE"] * 3
    _check_one_attempt_per_request(ledger, fake)


# --- Negative controls --------------------------------------------------------


async def test_negative_control_without_the_chain_walk_auth_reads_as_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exc = await _wrapped_auth_failure()
    monkeypatch.setattr(llm_gateway, "_exception_chain", lambda e: [e])
    with pytest.raises(AssertionError, match="classified as ProviderSchemaError"):
        _check_classified_as_auth(exc)


async def test_negative_control_instructor_retries_hide_requests_from_the_ledger(
    router: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm_gateway, "_INSTRUCTOR_MAX_RETRIES", 2)
    fake = FakeCompletion([
        _tool_call_response("{not json"),
        _tool_call_response("{not json"),
        _tool_call_response('{"value": "ok"}'),
    ])
    gateway, ledger = _gateway(router, fake)
    await gateway.structured_completion("t", PROMPT, Trivial, max_retries=2)
    with pytest.raises(AssertionError, match="3 requests left, the ledger shows 1"):
        _check_one_attempt_per_request(ledger, fake)
