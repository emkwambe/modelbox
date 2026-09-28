"""The model's output never reaches the ledger, the gateway's log, or Instructor's log.

A fake provider (real Instructor over a fake `acompletion`) returns invalid
output containing a unique marker, twice: once as broken JSON and once as a
wrong type, the two shapes of schema failure. Then no 8-character fragment of
the marker may appear in:

* the ledger's rows, which are append-only, so nothing written there can be
  cleaned up later;
* the error the gateway raises, which a synthesis job stores and the jobs API
  returns;
* the gateway's log and Instructor's log, as the application's own console
  handler writes them (`configure_logging`, captured from stdout, split by
  logger name).

What the ledger keeps instead is asserted too: provider, model,
classification, exception classes, and each error's field path and type.

Negative controls (Amendment 2): with `describe_provider_failure` replaced
in-process by the exception's text, the marker reaches the ledger; with the
log filter's redaction replaced by the identity, it reaches Instructor's log.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from app.core import logging_config
from app.core.config import Settings
from app.core.logging_config import RedactModelOutput, configure_logging
from app.services import llm_gateway
from app.services.llm_gateway import ProviderSchemaError
from tests._egress_doubles import RecordingLedger
from tests.test_gateway_instructor import (
    _ROUTER,
    FakeCompletion,
    Trivial,
    _gateway,
    _tool_call_response,
)

# The development format: "<asctime> <LEVEL> <logger name>: <message>".
_RECORD_START = re.compile(
    r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} [A-Z]+\s+(?P<name>[\w.]+): "
)


@pytest.fixture
def router(tmp_path: Path) -> str:
    path = tmp_path / "model_router.yaml"
    path.write_text(yaml.safe_dump(_ROUTER), encoding="utf-8")
    return str(path)


@pytest.fixture
def app_logging() -> Iterator[None]:
    """Restores the application's logging after a test that captured it."""
    yield
    # Rebind the console handler to whatever stdout is next, not this capture.
    configure_logging(Settings())  # type: ignore[call-arg]


def _capture_app_logging() -> None:
    """Install the application's logging, writing to the test's captured stdout.

    Called from the test body, not a fixture: pytest routes `sys.stdout` to
    `capsys` only for the call phase, and the handler binds the stream it sees
    when it is configured.
    """
    configure_logging(Settings())  # type: ignore[call-arg]


def _app_handlers() -> list[logging.Handler]:
    """The handlers `configure_logging` installed, not pytest's own capture handlers."""
    return [
        handler
        for logger in (logging.getLogger(), logging.getLogger("app"))
        for handler in logger.handlers
        if type(handler) is logging.StreamHandler
    ]


def _records_by_logger(output: str) -> dict[str, list[str]]:
    """Console output grouped into records, keyed by logger name."""
    records: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in output.splitlines():
        match = _RECORD_START.match(line)
        if match:
            current = records.setdefault(match["name"], [])
            current.append(line)
        elif current is not None:
            current[-1] += "\n" + line
    return records


async def _run_invalid_outputs(router: str, marker: str) -> tuple[RecordingLedger, str]:
    """Drive two invalid outputs through the gateway; return the ledger and the
    text of the error it raised."""
    fake = FakeCompletion([
        _tool_call_response('{"value": "' + marker),
        _tool_call_response('{"value": {"note": "' + marker + '"}}'),
    ])
    gateway, ledger = _gateway(router, fake)
    with pytest.raises(ProviderSchemaError) as raised:
        await gateway.structured_completion("t", "prompt", Trivial, max_retries=1)
    assert len(fake.requests) == 2, "fixture sanity: both invalid outputs were served"
    return ledger, str(raised.value)


def _sources(result: tuple[RecordingLedger, str], output: str) -> dict[str, str]:
    ledger, raised = result
    records = _records_by_logger(output)
    gateway_log = "\n".join(records.get("app.services.llm_gateway", []))
    instructor_log = "\n".join(
        line for name, lines in records.items()
        if name == "instructor" or name.startswith("instructor.")
        for line in lines
    )
    # Preconditions: both logs really were written, so an empty one cannot pass.
    seen = f"loggers in the output: {sorted(records)}; {len(output)} chars"
    assert "failed for task 't'" in gateway_log, f"fixture sanity: no gateway log; {seen}"
    assert "Max retries exceeded" in instructor_log, f"fixture sanity: no Instructor log; {seen}"
    return {
        "ledger": repr(ledger.rows),
        "raised error": raised,
        "gateway log": gateway_log,
        "instructor log": instructor_log,
    }


def _check_no_marker(sources: dict[str, str], marker: str) -> None:
    """The check, shared by the test and its negative controls."""
    fragments = {marker[i:i + 8] for i in range(len(marker) - 7)}
    for source, text in sources.items():
        found = sorted(f for f in fragments if f in text)
        assert not found, f"the {source} holds model output: {len(found)} marker fragments"


def _marker() -> str:
    return "mk" + uuid.uuid4().hex


async def test_model_output_reaches_no_ledger_error_or_log(
    router: str, app_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    _capture_app_logging()
    marker = _marker()
    result = await _run_invalid_outputs(router, marker)
    _check_no_marker(_sources(result, capsys.readouterr().out), marker)


async def test_the_ledger_keeps_the_described_fields(
    router: str, app_logging: None
) -> None:
    ledger, _ = await _run_invalid_outputs(router, _marker())
    errors = [row["error"] for row in ledger.rows if row["event"] == "FAILURE"]
    prefix = "ProviderSchemaError/InstructorRetryException<ValidationError"
    assert errors == [
        f"{prefix} provider=p model=anthropic/m errors=(root):json_invalid",
        f"{prefix} provider=p model=anthropic/m errors=value:string_type",
    ]


def test_the_console_handler_carries_the_filter(app_logging: None) -> None:
    _capture_app_logging()
    handlers = _app_handlers()
    assert handlers, "fixture sanity: configure_logging installed no handler"
    assert all(
        any(isinstance(f, RedactModelOutput) for f in h.filters) for h in handlers
    ), "an application handler writes Instructor's records without the redaction filter"


def test_redaction_covers_a_value_that_imitates_the_delimiter() -> None:
    line = "x [type=t, input_value='a, input_type=str] secret', input_type=str]"
    assert "secret" not in logging_config.redact_model_output(line)


# --- Negative controls --------------------------------------------------------


async def test_negative_control_describing_by_message_leaks_into_the_ledger(
    router: str, app_logging: None, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_gateway, "describe_provider_failure", lambda exc, **_: f"{exc}"
    )
    _capture_app_logging()
    marker = _marker()
    result = await _run_invalid_outputs(router, marker)
    with pytest.raises(AssertionError, match="the ledger holds model output"):
        _check_no_marker(_sources(result, capsys.readouterr().out), marker)


async def test_negative_control_without_the_filter_instructor_logs_it(
    router: str, app_logging: None, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_config, "redact_model_output", lambda text: text)
    _capture_app_logging()
    marker = _marker()
    result = await _run_invalid_outputs(router, marker)
    sources = _sources(result, capsys.readouterr().out)
    _check_no_marker({k: v for k, v in sources.items() if k != "instructor log"}, marker)
    with pytest.raises(AssertionError, match="the instructor log holds model output"):
        _check_no_marker(sources, marker)
