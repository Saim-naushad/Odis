"""Backward-compatible publisher export."""

from backend.simulator.publishers.http_publisher import HttpObservationPublisher

ObservationPublisher = HttpObservationPublisher

__all__ = ["ObservationPublisher"]
