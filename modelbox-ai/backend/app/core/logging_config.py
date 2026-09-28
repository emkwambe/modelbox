"""Application logging configuration.

Before v1.6.0 nothing in the application called ``basicConfig`` or
``dictConfig``. Under uvicorn's default configuration that leaves the root
logger at ``WARNING``, so the gateway's egress line —

    logger.info("Routing task '%s' -> provider '%s'", task, provider_name)

— was never emitted. The single record that a prompt had left the box did not
exist at runtime. This module makes it exist.

It is deliberately not an audit trail: an ephemeral log line records *that* a
request was routed, not what was in it, and it is not queryable or tamper
evident. The append-only ``egress_audit`` ledger (finding B3, Sprint 5) attaches
at the same choke point in ``LLMGateway.structured_completion``.

Called from both entrypoints — the API (``app.main``) and the Celery worker
(``app.worker``) — because synthesis runs in the worker, so egress happens
there too.
"""

from __future__ import annotations

import logging
import logging.config
import re
from typing import Any

from app.core.config import Settings

# Pydantic renders each error as `... [type=T, input_value=<repr>, input_type=X]`
# on one line; a repr escapes newlines, so the value cannot span lines. Greedy to
# the line's last `, input_type=`, so a value that itself contains that text is
# still covered.
_INPUT_VALUE = re.compile(r"input_value=.*, input_type=")
REDACTED = "input_value=<redacted>, input_type="


def redact_model_output(text: str) -> str:
    """``text`` with every pydantic ``input_value`` replaced."""
    return _INPUT_VALUE.sub(REDACTED, text)


class RedactModelOutput(logging.Filter):
    """Redacts ``input_value`` from Instructor's log records.

    Instructor logs a failed structured call's validation error, and pydantic's
    rendering of it quotes the value it rejected: the model's output. The
    gateway never logs that value itself (`describe_provider_failure`); this
    covers the library's own records. Installed on the handler rather than on
    the ``instructor`` logger, because a logger's filters do not apply to
    records from its children, and Instructor logs from ``instructor.v2.*``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "instructor" or record.name.startswith("instructor."):
            record.msg = redact_model_output(record.getMessage())
            record.args = None
            if record.exc_info:
                record.exc_text = redact_model_output(
                    logging.Formatter().formatException(record.exc_info)
                )
        return True


def logging_dict_config(settings: Settings) -> dict[str, Any]:
    """Build the dictConfig for the current environment."""
    level = "DEBUG" if settings.debug else "INFO"
    fmt = (
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        if settings.environment == "development"
        else '{"ts":"%(asctime)s","level":"%(levelname)s",'
             '"logger":"%(name)s","msg":"%(message)s"}'
    )
    return {
        "version": 1,
        # uvicorn and celery configure their own loggers before we run; leaving
        # them in place keeps access logs and worker output intact.
        "disable_existing_loggers": False,
        "formatters": {"standard": {"format": fmt}},
        "filters": {"redact_model_output": {"()": RedactModelOutput}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "stream": "ext://sys.stdout",
                "filters": ["redact_model_output"],
            }
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
        "loggers": {
            # The application's own loggers, including the LLM gateway, whose
            # routing line is the only runtime record that a prompt egressed.
            "app": {"handlers": ["console"], "level": level, "propagate": False},
        },
    }


def configure_logging(settings: Settings) -> None:
    """Install the logging configuration. Idempotent."""
    logging.config.dictConfig(logging_dict_config(settings))
