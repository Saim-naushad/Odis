"""Digital Twin domain aggregate.

The Digital Twin is an operator-facing projection that aggregates existing
domain concepts for a single asset. It intentionally owns no business rules
and does not duplicate computation or persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.domain.notification import Notification
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.recommendation import Recommendation
from backend.app.domain.timeline import TimelineEvent
from domain.value_objects.location import Location
from domain.value_objects.telemetry_forecast import TelemetryForecast


@dataclass(frozen=True, slots=True)
class DigitalTwin:
    """Immutable unified view of an asset for operators."""

    asset_id: str
    asset_name: str
    asset_type: str
    location: Location
    operational_state: OperationalState
    recommendation: Recommendation
    notification: Notification | None
    latest_reasoning_run_id: str
    timeline_preview: tuple[TimelineEvent, ...]
    telemetry_forecasts: tuple[TelemetryForecast, ...]
    last_updated: datetime

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not self.asset_name:
            raise ValueError("asset_name must not be empty")
        if not self.asset_type:
            raise ValueError("asset_type must not be empty")
        if not self.latest_reasoning_run_id:
            raise ValueError("latest_reasoning_run_id must not be empty")
        if not isinstance(self.last_updated, datetime):
            raise ValueError("last_updated must be a datetime")
