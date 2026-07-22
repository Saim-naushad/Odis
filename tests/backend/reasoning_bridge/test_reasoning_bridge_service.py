"""`ReasoningBridgeService` specification (PR178 spec sections 4, 7, 10,
16, 19 "Lifecycle" / "Persistence and events").

Uses a real (sqlite, in-memory) `UnitOfWork`/repository stack — this is
the persistence-integration layer the worker itself calls, so it is
tested against real persistence rather than a fake.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import AiFaultInvestigationUpdated
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.monitoring_event_handler import (
    MonitoringEventHandler,
)
from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_bridge.input_events import (
    ValidatedAlertTransition,
)
from backend.app.application.reasoning_bridge.reasoning_bridge_service import (
    ReasoningBridgeService,
    UnsupportedFaultClassError,
)
from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.ai_fault_evidence_repository import (
    SqlAlchemyAiFaultEvidenceRepository,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from backend.app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyTimelineRepository,
)

from .conftest import make_observation

_ASSET_ID = "fuel-cell-stack-01"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_INCREASING = [10.0, 10.0, 10.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
_DECREASING = [70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 10.0, 10.0, 10.0]


@pytest.fixture
def service(
    session_factory: Callable[[], Session],
) -> ReasoningBridgeService:
    return ReasoningBridgeService(lambda: SqlAlchemyUnitOfWork(session_factory))


def _seed_observations(
    session_factory: Callable[[], Session],
    *,
    asset_id: str,
    measurement: str,
    values: list[float],
    end: datetime,
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyObservationRepository(uow.session)
        for i, value in enumerate(values):
            timestamp = end - timedelta(seconds=(len(values) - i) * 10)
            repository.save(
                make_observation(
                    asset_id=asset_id,
                    measurement_type=measurement,
                    value=value,
                    unit="unit",
                    timestamp=timestamp,
                    observation_id=f"{measurement}-{i}",
                )
            )
        uow.commit()


def _event(**overrides: object) -> ValidatedAlertTransition:
    defaults: dict[str, object] = {
        "event_id": "evt-1",
        "event_version": "v1",
        "asset_id": _ASSET_ID,
        "source_timestamp": _T0,
        "transition_type": "confirmed",
        "from_state": "healthy",
        "to_state": "confirmed_cooling_degradation",
        "fault_class": "cooling_degradation",
        "diagnosed_class": "cooling_degradation",
        "evidence_items": ({"label": "x", "value": 1.0, "detail": "y"},),
        "model_system_version": "plant_alpha_fault_v1",
        "model_hash": "hash-a",
        "policy_hash": "policy-a",
        "feature_schema_version": "1.0",
        "class_scores": {"healthy": 0.05, "cooling_degradation": 0.9},
        "maximum_score": 0.9,
    }
    defaults.update(overrides)
    return ValidatedAlertTransition(**defaults)  # type: ignore[arg-type]


def test_first_confirmed_alert_creates_an_investigation_and_recommendation(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="stack_temperature",
        values=_INCREASING,
        end=_T0,
    )
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="coolant_flow",
        values=_DECREASING,
        end=_T0,
    )

    outcome = service.process_alert_transition(_event())

    assert outcome.is_duplicate is False
    assert outcome.is_new_investigation is True
    assert outcome.evidence.corroboration_result == "corroborated"
    assert outcome.evidence.investigation_status == "OPEN"
    assert outcome.evidence.recommendation is not None
    assert outcome.evidence.recommendation.status == "produced"
    assert outcome.evidence.source_event_id == "evt-1"


def test_duplicate_replay_is_idempotent(
    service: ReasoningBridgeService,
) -> None:
    first = service.process_alert_transition(_event())
    second = service.process_alert_transition(_event())

    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.evidence.id == first.evidence.id
    assert second.evidence.investigation_id == first.evidence.investigation_id


def test_duplicate_replay_does_not_create_a_second_investigation(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    service.process_alert_transition(_event())
    service.process_alert_transition(_event())

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyAiFaultEvidenceRepository(uow.session)
        latest = repository.get_latest_for_asset(_ASSET_ID)
        assert latest is not None
        assert latest.id == "evt-1"


def test_class_changed_updates_the_same_investigation(
    service: ReasoningBridgeService,
) -> None:
    first = service.process_alert_transition(_event())
    second = service.process_alert_transition(
        _event(
            event_id="evt-2",
            transition_type="class_changed",
            from_state="confirmed_cooling_degradation",
            to_state="confirmed_hydrogen_supply_issue",
            fault_class="hydrogen_supply_issue",
            diagnosed_class="hydrogen_supply_issue",
            source_timestamp=_T0 + timedelta(seconds=10),
        )
    )

    assert second.evidence.investigation_id == first.evidence.investigation_id
    assert second.evidence.previous_diagnosed_fault_class == "cooling_degradation"
    assert second.evidence.diagnosed_fault_class == "hydrogen_supply_issue"
    assert second.evidence.investigation_status == "OPEN"


def test_cleared_closes_the_investigation_without_a_recommendation(
    service: ReasoningBridgeService,
) -> None:
    first = service.process_alert_transition(_event())
    second = service.process_alert_transition(
        _event(
            event_id="evt-2",
            transition_type="cleared",
            from_state="confirmed_cooling_degradation",
            to_state="healthy",
            fault_class="cooling_degradation",
            diagnosed_class="healthy",
            source_timestamp=_T0 + timedelta(seconds=10),
        )
    )

    assert second.evidence.investigation_id == first.evidence.investigation_id
    assert second.evidence.investigation_status == "CLEARED"
    assert second.evidence.corroboration_result == "not_applicable"
    assert second.evidence.recommendation is None


def test_new_alert_after_clear_creates_a_new_occurrence(
    service: ReasoningBridgeService,
) -> None:
    first = service.process_alert_transition(_event())
    service.process_alert_transition(
        _event(
            event_id="evt-2",
            transition_type="cleared",
            from_state="confirmed_cooling_degradation",
            to_state="healthy",
            fault_class="cooling_degradation",
            diagnosed_class="healthy",
            source_timestamp=_T0 + timedelta(seconds=10),
        )
    )
    third = service.process_alert_transition(
        _event(
            event_id="evt-3",
            transition_type="confirmed",
            from_state="healthy",
            to_state="confirmed_cooling_degradation",
            fault_class="cooling_degradation",
            diagnosed_class="cooling_degradation",
            source_timestamp=_T0 + timedelta(seconds=20),
        )
    )

    assert third.evidence.investigation_id != first.evidence.investigation_id
    assert third.is_new_investigation is True
    assert third.evidence.investigation_status == "OPEN"


def test_unsupported_fault_class_is_rejected(
    service: ReasoningBridgeService,
) -> None:
    with pytest.raises(UnsupportedFaultClassError):
        service.process_alert_transition(
            _event(
                to_state="confirmed_membrane_dehydration",
                fault_class="membrane_dehydration",
                diagnosed_class="membrane_dehydration",
            )
        )


def test_evidence_provenance_is_retained(
    service: ReasoningBridgeService,
) -> None:
    outcome = service.process_alert_transition(_event())
    evidence = outcome.evidence
    assert evidence.source_event_id == "evt-1"
    assert evidence.model_system_version == "plant_alpha_fault_v1"
    assert evidence.model_hash == "hash-a"
    assert evidence.policy_hash == "policy-a"
    assert evidence.feature_schema_version == "1.0"
    assert evidence.class_scores == {"healthy": 0.05, "cooling_degradation": 0.9}
    assert evidence.evidence_items == (
        {"label": "x", "value": 1.0, "detail": "y"},
    )


def test_never_persists_all_features_only_curated_evidence_items(
    service: ReasoningBridgeService,
) -> None:
    """Spec section 5: 'do not persist all 153 features' — only the small
    curated `evidence_items` list PR176/177 already compute is stored."""
    outcome = service.process_alert_transition(_event())
    assert len(outcome.evidence.evidence_items) <= 5


def test_timeline_entries_are_written_for_a_processed_alert(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    service.process_alert_transition(_event())

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyTimelineRepository(uow.session)
        entries = repository.list_by_asset(_ASSET_ID)

    event_types = {entry.event_type for entry in entries}
    assert "ai_fault_alert_received" in event_types
    assert "ai_fault_corroboration_completed" in event_types
    assert "ai_fault_investigation_updated" in event_types
    assert "ai_fault_recommendation_recorded" in event_types


def test_corroboration_only_uses_observations_from_the_alerts_own_asset(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    """PR178 correction spec ("Corroboration window and provenance"):
    the corroboration window is asset-scoped — a corroborating series
    recorded under a different asset must not corroborate this alert."""
    _seed_observations(
        session_factory,
        asset_id="fuel-cell-stack-02",
        measurement="stack_temperature",
        values=_INCREASING,
        end=_T0,
    )
    _seed_observations(
        session_factory,
        asset_id="fuel-cell-stack-02",
        measurement="coolant_flow",
        values=_DECREASING,
        end=_T0,
    )

    outcome = service.process_alert_transition(_event())

    assert outcome.evidence.corroboration_result == "insufficient_evidence"
    assert outcome.evidence.recommendation is not None
    assert outcome.evidence.recommendation.supporting_observation_ids == ()


def test_corroboration_excludes_observations_after_the_alert_source_timestamp(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    """A corroborating series recorded strictly after the alert's own
    `source_timestamp` must be excluded — corroboration can only use
    evidence that existed at (or before) the moment the alert fired, not
    telemetry from later ticks."""
    future_end = _T0 + timedelta(hours=1)
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="stack_temperature",
        values=_INCREASING,
        end=future_end,
    )
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="coolant_flow",
        values=_DECREASING,
        end=future_end,
    )

    outcome = service.process_alert_transition(_event())

    assert outcome.evidence.corroboration_result == "insufficient_evidence"


def test_corroboration_excludes_observations_older_than_the_window(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    """Observations older than `corroboration_window_seconds` (default
    900s) before the alert's `source_timestamp` are stale and must not be
    used — this must fall back to `insufficient_evidence`, not reason
    against out-of-window history."""
    stale_end = _T0 - timedelta(seconds=2000)
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="stack_temperature",
        values=_INCREASING,
        end=stale_end,
    )
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="coolant_flow",
        values=_DECREASING,
        end=stale_end,
    )

    outcome = service.process_alert_transition(_event())

    assert outcome.evidence.corroboration_result == "insufficient_evidence"


def test_supporting_observation_ids_are_traceable_to_the_fetched_window(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    """The recommendation's `supporting_observation_ids` must name exactly
    the observations that were actually fetched for corroboration (the
    in-window, same-asset ones) — not stale or future observations that
    happen to share the asset and measurement type."""
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="stack_temperature",
        values=_INCREASING,
        end=_T0,
    )
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="coolant_flow",
        values=_DECREASING,
        end=_T0,
    )
    # A stale, out-of-window duplicate under distinct ids that must not
    # appear in the supporting-evidence list.
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyObservationRepository(uow.session)
        repository.save(
            make_observation(
                asset_id=_ASSET_ID,
                measurement_type="stack_temperature",
                value=999.0,
                unit="unit",
                timestamp=_T0 - timedelta(seconds=5000),
                observation_id="stale-outlier",
            )
        )
        uow.commit()

    outcome = service.process_alert_transition(_event())

    assert outcome.evidence.recommendation is not None
    supporting_ids = outcome.evidence.recommendation.supporting_observation_ids
    assert "obs-fuel-cell-stack-01-stale-outlier" not in supporting_ids
    assert all(
        ("stack_temperature-" in observation_id or "coolant_flow-" in observation_id)
        for observation_id in supporting_ids
    )


def test_class_changed_corroboration_uses_the_new_events_own_source_timestamp(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    """A `class_changed` transition must corroborate against its *own*
    `source_timestamp`'s window, not the earlier alert's — otherwise a
    stale first-alert window would silently keep being reused for every
    subsequent class change."""
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="stack_temperature",
        values=_INCREASING,
        end=_T0,
    )
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="coolant_flow",
        values=_DECREASING,
        end=_T0,
    )
    first = service.process_alert_transition(_event())
    assert first.evidence.corroboration_result == "corroborated"

    second_timestamp = _T0 + timedelta(seconds=30)
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="fuel_flow",
        values=_DECREASING,
        end=second_timestamp,
    )
    _seed_observations(
        session_factory,
        asset_id=_ASSET_ID,
        measurement="voltage",
        values=_DECREASING,
        end=second_timestamp,
    )

    second = service.process_alert_transition(
        _event(
            event_id="evt-2",
            transition_type="class_changed",
            from_state="confirmed_cooling_degradation",
            to_state="confirmed_hydrogen_supply_issue",
            fault_class="hydrogen_supply_issue",
            diagnosed_class="hydrogen_supply_issue",
            source_timestamp=second_timestamp,
        )
    )

    assert second.evidence.corroboration_result == "corroborated"
    assert second.evidence.recommendation is not None
    supporting_ids = second.evidence.recommendation.supporting_observation_ids
    assert any("fuel_flow-" in oid for oid in supporting_ids)
    assert any("voltage-" in oid for oid in supporting_ids)


def test_cleared_writes_a_distinct_cleared_timeline_entry(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    service.process_alert_transition(_event())
    service.process_alert_transition(
        _event(
            event_id="evt-2",
            transition_type="cleared",
            from_state="confirmed_cooling_degradation",
            to_state="healthy",
            fault_class="cooling_degradation",
            diagnosed_class="healthy",
            source_timestamp=_T0 + timedelta(seconds=10),
        )
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyTimelineRepository(uow.session)
        entries = repository.list_by_asset(_ASSET_ID)

    event_types = [entry.event_type for entry in entries]
    assert "ai_fault_alert_cleared" in event_types


def test_processed_alert_writes_an_outbox_event_and_publishes_to_the_bus(
    session_factory: Callable[[], Session],
) -> None:
    """PR179: a processed alert transition must reach the SSE pipeline via
    the same outbox -> DomainEventBus mechanism `InvestigationService`
    uses — not a bespoke path."""
    event_bus = DomainEventBus()
    published: list[AiFaultInvestigationUpdated] = []
    event_bus.subscribe(AiFaultInvestigationUpdated, published.append)
    outbox_dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory), event_bus
    )
    service = ReasoningBridgeService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        event_bus=event_bus,
        outbox_dispatcher=outbox_dispatcher,
    )

    outcome = service.process_alert_transition(_event())

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        rows = uow.session.scalars(select(OutboxEvent)).all()
    assert len(rows) == 1
    assert rows[0].event_type == "AiFaultInvestigationUpdated"
    assert rows[0].dispatched_at is not None  # dispatch() ran synchronously

    assert len(published) == 1
    assert published[0].asset_id == outcome.evidence.asset_id
    assert published[0].investigation_id == outcome.evidence.investigation_id


def test_duplicate_replay_does_not_write_a_second_outbox_event(
    session_factory: Callable[[], Session],
) -> None:
    event_bus = DomainEventBus()
    outbox_dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory), event_bus
    )
    service = ReasoningBridgeService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        event_bus=event_bus,
        outbox_dispatcher=outbox_dispatcher,
    )

    service.process_alert_transition(_event())
    service.process_alert_transition(_event())  # duplicate, same event_id

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        rows = uow.session.scalars(select(OutboxEvent)).all()
    assert len(rows) == 1


def test_without_event_bus_no_outbox_event_is_written(
    service: ReasoningBridgeService,
    session_factory: Callable[[], Session],
) -> None:
    """The default `event_bus=None` (used by direct unit-test construction)
    must not attempt to write an outbox row."""
    service.process_alert_transition(_event())

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        rows = uow.session.scalars(select(OutboxEvent)).all()
    assert rows == []


def test_processed_alert_reaches_the_sse_event_source_as_a_minimal_signal(
    session_factory: Callable[[], Session],
) -> None:
    """End-to-end proof of the PR179 SSE bridge: process_alert_transition
    -> outbox -> DomainEventBus -> MonitoringEventHandler -> a subscribed
    SSE queue receives `fault_investigation_updated` carrying only
    type/timestamp/asset_id — never the full evidence payload."""
    event_bus = DomainEventBus()
    event_source = InMemoryMonitoringEventSource()
    monitoring_handler = MonitoringEventHandler(event_source)
    event_bus.subscribe(
        AiFaultInvestigationUpdated,
        monitoring_handler.on_ai_fault_investigation_updated,
    )
    outbox_dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory), event_bus
    )
    service = ReasoningBridgeService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        event_bus=event_bus,
        outbox_dispatcher=outbox_dispatcher,
    )
    queue = event_source.subscribe()

    outcome = service.process_alert_transition(_event())

    sse_event = queue.get_nowait()
    assert sse_event.type == "fault_investigation_updated"
    assert sse_event.asset_id == outcome.evidence.asset_id
    assert sse_event.run_id is None
    payload = sse_event.to_json_dict()
    assert set(payload.keys()) == {"type", "timestamp", "asset_id"}
