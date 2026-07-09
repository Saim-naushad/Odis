"""Request ID middleware specifications."""

from __future__ import annotations

import io
import json
import logging
import uuid
from typing import Any, cast

import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog import contextvars as structlog_contextvars

from backend.app.api.middleware import RequestIDMiddleware
from backend.app.infrastructure.logging import configure_logging, get_logger
from backend.app.main import create_app

REQUEST_ID_HEADER = "X-Request-ID"


def _build_context_probe_app() -> FastAPI:
    configure_logging(environment="production")
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/context")
    def read_context() -> dict[str, str]:
        request_id = structlog_contextvars.get_contextvars().get("request_id")
        return {"request_id": request_id if isinstance(request_id, str) else ""}

    return app


def test_generates_request_id_when_header_absent() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    uuid.UUID(request_id)


def test_preserves_supplied_request_id() -> None:
    client = TestClient(create_app())
    supplied_request_id = "client-correlation-abc123"

    response = client.get(
        "/health",
        headers={REQUEST_ID_HEADER: supplied_request_id},
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == supplied_request_id


def test_response_header_matches_request_context() -> None:
    client = TestClient(_build_context_probe_app())
    supplied_request_id = "in-handler-id"

    response = client.get(
        "/context",
        headers={REQUEST_ID_HEADER: supplied_request_id},
    )

    assert response.status_code == 200
    assert response.json() == {"request_id": supplied_request_id}
    assert response.headers[REQUEST_ID_HEADER] == supplied_request_id


def test_context_cleared_between_requests() -> None:
    client = TestClient(_build_context_probe_app())

    first = client.get("/context")
    second = client.get("/context")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["request_id"]
    assert second.json()["request_id"]
    assert first.json()["request_id"] != second.json()["request_id"]
    assert structlog_contextvars.get_contextvars() == {}


def test_structured_logs_include_request_id() -> None:
    configure_logging(environment="production")
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    log_output = io.StringIO()
    handler = logging.StreamHandler(log_output)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.TimeStamper(fmt="iso"),
            ],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root_logger.handlers = [handler]

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    logger = get_logger("tests.request_id")

    @app.get("/log")
    def emit_log() -> dict[str, str]:
        logger.info("request_handled")
        return {"ok": "true"}

    try:
        client = TestClient(app)
        supplied_request_id = "log-correlation-xyz"
        response = client.get("/log", headers={REQUEST_ID_HEADER: supplied_request_id})

        assert response.status_code == 200
        assert response.headers[REQUEST_ID_HEADER] == supplied_request_id

        payload = _find_json_log_event(log_output.getvalue(), "request_handled")
        assert payload["event"] == "request_handled"
        assert payload["request_id"] == supplied_request_id
    finally:
        root_logger.handlers = original_handlers


def _find_json_log_event(output: str, event: str) -> dict[str, Any]:
    for line in output.splitlines():
        if not line.strip():
            continue
        payload = cast(dict[str, Any], json.loads(line))
        if payload.get("event") == event:
            return payload
    raise AssertionError(f"expected log event {event!r} in output: {output!r}")
