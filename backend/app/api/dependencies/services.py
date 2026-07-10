"""Application service dependency providers for route handlers."""

from datetime import UTC, datetime
from typing import Annotated, cast

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
    get_telemetry_aggregate_repository,
    get_timeline_repository,
)
from backend.app.api.routers.platform import REASONING_ENGINE_VERSION
from backend.app.application.continuous_aggregate_service import (
    ContinuousAggregateService,
)
from backend.app.application.digital_twin_cache import DigitalTwinCache
from backend.app.application.digital_twin_service import DigitalTwinService
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.feature_builder import FeatureBuilder
from backend.app.application.forecast_inference_engine import ForecastInferenceEngine
from backend.app.application.forecast_inference_service import ForecastInferenceService
from backend.app.application.health_service import HealthService
from backend.app.application.monitoring_service import MonitoringService
from backend.app.application.observation_service import ObservationService
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.telemetry_history_service import TelemetryHistoryService
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.repositories.timeline_repository import TimelineRepository
from backend.app.infrastructure.config.settings import get_settings
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
from domain.repositories.situation_repository import SituationRepository
from domain.repositories.telemetry_aggregate_repository import (
    TelemetryAggregateRepository,
)


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


def get_telemetry_history_service(
    observation_repository: Annotated[
        ObservationRepository, Depends(get_observation_repository)
    ],
) -> TelemetryHistoryService:
    """Provide a request-scoped telemetry history service."""
    return TelemetryHistoryService(observation_repository=observation_repository)


def get_continuous_aggregate_service(
    observation_repository: Annotated[
        ObservationRepository, Depends(get_observation_repository)
    ],
    telemetry_aggregate_repository: Annotated[
        TelemetryAggregateRepository, Depends(get_telemetry_aggregate_repository)
    ],
) -> ContinuousAggregateService:
    """Provide a request-scoped continuous aggregate service."""
    return ContinuousAggregateService(
        observation_repository=observation_repository,
        telemetry_aggregate_repository=telemetry_aggregate_repository,
    )


def get_forecast_inference_engine(request: Request) -> ForecastInferenceEngine | None:
    engine = getattr(request.app.state, "forecast_inference_engine", None)
    if engine is None:
        return None
    return cast(ForecastInferenceEngine, engine)


def get_forecast_inference_service(
    observation_repository: Annotated[
        ObservationRepository, Depends(get_observation_repository)
    ],
    telemetry_aggregate_repository: Annotated[
        TelemetryAggregateRepository, Depends(get_telemetry_aggregate_repository)
    ],
    inference_engine: Annotated[
        ForecastInferenceEngine | None,
        Depends(get_forecast_inference_engine),
    ],
) -> ForecastInferenceService | None:
    """Provide a request-scoped forecast inference service when enabled."""
    if inference_engine is None:
        return None

    settings = get_settings()
    feature_builder = FeatureBuilder(context_length=settings.forecast_context_length)
    return ForecastInferenceService(
        observation_repository=observation_repository,
        telemetry_aggregate_repository=telemetry_aggregate_repository,
        feature_builder=feature_builder,
        inference_engine=inference_engine,
    )


def get_digital_twin_cache(request: Request) -> DigitalTwinCache:
    cache = getattr(request.app.state, "digital_twin_cache", None)
    if cache is None:
        msg = "Digital twin cache is not configured on the application"
        raise RuntimeError(msg)
    return cast(DigitalTwinCache, cache)


def get_digital_twin_service(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    cache: Annotated[DigitalTwinCache, Depends(get_digital_twin_cache)],
    forecast_inference_service: Annotated[
        ForecastInferenceService | None,
        Depends(get_forecast_inference_service),
    ],
) -> DigitalTwinService:
    """Provide a request-scoped digital twin assembly service."""
    return DigitalTwinService(
        monitoring_service=monitoring_service,
        cache=cache,
        forecast_inference_service=forecast_inference_service,
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
