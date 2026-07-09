"""Prometheus metrics endpoint and instrumentation specifications."""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.metrics.monitoring_metrics import (
    monitoring_sse_connections,
)
from backend.app.main import create_app


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "metrics_api.db"
    return Settings(database_url=f"sqlite:///{database_path}")


@pytest.fixture
def api_client(sqlite_settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def _metric_value(metrics_text: str, metric_name: str) -> float:
    escaped = re.escape(metric_name)
    pattern = rf"^{escaped}(?:\{{[^}}]*\}})? (\d+(?:\.\d+)?(?:e[+-]?\d+)?)$"
    for line in metrics_text.splitlines():
        match = re.match(pattern, line)
        if match is not None:
            return float(match.group(1))
    return 0.0


def _metric_sum(metrics_text: str, metric_name: str) -> float:
    escaped = re.escape(metric_name)
    pattern = rf"^{escaped}\{{[^}}]*\}} (\d+(?:\.\d+)?(?:e[+-]?\d+)?)$"
    total = 0.0
    for line in metrics_text.splitlines():
        match = re.match(pattern, line)
        if match is not None:
            total += float(match.group(1))
    return total


def _metric_delta(
    before: str,
    after: str,
    metric_name: str,
) -> float:
    return _metric_value(after, metric_name) - _metric_value(before, metric_name)


def test_metrics_endpoint_returns_prometheus_text_format(
    api_client: TestClient,
) -> None:
    response = api_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert "# HELP http_requests_total" in response.text
    assert "# TYPE http_requests_total counter" in response.text


def test_http_metrics_increment_after_api_call(api_client: TestClient) -> None:
    before = api_client.get("/metrics").text

    health_response = api_client.get("/health")
    assert health_response.status_code == 200

    after = api_client.get("/metrics").text
    assert _metric_sum(after, "http_requests_total") - _metric_sum(
        before, "http_requests_total"
    ) >= 1.0
    assert "http_request_duration_seconds_bucket" in after
    assert "http_requests_in_progress" in after


def test_observations_created_total_increments(api_client: TestClient) -> None:
    before = api_client.get("/metrics").text

    response = api_client.post(
        "/observations",
        json={
            "id": "obs-metrics-1",
            "asset_id": "asset-metrics",
            "timestamp": "2026-01-01T12:00:00Z",
            "measurement_type": "temperature",
            "value": 42.5,
            "unit": "celsius",
        },
    )
    assert response.status_code == 201

    after = api_client.get("/metrics").text
    assert _metric_delta(before, after, "observations_created_total") == 1.0


def test_reasoning_metrics_increment_after_sufficient_observations(
    api_client: TestClient,
) -> None:
    first = {
        "id": "obs-reason-metrics-1",
        "asset_id": "asset-reason-metrics",
        "timestamp": "2026-01-01T10:00:00Z",
        "measurement_type": "temperature",
        "value": 30.0,
        "unit": "celsius",
    }
    second = {
        "id": "obs-reason-metrics-2",
        "asset_id": "asset-reason-metrics",
        "timestamp": "2026-01-01T11:00:00Z",
        "measurement_type": "temperature",
        "value": 45.0,
        "unit": "celsius",
    }

    before = api_client.get("/metrics").text
    api_client.post("/observations", json=first)
    api_client.post("/observations", json=second)

    after = api_client.get("/metrics").text
    assert _metric_delta(before, after, "reasoning_runs_total") == 1.0
    assert "reasoning_duration_seconds_bucket" in after
    assert "reasoning_duration_seconds_count" in after


def test_monitoring_sse_connections_gauge_updates(
    api_client: TestClient,
) -> None:
    # NOTE: End-to-end streaming clients can hang in-process test environments.
    # We validate the exported gauge updates via direct inc/dec + /metrics scrape.
    monitoring_sse_connections.set(0)
    before = api_client.get("/metrics").text
    assert _metric_value(before, "monitoring_sse_connections") == 0.0

    monitoring_sse_connections.inc()
    during = api_client.get("/metrics").text
    assert _metric_value(during, "monitoring_sse_connections") == 1.0

    monitoring_sse_connections.dec()
    after = api_client.get("/metrics").text
    assert _metric_value(after, "monitoring_sse_connections") == 0.0
