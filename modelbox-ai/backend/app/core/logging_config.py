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

import logging.config
from typing import Any

from app.core.config import Settings


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
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "stream": "ext://sys.stdout",
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
