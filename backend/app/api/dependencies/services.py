"""Application service dependency providers for route handlers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.api.dependencies.database import get_db_session
from backend.app.api.dependencies.monitoring_events import get_monitoring_event_source
from backend.app.api.dependencies.repositories import (
    get_decision_context_repository,
    get_decision_plan_repository,
    get_observation_repository,
    get_reasoning_run_index_repository,
    get_reasoning_run_repository,
    get_reasoning_trace_repository,
    get_situation_repository,
    get_structured_assessment_repository,
)
from backend.app.application.monitoring_event_source import MonitoringEventSource
from backend.app.application.monitoring_service import MonitoringService
from backend.app.application.observation_service import ObservationService
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.application.reasoning_task_runner import ReasoningTaskRunner
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
from domain.repositories.situation_repository import SituationRepository


def get_observation_service(
    session: Annotated[Session, Depends(get_db_session)],
    monitoring_event_source: Annotated[
        MonitoringEventSource, Depends(get_monitoring_event_source)
    ],
) -> ObservationService:
    """Provide a request-scoped observation application service."""
    return create_observation_service(session, monitoring_event_source)


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
    )
