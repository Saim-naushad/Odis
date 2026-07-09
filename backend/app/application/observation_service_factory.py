"""Factory for wiring an observation service to a database session."""

from sqlalchemy.orm import Session

from application.reasoning_session import ReasoningSession
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.observation_service import ObservationService
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_PROFILE
from backend.app.application.reasoning_job_queue import DatabaseReasoningJobQueue
from backend.app.application.unit_of_work import UnitOfWork
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
from domain.repositories.observation_repository import ObservationRepository


def create_observation_service(
    uow: UnitOfWork[Session],
    event_bus: DomainEventBus,
    outbox_dispatcher: OutboxDispatcher | None = None,
) -> ObservationService:
    """Build an observation service wired to the given session."""
    session = uow.session
    reasoning_session = ReasoningSession(
        profile=DEFAULT_OPERATIONAL_PROFILE,
        situation_repository=SqlAlchemySituationRepository(session),
        decision_context_repository=SqlAlchemyDecisionContextRepository(session),
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(session),
    )
    structured_assessment_repository: StructuredAssessmentRepository = (
        SqlAlchemyStructuredAssessmentRepository(session)
    )
    reasoning_trace_repository: ReasoningTraceRepository = (
        SqlAlchemyReasoningTraceRepository(session)
    )
    repository: ObservationRepository = SqlAlchemyObservationRepository(session)
    reasoning_job_queue = DatabaseReasoningJobQueue(
        SqlAlchemyReasoningJobRepository(session),
    )
    return ObservationService(
        uow,
        repository,
        event_bus=event_bus,
        outbox_dispatcher=outbox_dispatcher,
        reasoning_job_queue=reasoning_job_queue,
        reasoning_session=reasoning_session,
        structured_assessment_repository=structured_assessment_repository,
        reasoning_trace_repository=reasoning_trace_repository,
        decision_plan_repository=SqlAlchemyDecisionPlanRepository(session),
        reasoning_run_index_repository=SqlAlchemyReasoningRunIndexRepository(session),
        reasoning_run_repository=SqlAlchemyReasoningRunRepository(session),
    )
