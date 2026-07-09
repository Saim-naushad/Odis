"""Reasoning worker job lifecycle metrics."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

reasoning_jobs_created_total = Counter(
    "reasoning_jobs_created_total",
    "Total number of reasoning jobs enqueued",
)

reasoning_jobs_completed_total = Counter(
    "reasoning_jobs_completed_total",
    "Total number of reasoning jobs completed successfully",
)

reasoning_jobs_failed_total = Counter(
    "reasoning_jobs_failed_total",
    "Total number of reasoning jobs that failed",
)

reasoning_jobs_running = Gauge(
    "reasoning_jobs_running",
    "Number of reasoning jobs currently running",
)

reasoning_job_duration_seconds = Histogram(
    "reasoning_job_duration_seconds",
    "End-to-end reasoning job processing duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


def record_reasoning_job_created() -> None:
    """Increment when a reasoning job is enqueued."""
    reasoning_jobs_created_total.inc()


def record_reasoning_job_running_started() -> None:
    """Increment when a pending job is claimed and marked RUNNING."""
    reasoning_jobs_running.inc()


def record_reasoning_job_running_finished() -> None:
    """Decrement when a running job completes or fails."""
    reasoning_jobs_running.dec()


def record_reasoning_job_completed() -> None:
    """Increment when a claimed job is marked COMPLETED."""
    reasoning_jobs_completed_total.inc()


def record_reasoning_job_failed() -> None:
    """Increment when a claimed job is marked FAILED."""
    reasoning_jobs_failed_total.inc()


def record_reasoning_job_duration(duration_seconds: float) -> None:
    """Observe end-to-end job processing time in the worker."""
    reasoning_job_duration_seconds.observe(duration_seconds)
