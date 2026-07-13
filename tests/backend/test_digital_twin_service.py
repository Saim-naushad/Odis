from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.application.digital_twin_service import (
    DigitalTwinAssetNotFoundError,
    DigitalTwinNoReasoningHistoryError,
    DigitalTwinService,
)
from backend.app.domain.investigation import InvestigationEvent
from backend.app.domain.notification import Notification
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.recommendation import Recommendation
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.cache.memory_digital_twin_cache import (
    MemoryDigitalTwinCache,
)


class _FakeRun:
    def __init__(self, run_id: str, started_at: datetime) -> None:
        self.id = run_id
        self.started_at = started_at


class _FakeLatest:
    def __init__(self, run_id: str) -> None:
        self.run = _FakeRun(run_id, datetime(2026, 1, 1, tzinfo=UTC))


class _FakeMonitoringService:
    def __init__(
        self,
        *,
        history: list[object] | None,
        operational_state: OperationalState | None,
        recommendation: Recommendation | None,
        notification: Notification | None,
        timeline: list[TimelineEvent] | None,
        latest_run_id: str = "run-1",
        investigation: InvestigationEvent | None = None,
    ) -> None:
        self._history = history
        self._operational_state = operational_state
        self._recommendation = recommendation
        self._notification = notification
        self._timeline = timeline
        self._latest_run_id = latest_run_id
        self._investigation = investigation

    def asset_exists(self, asset_id: str) -> bool:
        return self._history is not None

    def get_history_for_asset(self, asset_id: str) -> list[object] | None:
        return self._history

    def get_latest_for_asset(self, asset_id: str) -> _FakeLatest | None:
        if not self.asset_exists(asset_id) or not self._history:
            return None
        return _FakeLatest(self._latest_run_id)

    def get_operational_state(self, asset_id: str) -> OperationalState | None:
        return self._operational_state

    def get_recommendation(self, asset_id: str) -> Recommendation | None:
        return self._recommendation

    def get_latest_notification(self, asset_id: str) -> Notification | None:
        return self._notification

    def get_latest_investigation_transition(
        self, recommendation_id: str
    ) -> InvestigationEvent | None:
        return self._investigation

    def get_timeline_for_asset(self, asset_id: str) -> list[TimelineEvent] | None:
        return self._timeline


def _timeline_event(event_id: str, ts: datetime) -> TimelineEvent:
    return TimelineEvent(
        id=event_id,
        asset_id="asset-1",
        timestamp=ts,
        event_type="reasoning_completed",
        title=f"Event {event_id}",
        description="desc",
        metadata={},
    )


def test_digital_twin_service_raises_when_asset_missing() -> None:
    monitoring = _FakeMonitoringService(
        history=None,
        operational_state=None,
        recommendation=None,
        notification=None,
        timeline=None,
    )
    service = DigitalTwinService(
        monitoring_service=monitoring,  # type: ignore[arg-type]
        cache=MemoryDigitalTwinCache(),
    )

    with pytest.raises(DigitalTwinAssetNotFoundError):
        service.get_for_asset("missing")


def test_digital_twin_service_raises_when_no_reasoning_history() -> None:
    monitoring = _FakeMonitoringService(
        history=[],
        operational_state=None,
        recommendation=None,
        notification=None,
        timeline=[],
    )
    service = DigitalTwinService(
        monitoring_service=monitoring,  # type: ignore[arg-type]
        cache=MemoryDigitalTwinCache(),
    )

    with pytest.raises(DigitalTwinNoReasoningHistoryError):
        service.get_for_asset("asset-1")


