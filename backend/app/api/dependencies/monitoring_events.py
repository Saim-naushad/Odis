"""Dependency providers for monitoring SSE event sources."""

from typing import Annotated, cast

from fastapi import Depends, Request

from backend.app.application.monitoring_event_source import (
    MonitoringEventSource,
)


def get_monitoring_event_source(request: Request) -> MonitoringEventSource:
    """Return the application-scoped monitoring event source."""
    return cast(MonitoringEventSource, request.app.state.monitoring_event_source)


MonitoringEventSourceDep = Annotated[
    MonitoringEventSource, Depends(get_monitoring_event_source)
]
