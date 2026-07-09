"""Integration Events — immutable messages emitted across service boundaries.

Integration events complement domain events: they are intended for external
consumers (Kafka) and must remain stable and versionable over time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class IntegrationEvent:
    """A stable, immutable integration message."""

    id: str
    type: str
    occurred_at: datetime
    payload: dict[str, Any]

