"""Health and readiness probe metrics."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

worker_heartbeat_age_seconds = Gauge(
    "worker_heartbeat_age_seconds",
    "Age in seconds of the most recent worker heartbeat",
)

reasoning_jobs_pending = Gauge(
    "reasoning_jobs_pending",
    "Number of reasoning jobs currently pending",
)

reasoning_jobs_failed_current = Gauge(
    "reasoning_jobs_failed_current",
    "Number of reasoning jobs currently in FAILED status",
)

readiness_check_failures_total = Counter(
    "readiness_check_failures_total",
    "Total readiness probe failures by dependency",
    labelnames=("dependency",),
)

_BOUNDED_READINESS_DEPENDENCIES = frozenset(
    {
        "database",
        "engine",
        "session_factory",
        "reasoning_job_queue",
        "worker",
    },
)


def set_worker_heartbeat_age_seconds(age_seconds: float) -> None:
    """Update the freshest worker heartbeat age gauge."""
    worker_heartbeat_age_seconds.set(age_seconds)


def set_reasoning_jobs_pending(count: int) -> None:
    """Update the pending reasoning jobs gauge."""
    reasoning_jobs_pending.set(count)


def set_reasoning_jobs_failed_current(count: int) -> None:
    """Update the current failed reasoning jobs gauge."""
    reasoning_jobs_failed_current.set(count)


def record_readiness_check_failure(dependency: str) -> None:
    """Increment when a required readiness dependency fails."""
    if dependency in _BOUNDED_READINESS_DEPENDENCIES:
        readiness_check_failures_total.labels(dependency=dependency).inc()
