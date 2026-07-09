"""Reasoning worker orchestration specifications."""

from collections.abc import Generator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.reasoning_session import ReasoningSession
from backend.app.application.events.domain_events import ReasoningCompleted
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
from backend.app.application.reasoning_worker import ReasoningWorker
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.reasoning_job import ReasoningJobStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.models.reasoning_job import ReasoningJobModel
from backend.app.infrastructure.database.models.reasoning_run_index import (
    ReasoningRunIndexModel,
)
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


def _database_queue_factory(uow: UnitOfWork[Session]) -> DatabaseReasoningJobQueue:
    return DatabaseReasoningJobQueue(SqlAlchemyReasoningJobRepository(uow.session))


def _build_observation_service(
    db_session: Session,
    event_bus: DomainEventBus,
    outbox_dispatcher: OutboxDispatcher,
) -> ObservationService:
    reasoning_session = ReasoningSession(
        profile=DEFAULT_OPERATIONAL_PROFILE,
        situation_repository=SqlAlchemySituationRepository(db_session),
        decision_context_repository=SqlAlchemyDecisionContextRepository(db_session),
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(db_session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(db_session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(db_session),
    )
    return ObservationService(
        SqlAlchemyUnitOfWork(lambda: db_session),
        SqlAlchemyObservationRepository(db_session),
        event_bus=event_bus,
        outbox_dispatcher=outbox_dispatcher,
        reasoning_job_queue=DatabaseReasoningJobQueue(
            SqlAlchemyReasoningJobRepository(db_session),
        ),
        reasoning_session=reasoning_session,
        structured_assessment_repository=SqlAlchemyStructuredAssessmentRepository(
            db_session
        ),
        reasoning_trace_repository=SqlAlchemyReasoningTraceRepository(db_session),
    )


def test_worker_processes_pending_job_and_persists_reasoning_artifacts(
    db_session: Session,
) -> None:
    event_bus = DomainEventBus()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        event_bus,
    )
    service = _build_observation_service(db_session, event_bus, dispatcher)
    first = build_observation(
        id="obs-worker-1",
        value=30.0,
        timestamp=build_observation().timestamp,
    )
    second = build_observation(
        id="obs-worker-2",
        value=45.0,
        timestamp=build_observation().timestamp.replace(hour=13),
    )
    service.create(first)
    service.create(second)

    worker = ReasoningWorker(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        _database_queue_factory,
        event_bus,
        dispatcher,
    )

    assert worker.process_next() is True
    assert worker.process_next() is True
    assert worker.process_next() is False

    jobs = db_session.scalars(select(ReasoningJobModel)).all()
    assert len(jobs) == 2
    assert all(job.status == ReasoningJobStatus.COMPLETED.value for job in jobs)

    index_models = db_session.scalars(select(ReasoningRunIndexModel)).all()
    assert len(index_models) == 2


def test_worker_marks_job_failed_when_reasoning_raises(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_bus = DomainEventBus()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        event_bus,
    )
    service = _build_observation_service(db_session, event_bus, dispatcher)
    service.create(build_observation(id="obs-worker-fail"))

    def _raise(_asset_id: str) -> bool:
        raise RuntimeError("reasoning exploded")

    monkeypatch.setattr(
        "backend.app.application.reasoning_worker.create_observation_service",
        lambda *_args, **_kwargs: type(
            "BrokenService",
            (),
            {"run_reasoning_for_asset": staticmethod(_raise)},
        )(),
    )

    worker = ReasoningWorker(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        _database_queue_factory,
        event_bus,
        dispatcher,
    )

    with pytest.raises(RuntimeError, match="reasoning exploded"):
        worker.process_next()

    job = db_session.scalars(select(ReasoningJobModel)).one()
    assert job.status == ReasoningJobStatus.FAILED.value
    assert job.attempts == 1


def test_worker_dispatches_outbox_events(
    db_session: Session,
) -> None:
    event_source = InMemoryMonitoringEventSource()
    event_bus = DomainEventBus()
    handler = MonitoringEventHandler(event_source)
    event_bus.subscribe(ReasoningCompleted, handler.on_reasoning_completed)
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        event_bus,
    )
    service = _build_observation_service(db_session, event_bus, dispatcher)
    first = build_observation(
        id="obs-worker-event-1",
        value=30.0,
        timestamp=build_observation().timestamp,
    )
    second = build_observation(
        id="obs-worker-event-2",
        value=45.0,
        timestamp=build_observation().timestamp.replace(hour=13),
    )
    service.create(first)
    service.create(second)
    queue = event_source.subscribe()

    worker = ReasoningWorker(
        lambda: SqlAlchemyUnitOfWork(lambda: db_session),
        _database_queue_factory,
        event_bus,
        dispatcher,
    )
    worker.process_next()
    worker.process_next()

    run_event = queue.get_nowait()
    assert run_event.type == "run_updated"
    assert run_event.asset_id == first.asset_id
    assert run_event.run_id is not None
