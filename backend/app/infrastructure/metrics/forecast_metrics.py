"""Forecast inference metrics."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

forecast_inference_total = Counter(
    "forecast_inference_total",
    "Total number of telemetry forecast inference requests",
)

forecast_inference_failures_total = Counter(
    "forecast_inference_failures_total",
    "Total number of failed telemetry forecast inference requests",
)

forecast_inference_duration_seconds = Histogram(
    "forecast_inference_duration_seconds",
    "Telemetry forecast inference duration in seconds",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def record_forecast_inference_success() -> None:
    forecast_inference_total.inc()


def record_forecast_inference_failure() -> None:
    forecast_inference_failures_total.inc()


def record_forecast_inference_duration(duration_seconds: float) -> None:
    forecast_inference_duration_seconds.observe(duration_seconds)
