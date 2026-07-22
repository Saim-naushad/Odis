"""Integration event publishing interface.

Concrete implementations live in infrastructure (e.g. Kafka).
"""

from __future__ import annotations

from typing import Protocol

from backend.app.application.integration_events import IntegrationEvent


class IntegrationEventPublisher(Protocol):
    def publish(self, event: IntegrationEvent) -> bool:
        """Publish an event; return True on confirmed delivery.

        Implementations must swallow their own transport failures (logging
        instead) and return False rather than raising, so a failed publish
        can be retried by the caller instead of losing the event.
        """
        ...

