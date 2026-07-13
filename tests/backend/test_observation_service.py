"""Observation service reasoning orchestration specifications."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from application.reasoning_session import ReasoningSession
from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.monitoring_event_handler import (
    MonitoringEventHandler,
)
from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
)
from backend.app.application.observation_service import ObservationService
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_PROFILE
from backend.app.application.reasoning_job_queue import DatabaseReasoningJobQueue
from backend.app.domain.reasoning_job import ReasoningJobStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.decision_context_repository import (
    SqlAlchemyDecisionContextRepository,
)
from backend.app.infrastructure.repositories.decision_plan_repository import (
    SqlAlchemyDecisionPlanRepository,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)
from backend.app.infrastructure.repositories.reasoning_run_index_repository import (
    SqlAlchemyReasoningRunIndexRepository,
)
from backend.app.infrastructure.repositories.reasoning_run_repository import (
    SqlAlchemyReasoningRunRepository,
)
from backend.app.infrastructure.repositories.reasoning_trace_repository import (
    SqlAlchemyReasoningTraceRepository,
)
from backend.app.infrastructure.repositories.situation_repository import (
    SqlAlchemySituationRepository,
)
from backend.app.infrastructure.repositories.structured_assessment_repository import (
    SqlAlchemyStructuredAssessmentRepository,
)
from domain.value_objects.trend_direction import TrendDirection
from tests.backend.helpers import assert_at_most_one_outstanding_job_per_asset
from tests.builders import build_observation


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def db_session(sqlite_settings: Settings) -> Generator[Session, None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def observation_service(db_session: Session) -> ObservationService:
    reasoning_session = ReasoningSession(
        profile=DEFAULT_OPERATIONAL_PROFILE,
        situation_repository=SqlAlchemySituationRepository(db_session),
        decision_context_repository=SqlAlchemyDecisionContextRepository(db_session),
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(db_session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(db_session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(db_session),
    )
    uow = SqlAlchemyUnitOfWork(lambda: db_session)
    return ObservationService(
        uow,
        SqlAlchemyObservationRepository(db_session),
        reasoning_session=reasoning_session,
        structured_assessment_repository=SqlAlchemyStructuredAssessmentRepository(
            db_session
        ),
        reasoning_trace_repository=SqlAlchemyReasoningTraceRepository(db_session),
    )


def test_create_enqueues_reasoning_job(
    db_session: Session,
) -> None:
    service = ObservationService(
        SqlAlchemyUnitOfWork(lambda: db_session),
        SqlAlchemyObservationRepository(db_session),
        reasoning_job_queue=DatabaseReasoningJobQueue(
            SqlAlchemyReasoningJobRepository(db_session),
        ),
    )
    observation = build_observation(id="obs-enqueue")

    result = service.create(observation)

    assert result.observation == observation
    assert result.job is not None
    assert result.job.asset_id == observation.asset_id
    assert result.job.status == ReasoningJobStatus.PENDING


def test_create_twice_before_claim_coalesces_into_one_job(
    db_session: Session,
) -> None:
    """Two writes for the same asset before any claim must not create two
    outstanding jobs — ObservationService needs no dirty-flag awareness of
    its own for this; the queue absorbs the second request transparently."""
    service = ObservationService(
        SqlAlchemyUnitOfWork(lambda: db_session),
        SqlAlchemyObservationRepository(db_session),
        reasoning_job_queue=DatabaseReasoningJobQueue(
            SqlAlchemyReasoningJobRepository(db_session),
        ),
    )
    first = build_observation(
        id="obs-coalesce-1",
        value=30.0,
        timestamp=build_observation().timestamp,
    )
    second = build_observation(
        id="obs-coalesce-2",
        value=45.0,
        timestamp=build_observation().timestamp.replace(hour=13),
    )

    first_result = service.create(first)
    second_result = service.create(second)

    assert first_result.job is not None
    assert second_result.job is not None
    assert second_result.job.id == first_result.job.id

    from sqlalchemy import select

    from backend.app.infrastructure.database.models.reasoning_job import (
        ReasoningJobModel,
    )

    jobs = db_session.scalars(select(ReasoningJobModel)).all()
    assert len(jobs) == 1
    assert_at_most_one_outstanding_job_per_asset(db_session)


def test_create_single_observation_does_not_run_reasoning(
    observation_service: ObservationService,
    db_session: Session,
) -> None:
    observation = build_observation(id="obs-single")

    observation_service.create(observation)

    from sqlalchemy import select

    from backend.app.infrastructure.database.models.reasoning_run import (
        ReasoningRunModel,
    )

    assert db_session.scalars(select(ReasoningRunModel)).all() == []


def test_create_second_observation_runs_reasoning_and_persists_artifacts(
    observation_service: ObservationService,
    db_session: Session,
) -> None:
    first = build_observation(
        id="obs-reason-1",
        value=30.0,
        timestamp=build_observation().timestamp,
    )
    second = build_observation(
        id="obs-reason-2",
        value=45.0,
        timestamp=build_observation().timestamp.replace(hour=13),
    )

    observation_service.create(first)
    observation_service.create(second)
    observation_service.run_reasoning_for_asset(first.asset_id)

    from sqlalchemy import select

    from backend.app.infrastructure.database.models.reasoning_run_index import (
        ReasoningRunIndexModel,
    )

    run_repository = SqlAlchemyReasoningRunRepository(db_session)
    assessment_repository = SqlAlchemyStructuredAssessmentRepository(db_session)
    trace_repository = SqlAlchemyReasoningTraceRepository(db_session)
    index_repository = SqlAlchemyReasoningRunIndexRepository(db_session)
    situation_repository = SqlAlchemySituationRepository(db_session)
    context_repository = SqlAlchemyDecisionContextRepository(db_session)
    plan_repository = SqlAlchemyDecisionPlanRepository(db_session)

    index_models = db_session.scalars(select(ReasoningRunIndexModel)).all()
    assert len(index_models) == 1
    index = index_repository.get(index_models[0].run_id)
    assert index is not None

    run = run_repository.get(index.run_id)
    assert run is not None

    assessment = assessment_repository.get_by_run_id(index.run_id)
    assert assessment is not None
    assert assessment.trend_direction == TrendDirection.INCREASING

    trace = trace_repository.get_by_run_id(index.run_id)
    assert trace is not None
    assert len(trace.steps) == 18

    situation = situation_repository.get(index.situation_id)
    assert situation is not None
    assert situation.observation_ids == ("obs-reason-1", "obs-reason-2")

    context = context_repository.get(index.context_id)
    assert context is not None
    assert context.situation_id == situation.id

    plan = plan_repository.get(index.plan_id)
    assert plan is not None
    assert plan.context_id == context.id


def test_create_publishes_asset_updated_event(
    db_session: Session,
) -> None:
    event_source = InMemoryMonitoringEventSource()
    event_bus = DomainEventBus()
    handler = MonitoringEventHandler(event_source)
    event_bus.subscribe(ObservationCreated, handler.on_observation_created)
    event_bus.subscribe(ReasoningCompleted, handler.on_reasoning_completed)
    reasoning_session = ReasoningSession(
        profile=DEFAULT_OPERATIONAL_PROFILE,
        situation_repository=SqlAlchemySituationRepository(db_session),
        decision_context_repository=SqlAlchemyDecisionContextRepository(db_session),
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(db_session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(db_session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(db_session),
    )
    service = ObservationService(
        SqlAlchemyUnitOfWork(lambda: db_session),
        SqlAlchemyObservationRepository(db_session),
        reasoning_session=reasoning_session,
        event_bus=event_bus,
        outbox_dispatcher=OutboxDispatcher(
            lambda: SqlAlchemyUnitOfWork(lambda: db_session),
            event_bus,
        ),
    )
    queue = event_source.subscribe()

    observation = build_observation(id="obs-event-1")
    service.create(observation)

    event = queue.get_nowait()
    assert event.type == "asset_updated"
    assert event.asset_id == observation.asset_id
    assert event.run_id is None


def test_create_publishes_run_and_asset_events_when_reasoning_runs(
    db_session: Session,
) -> None:
    event_source = InMemoryMonitoringEventSource()
    event_bus = DomainEventBus()
    handler = MonitoringEventHandler(event_source)
    event_bus.subscribe(ObservationCreated, handler.on_observation_created)
    event_bus.subscribe(ReasoningCompleted, handler.on_reasoning_completed)
    reasoning_session = ReasoningSession(
        profile=DEFAULT_OPERATIONAL_PROFILE,
        situation_repository=SqlAlchemySituationRepository(db_session),
        decision_context_repository=SqlAlchemyDecisionContextRepository(db_session),
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(db_session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(db_session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(db_session),
    )
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        event_bus,
    )
    service = ObservationService(
        SqlAlchemyUnitOfWork(lambda: db_session),
        SqlAlchemyObservationRepository(db_session),
        event_bus=event_bus,
        reasoning_session=reasoning_session,
        outbox_dispatcher=dispatcher,
        structured_assessment_repository=SqlAlchemyStructuredAssessmentRepository(
            db_session
        ),
        reasoning_trace_repository=SqlAlchemyReasoningTraceRepository(db_session),
    )
    queue = event_source.subscribe()

    first = build_observation(
        id="obs-event-2a",
        value=30.0,
        timestamp=build_observation().timestamp,
    )
    second = build_observation(
        id="obs-event-2b",
        value=45.0,
        timestamp=build_observation().timestamp.replace(hour=13),
    )
    service.create(first)
    service.create(second)
    service.run_reasoning_for_asset(second.asset_id)
    db_session.commit()
    dispatcher.dispatch()

    first_asset_event = queue.get_nowait()
    assert first_asset_event.type == "asset_updated"
    assert first_asset_event.asset_id == first.asset_id
    assert first_asset_event.run_id is None

    second_asset_event = queue.get_nowait()
    assert second_asset_event.type == "asset_updated"
    assert second_asset_event.asset_id == second.asset_id
    assert second_asset_event.run_id is None

    run_event = queue.get_nowait()
    assert run_event.type == "run_updated"
    assert run_event.asset_id == second.asset_id
    assert run_event.run_id is not None

    reasoning_asset_event = queue.get_nowait()
    assert reasoning_asset_event.type == "asset_updated"
    assert reasoning_asset_event.asset_id == second.asset_id
    assert reasoning_asset_event.run_id == run_event.run_id
