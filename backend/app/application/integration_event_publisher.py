"""Integration event publishing interface.

Concrete implementations live in infrastructure (e.g. Kafka).
"""

from __future__ import annotations

from typing import Protocol

from backend.app.application.integration_events import IntegrationEvent


class IntegrationEventPublisher(Protocol):
    def publish(self, event: IntegrationEvent) -> None: ...

