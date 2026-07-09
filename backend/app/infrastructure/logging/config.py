"""Centralized structured logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog import contextvars
from structlog.types import Processor

# Canonical context fields for cross-service correlation.
STANDARD_CONTEXT_FIELDS = (
    "event",
    "asset_id",
    "run_id",
    "observation_id",
    "request_id",
)


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def _resolve_log_level(log_level: str) -> int:
    level = logging.getLevelNamesMapping().get(log_level.upper())
    if level is None:
        raise ValueError(f"Unsupported log level: {log_level!r}")
    return level


def configure_logging(
    *,
    log_level: str = "INFO",
    environment: str = "development",
) -> None:
    """Initialize structlog and stdlib logging for the application."""
    level = _resolve_log_level(log_level)
    renderer: Processor = (
        structlog.dev.ConsoleRenderer()
        if environment == "development"
        else structlog.processors.JSONRenderer()
    )

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
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a module-scoped structured logger."""
    return structlog.get_logger(name)


def get_request_id() -> str | None:
    """Return the request_id bound in the current async/task context, if any."""
    request_id = contextvars.get_contextvars().get("request_id")
    if isinstance(request_id, str):
        return request_id
    return None


def bind_request_id(request_id: str | None) -> None:
    """Attach request_id to the current async/task context for downstream logs."""
    if request_id is not None:
        contextvars.bind_contextvars(request_id=request_id)


def clear_log_context(**extra: Any) -> None:
    """Reset bound context variables; optional keys preserve selected fields."""
    contextvars.clear_contextvars()
    if extra:
        contextvars.bind_contextvars(**extra)
