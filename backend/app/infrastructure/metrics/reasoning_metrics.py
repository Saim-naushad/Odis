"""Reasoning execution metrics."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

reasoning_runs_total = Counter(
    "reasoning_runs_total",
    "Total number of reasoning runs completed",
)

reasoning_duration_seconds = Histogram(
    "reasoning_duration_seconds",
    "Reasoning session execution duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

reasoning_failures_total = Counter(
    "reasoning_failures_total",
    "Total number of reasoning run failures",
)

trend_analysis_duration_seconds = Histogram(
    "trend_analysis_duration_seconds",
    "Trend diagnostics computation duration in seconds",
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

digital_twin_build_duration_seconds = Histogram(
    "digital_twin_build_duration_seconds",
    "Digital twin assembly duration in seconds",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def record_reasoning_run() -> None:
    """Increment when a reasoning run completes successfully in the worker."""
    reasoning_runs_total.inc()


def record_reasoning_failure() -> None:
    """Increment when a reasoning run fails in the worker."""
    reasoning_failures_total.inc()


def record_reasoning_duration(duration_seconds: float) -> None:
    """Observe reasoning session execution time."""
    reasoning_duration_seconds.observe(duration_seconds)


def record_trend_analysis_duration(duration_seconds: float) -> None:
    """Observe trend diagnostics computation time."""
    trend_analysis_duration_seconds.observe(duration_seconds)


def record_digital_twin_build_duration(duration_seconds: float) -> None:
    """Observe digital twin assembly time on cache miss."""
    digital_twin_build_duration_seconds.observe(duration_seconds)
