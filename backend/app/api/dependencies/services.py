"""Application service dependency providers for route handlers."""

from typing import Annotated

from fastapi import Depends

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_session import ReasoningSession
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
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
from backend.app.application.observation_service import ObservationService
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_PROFILE
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
from domain.repositories.situation_repository import SituationRepository


def get_reasoning_session(
    reasoning_run_repository: Annotated[
        ReasoningRunRepository, Depends(get_reasoning_run_repository)
    ],
    situation_repository: Annotated[
        SituationRepository, Depends(get_situation_repository)
    ],
    decision_context_repository: Annotated[
        DecisionContextRepository, Depends(get_decision_context_repository)
    ],
    decision_plan_repository: Annotated[
        DecisionPlanRepository, Depends(get_decision_plan_repository)
    ],
    reasoning_run_index_repository: Annotated[
        ReasoningRunIndexRepository, Depends(get_reasoning_run_index_repository)
    ],
) -> ReasoningSession:
    """Provide a request-scoped reasoning session wired for platform persistence."""
    return ReasoningSession(
        profile=DEFAULT_OPERATIONAL_PROFILE,
        situation_repository=situation_repository,
        decision_context_repository=decision_context_repository,
        decision_plan_repository=decision_plan_repository,
        reasoning_run_repository=reasoning_run_repository,
        reasoning_run_index_repository=reasoning_run_index_repository,
    )


def get_observation_service(
    repository: Annotated[ObservationRepository, Depends(get_observation_repository)],
    reasoning_session: Annotated[ReasoningSession, Depends(get_reasoning_session)],
    structured_assessment_repository: Annotated[
        StructuredAssessmentRepository, Depends(get_structured_assessment_repository)
    ],
    reasoning_trace_repository: Annotated[
        ReasoningTraceRepository, Depends(get_reasoning_trace_repository)
    ],
) -> ObservationService:
    """Provide a request-scoped observation application service."""
    return ObservationService(
        repository,
        reasoning_session=reasoning_session,
        structured_assessment_repository=structured_assessment_repository,
        reasoning_trace_repository=reasoning_trace_repository,
    )
