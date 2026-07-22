"""Reasoning-bridge worker metrics (PR178 spec section 17).

Follows this codebase's existing metrics convention (module-level
`Counter`/`Histogram` instances + `record_xxx` helpers, `snake_case`
names ending in `_total` for counters). No raw `asset_id` label anywhere;
only bounded vocabularies (`reason`, `result`, `status`, `transition_type`).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

reasoning_bridge_alert_transitions_consumed_total = Counter(
    "reasoning_bridge_alert_transitions_consumed_total",
    "Total alert-transition events consumed from the input topic",
)

reasoning_bridge_malformed_events_total = Counter(
    "reasoning_bridge_malformed_events_total",
    "Total alert-transition events rejected as malformed",
    ["reason"],
)

reasoning_bridge_duplicate_events_ignored_total = Counter(
    "reasoning_bridge_duplicate_events_ignored_total",
    "Total alert-transition events ignored as already-processed replays",
)

reasoning_bridge_corroboration_results_total = Counter(
    "reasoning_bridge_corroboration_results_total",
    "Total corroboration outcomes, by result",
    ["result"],
)

reasoning_bridge_investigations_created_total = Counter(
    "reasoning_bridge_investigations_created_total",
    "Total new AI fault investigations opened",
)

reasoning_bridge_investigations_updated_total = Counter(
    "reasoning_bridge_investigations_updated_total",
    "Total existing AI fault investigations updated in place",
)

reasoning_bridge_recommendations_produced_total = Counter(
    "reasoning_bridge_recommendations_produced_total",
    "Total actionable recommendations produced",
)

reasoning_bridge_recommendations_withheld_total = Counter(
    "reasoning_bridge_recommendations_withheld_total",
    "Total recommendations withheld (not-corroborated or insufficient evidence)",
)

reasoning_bridge_class_change_updates_total = Counter(
    "reasoning_bridge_class_change_updates_total",
    "Total class_changed transitions applied to an existing investigation",
)

reasoning_bridge_clear_transitions_processed_total = Counter(
    "reasoning_bridge_clear_transitions_processed_total",
    "Total cleared transitions processed",
)

reasoning_bridge_failures_total = Counter(
    "reasoning_bridge_failures_total",
    "Total unexpected failures while processing an alert-transition event",
)

reasoning_bridge_processing_latency_seconds = Histogram(
    "reasoning_bridge_processing_latency_seconds",
    "Time spent processing one alert-transition event end to end",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

reasoning_bridge_publish_failures_total = Counter(
    "reasoning_bridge_publish_failures_total",
    "Total Kafka publish failures for the reasoning-result event",
)

reasoning_bridge_worker_starts_total = Counter(
    "reasoning_bridge_worker_starts_total",
    "Total times this worker process has started",
)


def record_alert_transition_consumed() -> None:
    reasoning_bridge_alert_transitions_consumed_total.inc()


def record_malformed_event(reason: str) -> None:
    reasoning_bridge_malformed_events_total.labels(reason=reason).inc()


def record_duplicate_event_ignored() -> None:
    reasoning_bridge_duplicate_events_ignored_total.inc()


def record_corroboration_result(result: str) -> None:
    reasoning_bridge_corroboration_results_total.labels(result=result).inc()


def record_investigation_created() -> None:
    reasoning_bridge_investigations_created_total.inc()


def record_investigation_updated() -> None:
    reasoning_bridge_investigations_updated_total.inc()


def record_recommendation_produced() -> None:
    reasoning_bridge_recommendations_produced_total.inc()


def record_recommendation_withheld() -> None:
    reasoning_bridge_recommendations_withheld_total.inc()


def record_class_change_update() -> None:
    reasoning_bridge_class_change_updates_total.inc()


def record_clear_transition_processed() -> None:
    reasoning_bridge_clear_transitions_processed_total.inc()


def record_failure() -> None:
    reasoning_bridge_failures_total.inc()


def record_processing_latency(seconds: float) -> None:
    reasoning_bridge_processing_latency_seconds.observe(seconds)


def record_publish_failure() -> None:
    reasoning_bridge_publish_failures_total.inc()


def record_worker_start() -> None:
    reasoning_bridge_worker_starts_total.inc()
