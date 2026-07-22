"""Outbox dispatcher backlog metrics."""

from __future__ import annotations

from prometheus_client import Gauge

outbox_pending_events = Gauge(
    "outbox_pending_events",
    "Number of outbox events not yet dispatched, sampled at the end of "
    "each dispatch cycle",
)


def record_outbox_pending(count: int) -> None:
    outbox_pending_events.set(count)
