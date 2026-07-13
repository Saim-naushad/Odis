"""Monitoring endpoints for reasoning history and debugging."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies.monitoring_events import MonitoringEventSourceDep
from backend.app.api.dependencies.services import (
    get_continuous_aggregate_service,
    get_digital_twin_service,
    get_forecast_inference_service,
    get_investigation_service,
    get_monitoring_service,
    get_telemetry_history_service,
)
from backend.app.api.schemas.monitoring import (
    AlternativeHypothesisResponse,
    AssessmentSummaryResponse,
    ConfidenceBreakdownResponse,
    ConfidenceScoreResponse,
    DecisionContextResponse,
    DecisionPlanResponse,
    DecisionPlanSummaryResponse,
    DigitalTwinResponse,
    EvidenceResponse,
    ExplanationResponse,
    HypothesisResponse,
    InvestigationTransitionRequest,
    InvestigationTransitionResponse,
    LocationResponse,
    MonitoringAssetHistoryItemResponse,
    MonitoringAssetLatestResponse,
    MonitoringAssetResponse,
    MonitoringRunDetailsResponse,
    NotificationResponse,
    OperationalSituationResponse,
    OperationalStateResponse,
    ReasoningTraceResponse,
    RecommendationResponse,
    StructuredAssessmentResponse,
    TimelineEventResponse,
    TrendAnalysisResponse,
)
from backend.app.api.schemas.observation import ObservationResponse
from backend.app.api.schemas.telemetry import (
    TelemetryAggregateSeriesResponse,
    TelemetryForecastResponse,
    TelemetrySeriesResponse,
)
from backend.app.application.continuous_aggregate_service import (
    ContinuousAggregateService,
)
from backend.app.application.digital_twin_service import (
    DigitalTwinAssetNotFoundError,
    DigitalTwinNoReasoningHistoryError,
    DigitalTwinService,
)
from backend.app.application.forecast_inference_service import ForecastInferenceService
from backend.app.application.investigation_service import (
    InvestigationService,
    InvestigationTransitionRejectedError,
)
from backend.app.application.monitoring_service import MonitoringService
from backend.app.application.monitoring_sse_stream import stream_monitoring_sse_events
from backend.app.application.telemetry_history_service import (
    MAX_TELEMETRY_LIMIT,
    TelemetryHistoryService,
)
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.monitoring_metrics import (
    monitoring_sse_connections,
)
from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_bucket import TelemetryBucket

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
logger = get_logger(__name__)


@router.get(
    "/events",
    summary="Stream monitoring updates (SSE)",
    response_description="Continuous Server-Sent Events stream for monitoring updates.",
)
async def stream_monitoring_events(
    request: Request,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    event_source: MonitoringEventSourceDep,
) -> StreamingResponse:
    # NOTE: service is injected now to keep the API surface stable; future PRs can
    # stream real monitoring events from persisted runs without changing the route.
    _ = service

    monitoring_sse_connections.inc()

    async def event_generator() -> AsyncIterator[str]:
        logger.info("monitoring_sse_started")
        try:
            async for message in stream_monitoring_sse_events(
                is_disconnected=request.is_disconnected,
                event_source=event_source,
            ):
                yield message
        finally:
            monitoring_sse_connections.dec()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/assets",
    response_model=list[MonitoringAssetResponse],
    summary="List known assets",
    response_description="All known asset identifiers in stable order.",
)
def list_assets(
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> list[MonitoringAssetResponse]:
    asset_ids = service.list_assets()
    return [MonitoringAssetResponse(id=asset_id) for asset_id in asset_ids]


@router.get(
    "/assets/{asset_id}/latest",
    response_model=MonitoringAssetLatestResponse,
    summary="Get latest reasoning result for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_latest_for_asset(
    asset_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> MonitoringAssetLatestResponse:
    latest = service.get_latest_for_asset(asset_id)
    if latest is None:
        if not service.asset_exists(asset_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"asset with id {asset_id!r} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} has no reasoning history",
        )
    return MonitoringAssetLatestResponse(
        asset_id=latest.asset_id,
        run_id=latest.run.id,
        timestamp=latest.run.started_at,
        operational_situation=OperationalSituationResponse.from_domain(
            latest.operational_situation
        ),
        structured_assessment=(
            StructuredAssessmentResponse.from_domain(latest.structured_assessment)
            if latest.structured_assessment is not None
            else None
        ),
        decision_plan=DecisionPlanSummaryResponse.from_domain(latest.decision_plan),
    )


@router.get(
    "/assets/{asset_id}/history",
    response_model=list[MonitoringAssetHistoryItemResponse],
    summary="Get reasoning history for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_history_for_asset(
    asset_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> list[MonitoringAssetHistoryItemResponse]:
    history = service.get_history_for_asset(asset_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )
    return [
        MonitoringAssetHistoryItemResponse(
            asset_id=item.asset_id,
            run_id=item.run.id,
            timestamp=item.run.started_at,
            operational_situation=OperationalSituationResponse.from_domain(
                item.operational_situation
            ),
            structured_assessment=(
                StructuredAssessmentResponse.from_domain(item.structured_assessment)
                if item.structured_assessment is not None
                else None
            ),
            decision_plan=DecisionPlanSummaryResponse.from_domain(item.decision_plan),
        )
        for item in history
    ]


@router.get(
    "/assets/{asset_id}/timeline",
    response_model=list[TimelineEventResponse],
    summary="Get investigation timeline for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_timeline_for_asset(
    asset_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> list[TimelineEventResponse]:
    timeline = service.get_timeline_for_asset(asset_id)
    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )
    return [TimelineEventResponse.from_domain(event) for event in timeline]


@router.get(
    "/assets/{asset_id}/telemetry",
    response_model=list[TelemetrySeriesResponse],
    summary="Get historical telemetry for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_telemetry_history_for_asset(
    asset_id: str,
    service: Annotated[TelemetryHistoryService, Depends(get_telemetry_history_service)],
    start: Annotated[
        datetime | None,
        Query(description="Inclusive start of the query window (ISO 8601)"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="Inclusive end of the query window (ISO 8601)"),
    ] = None,
    measurement_type: Annotated[
        str | None,
        Query(min_length=1, description="Optional measurement type filter"),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_TELEMETRY_LIMIT,
            description="Maximum number of raw observations to retrieve",
        ),
    ] = 1000,
) -> list[TelemetrySeriesResponse]:
    if not service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must not be after end",
        )

    series = service.get_history(
        asset_id,
        start=start,
        end=end,
        measurement_type=measurement_type,
        limit=limit,
    )
    return [TelemetrySeriesResponse.from_domain(item) for item in series]


@router.get(
    "/assets/{asset_id}/telemetry/aggregate",
    response_model=list[TelemetryAggregateSeriesResponse],
    summary="Get downsampled telemetry aggregates for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_telemetry_aggregates_for_asset(
    asset_id: str,
    service: Annotated[
        ContinuousAggregateService, Depends(get_continuous_aggregate_service)
    ],
    bucket: Annotated[
        str,
        Query(description="Aggregate bucket width", pattern="^(1h|1d)$"),
    ],
    start: Annotated[
        datetime | None,
        Query(description="Inclusive start of the query window (ISO 8601)"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="Inclusive end of the query window (ISO 8601)"),
    ] = None,
    measurement_type: Annotated[
        str | None,
        Query(min_length=1, description="Optional measurement type filter"),
    ] = None,
) -> list[TelemetryAggregateSeriesResponse]:
    if not service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must not be after end",
        )

    try:
        bucket_granularity = TelemetryBucket.from_query(bucket)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    resolved_bucket = ContinuousAggregateService.resolve_bucket(
        bucket_granularity,
        start=start,
        end=end,
    )
    points = service.list_aggregate_points(
        asset_id,
        bucket=resolved_bucket,
        start=start,
        end=end,
        measurement_type=measurement_type,
    )

    grouped: dict[str, list[TelemetryAggregatePoint]] = {}
    units: dict[str, str] = {}
    for point in points:
        grouped.setdefault(point.measurement_type, []).append(point)
        units[point.measurement_type] = point.unit

    responses: list[TelemetryAggregateSeriesResponse] = []
    for metric in sorted(grouped):
        metric_points = grouped[metric]
        metric_points.sort(key=lambda item: item.bucket)
        responses.append(
            TelemetryAggregateSeriesResponse.from_points(
                asset_id=asset_id,
                bucket=resolved_bucket,
                measurement_type=metric,
                unit=units[metric],
                points=metric_points,
            )
        )
    return responses


@router.get(
    "/assets/{asset_id}/telemetry/latest",
    response_model=list[TelemetrySeriesResponse],
    summary="Get latest telemetry samples for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_latest_telemetry_for_asset(
    asset_id: str,
    service: Annotated[TelemetryHistoryService, Depends(get_telemetry_history_service)],
    measurement_type: Annotated[
        str | None,
        Query(min_length=1, description="Optional measurement type filter"),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_TELEMETRY_LIMIT,
            description="Maximum samples per measurement type",
        ),
    ] = 1,
) -> list[TelemetrySeriesResponse]:
    if not service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )

    series = service.get_latest(
        asset_id,
        measurement_type=measurement_type,
        limit=limit,
    )
    return [TelemetrySeriesResponse.from_domain(item) for item in series]


@router.get(
    "/assets/{asset_id}/telemetry/forecast",
    response_model=list[TelemetryForecastResponse],
    summary="Get ONNX-backed telemetry forecasts for an asset",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Asset not found"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Forecasting is disabled",
        },
    },
)
def get_telemetry_forecasts_for_asset(
    asset_id: str,
    service: Annotated[
        ForecastInferenceService | None,
        Depends(get_forecast_inference_service),
    ],
    bucket: Annotated[
        str,
        Query(
            description="Aggregate bucket width used for model context",
            pattern="^(1h|1d)$",
        ),
    ] = "1h",
    start: Annotated[
        datetime | None,
        Query(description="Inclusive start of the context window (ISO 8601)"),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="Inclusive end of the context window (ISO 8601)"),
    ] = None,
    measurement_type: Annotated[
        str | None,
        Query(min_length=1, description="Optional measurement type filter"),
    ] = None,
    horizon_steps: Annotated[
        int | None,
        Query(ge=1, le=48, description="Optional forecast horizon override"),
    ] = None,
) -> list[TelemetryForecastResponse]:
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="forecasting is disabled",
        )
    if not service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must not be after end",
        )

    try:
        bucket_granularity = TelemetryBucket.from_query(bucket)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    if measurement_type is not None:
        try:
            forecasts = [
                service.get_forecast(
                    asset_id,
                    measurement_type=measurement_type,
                    bucket=bucket_granularity,
                    start=start,
                    end=end,
                    horizon_steps=horizon_steps,
                )
            ]
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
    else:
        forecasts = service.get_forecasts_for_asset(
            asset_id,
            bucket=bucket_granularity,
            start=start,
            end=end,
            horizon_steps=horizon_steps,
        )

    return [TelemetryForecastResponse.from_domain(item) for item in forecasts]


@router.get(
    "/assets/{asset_id}/state",
    response_model=OperationalStateResponse,
    summary="Get current operational state for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_operational_state_for_asset(
    asset_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> OperationalStateResponse:
    state = service.get_operational_state(asset_id)
    if state is None:
        if not service.asset_exists(asset_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"asset with id {asset_id!r} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} has no reasoning history",
        )
    return OperationalStateResponse.from_domain(state)


@router.get(
    "/assets/{asset_id}/recommendation",
    response_model=RecommendationResponse,
    summary="Get current recommendation for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_recommendation_for_asset(
    asset_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> RecommendationResponse:
    recommendation = service.get_recommendation(asset_id)
    if recommendation is None:
        if not service.asset_exists(asset_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"asset with id {asset_id!r} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} has no reasoning history",
        )
    return RecommendationResponse.from_domain(recommendation)


@router.get(
    "/assets/{asset_id}/notification",
    response_model=NotificationResponse,
    summary="Get latest notification for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Notification not found"}},
)
def get_latest_notification_for_asset(
    asset_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> NotificationResponse:
    notification = service.get_latest_notification(asset_id)
    if notification is None:
        if not service.asset_exists(asset_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"asset with id {asset_id!r} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} has no notification",
        )
    return NotificationResponse.from_domain(notification)


@router.post(
    "/assets/{asset_id}/investigation",
    response_model=InvestigationTransitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an operator investigation transition",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Asset or recommendation not found"
        },
        status.HTTP_409_CONFLICT: {
            "description": "Illegal investigation transition"
        },
    },
)
def record_investigation_transition(
    asset_id: str,
    payload: InvestigationTransitionRequest,
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    investigation_service: Annotated[
        InvestigationService, Depends(get_investigation_service)
    ],
) -> InvestigationTransitionResponse:
    if not monitoring_service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )

    recommendation = monitoring_service.get_recommendation(asset_id)
    if recommendation is None or recommendation.id != payload.recommendation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"recommendation {payload.recommendation_id!r} is not the "
                f"current recommendation for asset {asset_id!r}"
            ),
        )

    try:
        transition = investigation_service.record_transition(
            asset_id=asset_id,
            recommendation_id=payload.recommendation_id,
            status=payload.status,
            actor_id=payload.actor_id,
            actor_display_name=payload.actor_display_name,
            notes=payload.notes,
        )
    except InvestigationTransitionRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return InvestigationTransitionResponse.from_domain(transition)


@router.get(
    "/assets/{asset_id}/digital-twin",
    response_model=DigitalTwinResponse,
    summary="Get unified Digital Twin for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_digital_twin_for_asset(
    asset_id: str,
    service: Annotated[DigitalTwinService, Depends(get_digital_twin_service)],
) -> DigitalTwinResponse:
    try:
        twin = service.get_for_asset(asset_id)
    except DigitalTwinAssetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        ) from None
    except DigitalTwinNoReasoningHistoryError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} has no reasoning history",
        ) from None
    return DigitalTwinResponse(
        asset_id=twin.asset_id,
        asset_name=twin.asset_name,
        asset_type=twin.asset_type,
        location=LocationResponse.from_domain(twin.location),
        operational_state=OperationalStateResponse.from_domain(twin.operational_state),
        recommendation=RecommendationResponse.from_domain(twin.recommendation),
        notification=(
            NotificationResponse.from_domain(twin.notification)
            if twin.notification is not None
            else None
        ),
        investigation=(
            InvestigationTransitionResponse.from_domain(twin.investigation)
            if twin.investigation is not None
            else None
        ),
        latest_reasoning_run_id=twin.latest_reasoning_run_id,
        timeline_preview=[
            TimelineEventResponse.from_domain(event) for event in twin.timeline_preview
        ],
        telemetry_forecasts=[
            TelemetryForecastResponse.from_domain(forecast)
            for forecast in twin.telemetry_forecasts
        ],
        last_updated=twin.last_updated,
    )


@router.get(
    "/runs/{run_id}",
    response_model=MonitoringRunDetailsResponse,
    summary="Get complete reasoning run details",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Run not found"}},
)
def get_run_details(
    run_id: str,
    service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> MonitoringRunDetailsResponse:
    details = service.get_run_details(run_id)
    if details is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"reasoning run with id {run_id!r} not found",
        )

    from backend.app.application.explainable_reasoning import build_explainable_decision
    from backend.app.application.reasoning_compatibility import (
        build_reasoning_context_through_explanation,
    )
    from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_GOAL

    explainable = build_explainable_decision(
        assessment=details.decision_context.assessment,
        observations=details.observations,
        decision_plan=details.decision_plan,
        structured_assessment=details.structured_assessment,
    )

    reasoning_context = build_reasoning_context_through_explanation(
        goal=DEFAULT_OPERATIONAL_GOAL,
        observations=details.observations,
    )
    artifacts = reasoning_context.artifacts

    plan_response = DecisionPlanResponse.from_domain(details.decision_plan)
    plan_response = plan_response.model_copy(
        update={
            "confidence": ConfidenceScoreResponse.from_domain(explainable.confidence),
            "evidence": tuple(
                EvidenceResponse.from_domain(item) for item in explainable.evidence
            ),
            "alternative_hypotheses": tuple(
                AlternativeHypothesisResponse.from_domain(item)
                for item in explainable.alternative_hypotheses
            ),
            "expected_outcome": explainable.expected_outcome,
        }
    )

    return MonitoringRunDetailsResponse(
        run_id=details.run.id,
        started_at=details.run.started_at,
        observations=[
            ObservationResponse.from_domain(observation)
            for observation in details.observations
        ],
        reasoning_trace=(
            ReasoningTraceResponse.from_domain(details.reasoning_trace)
            if details.reasoning_trace is not None
            else None
        ),
        structured_assessment=(
            StructuredAssessmentResponse.from_domain(details.structured_assessment)
            if details.structured_assessment is not None
            else None
        ),
        operational_situation=OperationalSituationResponse.from_domain(
            details.operational_situation
        ),
        decision_context=DecisionContextResponse.from_domain(details.decision_context),
        decision_plan=plan_response,
        trend_analysis=TrendAnalysisResponse.from_domain(explainable.trend_analysis),
        confidence_breakdown=(
            ConfidenceBreakdownResponse.from_domain(artifacts.confidence)
            if artifacts.confidence is not None
            else None
        ),
        explanation=(
            ExplanationResponse.from_domain(artifacts.explanation)
            if artifacts.explanation is not None
            else None
        ),
        hypotheses=(
            tuple(
                HypothesisResponse.from_domain(item)
                for item in artifacts.hypotheses
            )
            if artifacts.hypotheses
            else None
        ),
        assessment_summary=(
            AssessmentSummaryResponse.from_domain(artifacts.assessment_summary)
            if artifacts.assessment_summary is not None
            else None
        ),
    )

