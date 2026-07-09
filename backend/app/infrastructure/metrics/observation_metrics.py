"""Observation lifecycle metrics."""

from __future__ import annotations

from prometheus_client import Counter

observations_created_total = Counter(
    "observations_created_total",
    "Total number of observations created",
)
