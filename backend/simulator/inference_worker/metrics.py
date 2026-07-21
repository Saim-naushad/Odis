"""Prometheus metrics for the streaming worker (PR177 spec section 12).

Follows `backend.app.infrastructure.metrics`'s conventions exactly —
module-level `Counter`/`Gauge`/`Histogram` instances plus `record_xxx`
helper functions, `snake_case` names ending in `_total` for counters —
without importing that package (see `logging_setup.py`'s docstring for
why: `backend/simulator` has no existing dependency on `backend/app`).

Labels stay low-cardinality by design: no raw `asset_id` label anywhere
(spec section 12), only bounded vocabularies (`status`, `reason`,
`transition_type`, and `diagnosed_class`, which is one of a handful of
promoted model classes).
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

fault_inference_telemetry_events_consumed_total = Counter(
    "fault_inference_telemetry_events_consumed_total",
    "Total telemetry events consumed from the input topic",
)

fault_inference_samples_assembled_total = Counter(
    "fault_inference_samples_assembled_total",
    "Total complete per-asset/timestamp samples assembled",
)

fault_inference_malformed_events_total = Counter(
    "fault_inference_malformed_events_total",
    "Total input events rejected as malformed",
    ["reason"],
)

fault_inference_incomplete_sample_expirations_total = Counter(
    "fault_inference_incomplete_sample_expirations_total",
    "Total samples rejected as incomplete after timeout or buffer eviction",
)

fault_inference_conflicting_duplicates_total = Counter(
    "fault_inference_conflicting_duplicates_total",
    "Total samples rejected due to a conflicting duplicate measurement",
)

fault_inference_late_samples_total = Counter(
    "fault_inference_late_samples_total",
    "Total samples rejected as late (older than the asset's last processed sample)",
)

fault_inference_results_total = Counter(
    "fault_inference_results_total",
    "Total fault_inference.v1 events published, by status",
    ["status"],
)

fault_inference_diagnoses_total = Counter(
    "fault_inference_diagnoses_total",
    "Total valid_prediction results, by diagnosed class",
    ["diagnosed_class"],
)

fault_inference_alert_transitions_total = Counter(
    "fault_inference_alert_transitions_total",
    "Total fault_alert_transition.v1 events published, by transition type and class",
    ["transition_type", "diagnosed_class"],
)

fault_inference_active_asset_sessions = Gauge(
    "fault_inference_active_asset_sessions",
    "Number of asset sessions currently tracked by this worker process",
)

fault_inference_assembly_buffer_size = Gauge(
    "fault_inference_assembly_buffer_size",
    "Total number of in-progress (asset, timestamp) samples buffered",
)

fault_inference_inference_latency_seconds = Histogram(
    "fault_inference_inference_latency_seconds",
    "Time spent running the promoted model on one assembled sample",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

fault_inference_event_lag_seconds = Histogram(
    "fault_inference_event_lag_seconds",
    "End-to-end lag between a sample's source_timestamp and processing time",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)

fault_inference_publish_failures_total = Counter(
    "fault_inference_publish_failures_total",
    "Total Kafka publish failures, by target topic role",
    ["topic_role"],
)

fault_inference_worker_starts_total = Counter(
    "fault_inference_worker_starts_total",
    "Total times this worker process has started (each start begins a cold "
    "warm-up — compare against process start time to detect restarts)",
)


def record_telemetry_event_consumed() -> None:
    fault_inference_telemetry_events_consumed_total.inc()


def record_sample_assembled() -> None:
    fault_inference_samples_assembled_total.inc()


def record_malformed_event(reason: str) -> None:
    fault_inference_malformed_events_total.labels(reason=reason).inc()


def record_incomplete_sample_expiration() -> None:
    fault_inference_incomplete_sample_expirations_total.inc()


def record_conflicting_duplicate() -> None:
    fault_inference_conflicting_duplicates_total.inc()


def record_late_sample() -> None:
    fault_inference_late_samples_total.inc()


def record_result(status: str, diagnosed_class: str | None) -> None:
    fault_inference_results_total.labels(status=status).inc()
    if diagnosed_class is not None:
        fault_inference_diagnoses_total.labels(diagnosed_class=diagnosed_class).inc()


def record_alert_transition(transition_type: str, diagnosed_class: str | None) -> None:
    fault_inference_alert_transitions_total.labels(
        transition_type=transition_type,
        diagnosed_class=diagnosed_class or "unknown",
    ).inc()


def record_active_asset_sessions(count: int) -> None:
    fault_inference_active_asset_sessions.set(count)


def record_assembly_buffer_size(count: int) -> None:
    fault_inference_assembly_buffer_size.set(count)


def record_inference_latency(seconds: float) -> None:
    fault_inference_inference_latency_seconds.observe(seconds)


def record_event_lag(seconds: float) -> None:
    if seconds >= 0:
        fault_inference_event_lag_seconds.observe(seconds)


def record_publish_failure(topic_role: str) -> None:
    fault_inference_publish_failures_total.labels(topic_role=topic_role).inc()


def record_worker_start() -> None:
    fault_inference_worker_starts_total.inc()
