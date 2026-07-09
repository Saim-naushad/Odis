"""Digital Twin cache metrics."""

from __future__ import annotations

from prometheus_client import Counter

cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of Digital Twin cache hits",
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of Digital Twin cache misses",
)

cache_invalidations_total = Counter(
    "cache_invalidations_total",
    "Total number of Digital Twin cache invalidations",
)

