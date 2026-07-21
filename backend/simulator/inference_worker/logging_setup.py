"""Structured logging for the streaming worker.

`backend/simulator` has no existing dependency on `backend/app` (its
publishers talk to the platform only over HTTP/MQTT/Kafka, never by
importing `backend.app.*`); this module preserves that boundary by
defining its own tiny setup rather than importing
`backend.app.infrastructure.logging`, while matching its conventions
exactly — `structlog` bound to stdlib logging, JSON in production,
`snake_case` past-tense event names as the first positional log argument.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.stdlib import BoundLogger
from structlog.stdlib import get_logger as get_stdlib_logger
from structlog.types import Processor


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def configure_logging(*, log_level: str = "INFO") -> None:
    level = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: str | None = None) -> BoundLogger:
    return get_stdlib_logger(name)
