"""Operational state transition metrics."""

from __future__ import annotations

from prometheus_client import Counter

operational_state_transitions_total = Counter(
    "operational_state_transitions_total",
    "Total number of operational state transitions",
    labelnames=("from_state", "to_state"),
)


def record_operational_state_transition(
    *,
    from_state: str,
    to_state: str,
) -> None:
    """Increment when health status or risk level changes during reasoning."""
    operational_state_transitions_total.labels(
        from_state=from_state,
        to_state=to_state,
    ).inc()
