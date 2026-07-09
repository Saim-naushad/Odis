"""TrendChanged timeline event generation specifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import List

from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.observation_service import ObservationService
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


class _FakeUow:
    def __init__(self) -> None:
        self.session = _FakeSession()

    def commit(self) -> None:
        return


class _FakeObservationRepository:
    def __init__(self, observations: list[Observation]) -> None:
        self._observations = observations

    def save(self, observation: Observation) -> None:  # pragma: no cover
        self._observations.append(observation)

    def get(self, observation_id: str) -> Observation | None:  # pragma: no cover
        return next((o for o in self._observations if o.id == observation_id), None)

    def list(self) -> List[Observation]:  # pragma: no cover
        return list(self._observations)

    def list_by_asset(self, asset_id: str) -> List[Observation]:
        return [o for o in self._observations if o.asset_id == asset_id]


@dataclass(frozen=True)
class _FakeRun:
    id: str
    started_at: datetime


@dataclass(frozen=True)
class _FakePlan:
    recommendation: str


@dataclass(frozen=True)
class _FakeReasoningResult:
    run: _FakeRun
    plan: _FakePlan
    structured_assessment: object | None = None
    trace: object | None = None


class _FakeReasoningSession:
    def run(
        self, goal: object, observations: list[Observation]
    ) -> _FakeReasoningResult:
        _ = goal
        _ = observations
        return _FakeReasoningResult(
            run=_FakeRun(id="run-1", started_at=datetime.now(UTC)),
            plan=_FakePlan(recommendation="Monitor"),
        )


def _obs(idx: int, value: float) -> Observation:
    ts = datetime(2026, 1, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=idx)
    return Observation(
        id=f"obs-{idx}",
        asset_id="asset-1",
        timestamp=ts,
        measurement_type=MeasurementType(name="Temperature"),
        value=value,
        unit="C",
    )


def test_observation_service_emits_trend_changed_when_direction_becomes_meaningful(
) -> None:
    # Window behavior:
    # prev window (obs-0..obs-4): unstable due to outlier, classified as stable.
    # new window (obs-1..obs-5): sustained rising, classified as rising.
    observations = [
        _obs(0, 20.0),
        _obs(1, 10.0),
        _obs(2, 11.0),
        _obs(3, 12.0),
        _obs(4, 13.0),
        _obs(5, 14.0),
    ]
    uow = _FakeUow()
    repo = _FakeObservationRepository(observations)
    service = ObservationService(
        uow,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        event_bus=DomainEventBus(),
        reasoning_session=_FakeReasoningSession(),  # type: ignore[arg-type]
    )

    assert service.run_reasoning_for_asset("asset-1") is True

    outbox_events = [e for e in uow.session.added if getattr(e, "event_type", None)]
    assert any(
        getattr(event, "event_type", None) == "TrendChanged"
        for event in outbox_events
    )

