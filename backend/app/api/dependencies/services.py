"""Application service dependency providers for route handlers."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.api.dependencies.database import get_unit_of_work
from backend.app.api.dependencies.repositories import (
    get_decision_context_repository,
    get_decision_plan_repository,
    get_observation_repository,
    get_reasoning_run_index_repository,
    get_reasoning_run_repository,
    get_reasoning_trace_repository,
    get_situation_repository,
    get_structured_assessment_repository,
    get_timeline_repository,
)
from backend.app.api.routers.platform import REASONING_ENGINE_VERSION
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.health_service import HealthService
from backend.app.application.monitoring_service import MonitoringService
from backend.app.application.observation_service import ObservationService
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_task_runner import ReasoningTaskRunner
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.repositories.timeline_repository import TimelineRepository
from backend.app.infrastructure.config.settings import get_settings
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
from domain.repositories.situation_repository import SituationRepository


def get_domain_event_bus(request: Request) -> DomainEventBus:
    bus = getattr(request.app.state, "domain_event_bus", None)
    if not isinstance(bus, DomainEventBus):
        msg = "Domain event bus is not configured on the application"
        raise RuntimeError(msg)
    return bus


def get_outbox_dispatcher(request: Request) -> OutboxDispatcher:
    dispatcher = getattr(request.app.state, "outbox_dispatcher", None)
    if not isinstance(dispatcher, OutboxDispatcher):
        msg = "Outbox dispatcher is not configured on the application"
        raise RuntimeError(msg)
    return dispatcher


def get_observation_service(
    uow: Annotated[UnitOfWork[Session], Depends(get_unit_of_work)],
    event_bus: Annotated[DomainEventBus, Depends(get_domain_event_bus)],
    outbox_dispatcher: Annotated[OutboxDispatcher, Depends(get_outbox_dispatcher)],
) -> ObservationService:
    """Provide a request-scoped observation application service."""
    return create_observation_service(uow, event_bus, outbox_dispatcher)


def get_reasoning_task_runner(request: Request) -> ReasoningTaskRunner:
    """Return the application-scoped background reasoning runner."""
    runner = getattr(request.app.state, "reasoning_task_runner", None)
    if not isinstance(runner, ReasoningTaskRunner):
        msg = "Reasoning task runner is not configured on the application"
        raise RuntimeError(msg)
    return runner


def get_monitoring_service(
    observation_repository: Annotated[
        ObservationRepository, Depends(get_observation_repository)
    ],
    reasoning_run_repository: Annotated[
        ReasoningRunRepository, Depends(get_reasoning_run_repository)
    ],
    reasoning_run_index_repository: Annotated[
        ReasoningRunIndexRepository, Depends(get_reasoning_run_index_repository)
    ],
    situation_repository: Annotated[
        SituationRepository, Depends(get_situation_repository)
    ],
    structured_assessment_repository: Annotated[
        StructuredAssessmentRepository, Depends(get_structured_assessment_repository)
    ],
    reasoning_trace_repository: Annotated[
        ReasoningTraceRepository, Depends(get_reasoning_trace_repository)
    ],
    decision_context_repository: Annotated[
        DecisionContextRepository, Depends(get_decision_context_repository)
    ],
    decision_plan_repository: Annotated[
        DecisionPlanRepository, Depends(get_decision_plan_repository)
    ],
    timeline_repository: Annotated[
        TimelineRepository, Depends(get_timeline_repository)
    ],
) -> MonitoringService:
    """Provide a request-scoped monitoring service."""
    return MonitoringService(
        observation_repository=observation_repository,
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
        situation_repository=situation_repository,
        structured_assessment_repository=structured_assessment_repository,
        reasoning_trace_repository=reasoning_trace_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
        timeline_repository=timeline_repository,
    )


def get_health_service(request: Request) -> HealthService:
    """Return the application-scoped health service."""
    settings = getattr(request.app.state, "settings", None)
    runtime = getattr(request.app.state, "runtime", None)
    engine = getattr(request.app.state, "engine", None)
    session_factory = getattr(request.app.state, "session_factory", None)
    monitoring_event_source = getattr(
        request.app.state,
        "monitoring_event_source",
        None,
    )

    if settings is None:
        settings = get_settings()

    started_at = (
        runtime.started_at
        if runtime is not None and hasattr(runtime, "started_at")
        else datetime.now(UTC)
    )

    return HealthService(
        settings=settings,
        started_at=started_at,
        reasoning_engine_version=REASONING_ENGINE_VERSION,
        engine=engine,
        session_factory=session_factory,
        monitoring_event_source=monitoring_event_source,
    )
