"""Repository dependency providers for route handlers."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.api.dependencies.database import get_db_session
from backend.app.domain.repositories.ai_fault_evidence_repository import (
    AiFaultEvidenceRepository,
)
from backend.app.domain.repositories.investigation_repository import (
    InvestigationRepository,
)
from backend.app.domain.repositories.timeline_repository import TimelineRepository
from backend.app.infrastructure.repositories.ai_fault_evidence_repository import (
    SqlAlchemyAiFaultEvidenceRepository,
)
from backend.app.infrastructure.repositories.decision_context_repository import (
    SqlAlchemyDecisionContextRepository,
)
from backend.app.infrastructure.repositories.decision_plan_repository import (
    SqlAlchemyDecisionPlanRepository,
)
from backend.app.infrastructure.repositories.investigation_repository import (
    SqlAlchemyInvestigationRepository,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
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
from backend.app.infrastructure.repositories.telemetry_aggregate_repository import (
    SqlAlchemyTelemetryAggregateRepository,
)
from backend.app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyTimelineRepository,
)
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
from domain.repositories.situation_repository import SituationRepository
from domain.repositories.telemetry_aggregate_repository import (
    TelemetryAggregateRepository,
)


def get_observation_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> ObservationRepository:
    """Provide a request-scoped observation repository."""
    return SqlAlchemyObservationRepository(session)


def get_telemetry_aggregate_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> TelemetryAggregateRepository:
    """Provide a request-scoped telemetry aggregate repository."""
    return SqlAlchemyTelemetryAggregateRepository(session)


def get_reasoning_run_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> ReasoningRunRepository:
    """Provide a request-scoped reasoning run repository."""
    return SqlAlchemyReasoningRunRepository(session)


def get_situation_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> SituationRepository:
    """Provide a request-scoped operational situation repository."""
    return SqlAlchemySituationRepository(session)


def get_decision_context_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> DecisionContextRepository:
    """Provide a request-scoped decision context repository."""
    return SqlAlchemyDecisionContextRepository(session)


def get_decision_plan_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> DecisionPlanRepository:
    """Provide a request-scoped decision plan repository."""
    return SqlAlchemyDecisionPlanRepository(session)


def get_reasoning_run_index_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> ReasoningRunIndexRepository:
    """Provide a request-scoped reasoning run index repository."""
    return SqlAlchemyReasoningRunIndexRepository(session)


def get_structured_assessment_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> StructuredAssessmentRepository:
    """Provide a request-scoped structured assessment repository."""
    return SqlAlchemyStructuredAssessmentRepository(session)


def get_reasoning_trace_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> ReasoningTraceRepository:
    """Provide a request-scoped reasoning trace repository."""
    return SqlAlchemyReasoningTraceRepository(session)


def get_timeline_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> TimelineRepository:
    """Provide a request-scoped timeline repository."""
    return SqlAlchemyTimelineRepository(session)


def get_investigation_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> InvestigationRepository:
    """Provide a request-scoped investigation transition repository."""
    return SqlAlchemyInvestigationRepository(session)


def get_ai_fault_evidence_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AiFaultEvidenceRepository:
    """Provide a request-scoped AI fault evidence repository."""
    return SqlAlchemyAiFaultEvidenceRepository(session)
