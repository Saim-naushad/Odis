"""Shared application runtime bootstrap for API and worker processes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.application.digital_twin_cache import DigitalTwinCache
from backend.app.application.events.domain_events import (
    AiFaultInvestigationUpdated,
    HealthChanged,
    InvestigationTransitionRecorded,
    NotificationCreated,
    ObservationCreated,
    ReasoningCompleted,
    ReasoningStarted,
    RecommendationUpdated,
    RiskChanged,
    TrendChanged,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers import DigitalTwinCacheInvalidationHandler
from backend.app.application.events.handlers.monitoring_event_handler import (
    MonitoringEventHandler,
)
from backend.app.application.events.handlers.timeline_event_handler import (
    TimelineEventHandler,
)
from backend.app.application.forecast_inference_engine import ForecastInferenceEngine
from backend.app.application.integration_event_publisher import (
    IntegrationEventPublisher,
)
from backend.app.application.monitoring_event_source import (
    MonitoringEventSource,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.infrastructure.cache.redis_digital_twin_cache import (
    RedisDigitalTwinCache,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.events.kafka_integration_event_publisher import (
    KafkaIntegrationEventPublisher,
)
from backend.app.infrastructure.events.redis_monitoring_event_source import (
    RedisMonitoringEventSource,
)
from backend.app.infrastructure.inference.factory import (
    create_forecast_inference_engine,
)


@dataclass(frozen=True, slots=True)
class ApplicationRuntime:
    """Process-local services wired through a single composition root."""

    domain_event_bus: DomainEventBus
    monitoring_event_source: MonitoringEventSource
    digital_twin_cache: DigitalTwinCache
    outbox_dispatcher: OutboxDispatcher | None
    forecast_inference_engine: ForecastInferenceEngine | None


def create_integration_event_publisher(
    settings: Settings,
) -> IntegrationEventPublisher | None:
    """Return a Kafka publisher when bootstrap servers are configured."""
    if not settings.kafka_bootstrap_servers:
        return None
    return KafkaIntegrationEventPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
    )


def register_domain_event_handlers(
    event_bus: DomainEventBus,
    *,
    digital_twin_cache: DigitalTwinCache,
    monitoring_event_source: MonitoringEventSource,
    unit_of_work_factory: Callable[[], UnitOfWork[Session]] | None = None,
) -> None:
    """Register all domain event handlers on the bus."""
    cache_invalidation_handler = DigitalTwinCacheInvalidationHandler(
        digital_twin_cache,
    )
    event_bus.subscribe(
        HealthChanged,
        cache_invalidation_handler.on_health_changed,
    )
    event_bus.subscribe(
        RiskChanged,
        cache_invalidation_handler.on_risk_changed,
    )
    event_bus.subscribe(
        RecommendationUpdated,
        cache_invalidation_handler.on_recommendation_updated,
    )
    event_bus.subscribe(
        NotificationCreated,
        cache_invalidation_handler.on_notification_created,
    )
    event_bus.subscribe(
        ReasoningCompleted,
        cache_invalidation_handler.on_reasoning_completed,
    )
    event_bus.subscribe(
        InvestigationTransitionRecorded,
        cache_invalidation_handler.on_investigation_transition_recorded,
    )

    monitoring_handler = MonitoringEventHandler(monitoring_event_source)
    event_bus.subscribe(
        ObservationCreated,
        monitoring_handler.on_observation_created,
    )
    event_bus.subscribe(
        ReasoningCompleted,
        monitoring_handler.on_reasoning_completed,
    )
    event_bus.subscribe(
        AiFaultInvestigationUpdated,
        monitoring_handler.on_ai_fault_investigation_updated,
    )

    if unit_of_work_factory is not None:
        timeline_handler = TimelineEventHandler(unit_of_work_factory)
        event_bus.subscribe(
            ObservationCreated,
            timeline_handler.on_observation_created,
        )
        event_bus.subscribe(
            ReasoningStarted,
            timeline_handler.on_reasoning_started,
        )
        event_bus.subscribe(
            ReasoningCompleted,
            timeline_handler.on_reasoning_completed,
        )
        event_bus.subscribe(
            RecommendationUpdated,
            timeline_handler.on_recommendation_updated,
        )
        event_bus.subscribe(
            TrendChanged,
            timeline_handler.on_trend_changed,
        )
        event_bus.subscribe(
            HealthChanged,
            timeline_handler.on_health_changed,
        )
        event_bus.subscribe(
            RiskChanged,
            timeline_handler.on_risk_changed,
        )
        event_bus.subscribe(
            NotificationCreated,
            timeline_handler.on_notification_created,
        )
        event_bus.subscribe(
            InvestigationTransitionRecorded,
            timeline_handler.on_investigation_transition_recorded,
        )


def bootstrap_application_runtime(
    settings: Settings,
    unit_of_work_factory: Callable[[], UnitOfWork[Session]] | None = None,
) -> ApplicationRuntime:
    """Create and wire the shared application runtime for any process."""
    monitoring_event_source = RedisMonitoringEventSource(
        redis_url=settings.redis_url,
    )
    digital_twin_cache = RedisDigitalTwinCache(
        redis_url=settings.redis_url,
        ttl_seconds=settings.cache_ttl_seconds,
    )
    domain_event_bus = DomainEventBus()

    register_domain_event_handlers(
        domain_event_bus,
        digital_twin_cache=digital_twin_cache,
        monitoring_event_source=monitoring_event_source,
        unit_of_work_factory=unit_of_work_factory,
    )

    outbox_dispatcher: OutboxDispatcher | None = None
    if unit_of_work_factory is not None:
        outbox_dispatcher = OutboxDispatcher(
            unit_of_work_factory,
            domain_event_bus,
            create_integration_event_publisher(settings),
        )

    forecast_inference_engine = create_forecast_inference_engine(settings)

    return ApplicationRuntime(
        domain_event_bus=domain_event_bus,
        monitoring_event_source=monitoring_event_source,
        digital_twin_cache=digital_twin_cache,
        outbox_dispatcher=outbox_dispatcher,
        forecast_inference_engine=forecast_inference_engine,
    )
