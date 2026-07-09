"""Monitoring endpoints for reasoning history and debugging."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies.monitoring_events import MonitoringEventSourceDep
from backend.app.api.dependencies.services import get_monitoring_service
from backend.app.api.schemas.monitoring import (
    DecisionContextResponse,
    DecisionPlanResponse,
    DecisionPlanSummaryResponse,
    MonitoringAssetHistoryItemResponse,
    MonitoringAssetLatestResponse,
    MonitoringAssetResponse,
    MonitoringRunDetailsResponse,
    OperationalSituationResponse,
    ReasoningTraceResponse,
    StructuredAssessmentResponse,
)
from backend.app.api.schemas.observation import ObservationResponse
from backend.app.application.monitoring_service import MonitoringService
from backend.app.application.monitoring_sse_stream import stream_monitoring_sse_events

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


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

    async def event_generator() -> AsyncIterator[str]:
        async for message in stream_monitoring_sse_events(
            is_disconnected=request.is_disconnected,
            event_source=event_source,
        ):
            yield message

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
    history = service.get_history_for_asset(asset_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} has no reasoning history",
        )
    latest = service.get_latest_for_asset(asset_id)
    assert latest is not None
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
        decision_plan=DecisionPlanResponse.from_domain(details.decision_plan),
    )