def test_digital_twin_service_assembles_preview_latest_five_in_order() -> None:
    asset_id = "fuel-cell-stack-01"
    state = OperationalState(
        asset_id=asset_id,
        health_score=90,
        health_status="NORMAL",
        risk_level="LOW",
        confidence=80,
        primary_driver="ok",
        recommended_action="monitor",
        last_updated=datetime(2026, 1, 2, tzinfo=UTC),
    )
    recommendation = Recommendation(
        id="rec-1",
        asset_id=asset_id,
        category="monitor",
        priority="P3",
        urgency="SCHEDULED",
        title="Monitor",
        description="desc",
        recommended_steps=("step",),
        estimated_impact="low",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    notification = None
    timeline = [
        _timeline_event("e1", datetime(2026, 1, 1, 0, 0, tzinfo=UTC)),
        _timeline_event("e2", datetime(2026, 1, 1, 0, 1, tzinfo=UTC)),
        _timeline_event("e3", datetime(2026, 1, 1, 0, 2, tzinfo=UTC)),
        _timeline_event("e4", datetime(2026, 1, 1, 0, 3, tzinfo=UTC)),
        _timeline_event("e5", datetime(2026, 1, 1, 0, 4, tzinfo=UTC)),
        _timeline_event("e6", datetime(2026, 1, 1, 0, 5, tzinfo=UTC)),
    ]

    monitoring = _FakeMonitoringService(
        history=[object()],
        operational_state=state,
        recommendation=recommendation,
        notification=notification,
        timeline=timeline,
        latest_run_id="run-99",
    )
    service = DigitalTwinService(
        monitoring_service=monitoring,  # type: ignore[arg-type]
        cache=MemoryDigitalTwinCache(),
    )

    twin = service.get_for_asset(asset_id)
    assert twin is not None

    assert twin.asset_id == asset_id
    assert twin.asset_name == "PEM Fuel Cell Stack 01"
    assert twin.asset_type == "PEM Fuel Cell Stack"
    assert twin.location.identifier == "North Production Line"
    assert twin.latest_reasoning_run_id == "run-99"
    assert twin.last_updated == state.last_updated
    assert [e.id for e in twin.timeline_preview] == ["e2", "e3", "e4", "e5", "e6"]


def test_digital_twin_service_falls_back_for_unknown_asset() -> None:
    asset_id = "not-a-plant-alpha-asset"
    state = OperationalState(
        asset_id=asset_id,
        health_score=90,
        health_status="NORMAL",
        risk_level="LOW",
        confidence=80,
        primary_driver="ok",
        recommended_action="monitor",
        last_updated=datetime(2026, 1, 2, tzinfo=UTC),
    )
    recommendation = Recommendation(
        id="rec-1",
        asset_id=asset_id,
        category="monitor",
        priority="P3",
        urgency="SCHEDULED",
        title="Monitor",
        description="desc",
        recommended_steps=("step",),
        estimated_impact="low",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    monitoring = _FakeMonitoringService(
        history=[object()],
        operational_state=state,
        recommendation=recommendation,
        notification=None,
        timeline=[],
        latest_run_id="run-1",
    )
    service = DigitalTwinService(
        monitoring_service=monitoring,  # type: ignore[arg-type]
        cache=MemoryDigitalTwinCache(),
    )

    twin = service.get_for_asset(asset_id)

    assert twin.asset_type == "unknown"
    assert twin.location.identifier == "unknown"
    assert twin.asset_name == "not a plant alpha asset"


def test_digital_twin_service_composes_investigation_by_recommendation_id() -> None:
    asset_id = "fuel-cell-stack-01"
    state = OperationalState(
        asset_id=asset_id,
        health_score=90,
        health_status="NORMAL",
        risk_level="LOW",
        confidence=80,
        primary_driver="ok",
        recommended_action="monitor",
        last_updated=datetime(2026, 1, 2, tzinfo=UTC),
    )
    recommendation = Recommendation(
        id="rec-42",
        asset_id=asset_id,
        category="monitor",
        priority="P3",
        urgency="SCHEDULED",
        title="Monitor",
        description="desc",
        recommended_steps=("step",),
        estimated_impact="low",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    investigation = InvestigationEvent(
        id="inv-1",
        asset_id=asset_id,
        recommendation_id="rec-42",
        status="ACKNOWLEDGED",
        actor_id="op-1",
        actor_display_name="Operator One",
        occurred_at=datetime(2026, 1, 2, 1, 0, tzinfo=UTC),
        notes="Looking into it",
    )

    monitoring = _FakeMonitoringService(
        history=[object()],
        operational_state=state,
        recommendation=recommendation,
        notification=None,
        timeline=[],
        investigation=investigation,
    )
    service = DigitalTwinService(
        monitoring_service=monitoring,  # type: ignore[arg-type]
        cache=MemoryDigitalTwinCache(),
    )

    twin = service.get_for_asset(asset_id)

    assert twin.investigation is investigation
    assert twin.investigation is not None
    assert twin.investigation.recommendation_id == recommendation.id

