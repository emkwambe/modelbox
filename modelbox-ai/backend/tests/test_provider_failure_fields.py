"""A provider failure is recorded with structured fields, never free text.

The ledger's error column and the gateway's log keep the HTTP status, the
provider's error type and code, and any retry-after seconds, as validated
`key=value` fields: a status is an integer in 100..599, a type or code is an
identifier of at most 64 characters, retry-after is whole seconds in 0..86400.
A value that fails its check is dropped, never truncated or quoted.

Real Instructor over a fake `acompletion` that raises LiteLLM's own exceptions
carrying a real `httpx.Response`, so the fields are read from what LiteLLM
actually hands the gateway.

Negative control (Amendment 2): with the identifier check replaced in-process
by `str`, a sentence in the provider's error type reaches the ledger.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import litellm
import pytest
import yaml

from app.services import llm_gateway
from app.services.llm_gateway import ProviderAuthError, ProviderRateLimitError
from tests.test_gateway_instructor import _ROUTER, FakeCompletion, Trivial, _gateway


@pytest.fixture
def router(tmp_path: Path) -> str:
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(_ROUTER), encoding="utf-8")
    return str(path)


def _response(status: int, headers: dict[str, str], error: dict[str, str]) -> httpx.Response:
    return httpx.Response(
        status,
        headers=headers,
        json={"error": error},
        request=httpx.Request("POST", "https://provider.invalid/v1/messages"),
    )


def _rate_limit(headers: dict[str, str], error: dict[str, str]) -> litellm.RateLimitError:
    """LiteLLM's 429, chained from the provider's HTTP error as LiteLLM raises it.

    `litellm.RateLimitError` replaces the response it is given with one of its
    own that keeps the headers and drops the body, so the provider's error
    object is only on the exception it was raised from.
    """
    response = _response(429, headers, error)
    exc = litellm.RateLimitError(
        message=error.get("message", "rate limited"),
        llm_provider="anthropic",
        model="m",
        response=response,
    )
    exc.__cause__ = httpx.HTTPStatusError("429", request=response.request, response=response)
    return exc


async def _failure_row(router: str, exc: BaseException, expected: type) -> str:
    fake = FakeCompletion([exc])
    gateway, ledger = _gateway(router, fake)
    with pytest.raises(expected):
        await gateway.structured_completion("t", "prompt", Trivial, max_retries=0)
    [row] = [r for r in ledger.rows if r["event"] == "FAILURE"]
    return str(row["error"])


def _check_no_free_text(error: str, marker: str) -> None:
    """The check, shared by the test and its negative control."""
    assert marker not in error, f"free text reached the ledger: {error}"


async def test_a_rate_limit_records_status_type_code_and_retry_after(router: str) -> None:
    marker = uuid.uuid4().hex
    exc = _rate_limit(
        {"retry-after": "30"},
        {"type": "rate_limit_error", "code": "rate_limit_exceeded", "message": f"slow down {marker}"},
    )
    error = await _failure_row(router, exc, ProviderRateLimitError)
    assert error == (
        "ProviderRateLimitError/InstructorRetryException<RateLimitError<HTTPStatusError "
        "provider=p model=anthropic/m status=429 type=rate_limit_error "
        "code=rate_limit_exceeded retry_after=30"
    )
    _check_no_free_text(error, marker)


async def test_an_auth_failure_records_its_status(router: str) -> None:
    exc = litellm.AuthenticationError(
        message="bad key",
        llm_provider="anthropic",
        model="m",
        response=_response(401, {}, {"type": "authentication_error"}),
    )
    error = await _failure_row(router, exc, ProviderAuthError)
    assert "status=401 type=authentication_error" in error
    assert "retry_after" not in error


async def test_a_sentence_in_the_type_is_dropped(router: str) -> None:
    marker = uuid.uuid4().hex
    exc = _rate_limit({}, {"type": f"Too many requests from {marker}"})
    error = await _failure_row(router, exc, ProviderRateLimitError)
    assert "type=" not in error
    _check_no_free_text(error, marker)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"retry-after-ms": "1500"}, "retry_after=2"),
        ({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({"retry-after": "999999"}, None),
        ({"retry-after": "-1"}, None),
    ],
)
async def test_retry_after_is_whole_seconds_in_range(
    router: str, headers: dict[str, str], expected: str | None
) -> None:
    error = await _failure_row(router, _rate_limit(headers, {}), ProviderRateLimitError)
    if expected is None:
        assert "retry_after" not in error
    else:
        assert expected in error


async def test_negative_control_without_the_identifier_check_text_gets_in(
    router: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm_gateway, "_token", lambda value: str(value) if value else None)
    marker = uuid.uuid4().hex
    exc = _rate_limit({}, {"type": f"Too many requests from {marker}"})
    error = await _failure_row(router, exc, ProviderRateLimitError)
    with pytest.raises(AssertionError, match="free text reached the ledger"):
        _check_no_free_text(error, marker)
