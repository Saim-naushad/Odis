"""Reasoning execution metrics."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

reasoning_runs_total = Counter(
    "reasoning_runs_total",
    "Total number of reasoning runs completed",
)

reasoning_duration_seconds = Histogram(
    "reasoning_duration_seconds",
    "Reasoning run duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

reasoning_failures_total = Counter(
    "reasoning_failures_total",
    "Total number of reasoning run failures",
)
