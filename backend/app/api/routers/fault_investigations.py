"""Operator-facing read-model endpoints for AI-detected fault investigations.

Exposes `backend.app.domain.ai_fault_evidence.AiFaultEvidence` (persisted by
the reasoning bridge, PR177/178) to the dashboard. A known asset with no
active AI-fault investigation returns HTTP 200 with a null/empty result —
that is a normal operational state, never a 404. Only an unknown asset id
or an unknown investigation id is a 404. See
`docs/fault-investigation-dashboard.md`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.dependencies.services import (
    get_fault_investigation_service,
    get_monitoring_service,
)
from backend.app.api.schemas.fault_investigation import (
    ActiveFaultInvestigationResponse,
    FaultInvestigationDetailResponse,
    FaultInvestigationSummaryResponse,
)
from backend.app.application.fault_investigation_service import (
    DEFAULT_FAULT_INVESTIGATION_HISTORY_LIMIT,
    FaultInvestigationService,
)
from backend.app.application.monitoring_service import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["fault-investigations"])


@router.get(
    "/assets/{asset_id}/fault-investigation",
    response_model=ActiveFaultInvestigationResponse,
    summary="Get the active AI-detected fault investigation for an asset",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def get_active_fault_investigation_for_asset(
    asset_id: str,
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    fault_investigation_service: Annotated[
        FaultInvestigationService, Depends(get_fault_investigation_service)
    ],
) -> ActiveFaultInvestigationResponse:
    if not monitoring_service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )

    active = fault_investigation_service.get_active_for_asset(asset_id)
    if active is None:
        return ActiveFaultInvestigationResponse(active_investigation=None)

    supporting_observations = (
        fault_investigation_service.resolve_supporting_evidence(active)
    )
    return ActiveFaultInvestigationResponse(
        active_investigation=FaultInvestigationSummaryResponse.from_domain(
            active, supporting_observations=supporting_observations
        )
    )


@router.get(
    "/assets/{asset_id}/fault-investigations",
    response_model=list[FaultInvestigationSummaryResponse],
    summary="List an asset's AI-detected fault investigation history",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Asset not found"}},
)
def list_fault_investigations_for_asset(
    asset_id: str,
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    fault_investigation_service: Annotated[
        FaultInvestigationService, Depends(get_fault_investigation_service)
    ],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum number of investigations")
    ] = DEFAULT_FAULT_INVESTIGATION_HISTORY_LIMIT,
) -> list[FaultInvestigationSummaryResponse]:
    if not monitoring_service.asset_exists(asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset with id {asset_id!r} not found",
        )

    history = fault_investigation_service.list_history_for_asset(
        asset_id, limit=limit
    )
    return [
        FaultInvestigationSummaryResponse.from_domain(evidence)
        for evidence in history
    ]


@router.get(
    "/fault-investigations/{investigation_id}",
    response_model=FaultInvestigationDetailResponse,
    summary="Get the full lifecycle of one AI-detected fault investigation",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Investigation not found"}
    },
)
def get_fault_investigation_detail(
    investigation_id: str,
    fault_investigation_service: Annotated[
        FaultInvestigationService, Depends(get_fault_investigation_service)
    ],
) -> FaultInvestigationDetailResponse:
    lifecycle = fault_investigation_service.get_investigation(investigation_id)
    if not lifecycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"investigation with id {investigation_id!r} not found",
        )

    latest = lifecycle[-1]
    supporting_observations = (
        fault_investigation_service.resolve_supporting_evidence(latest)
    )
    return FaultInvestigationDetailResponse(
        investigation_id=investigation_id,
        asset_id=latest.asset_id,
        current=FaultInvestigationSummaryResponse.from_domain(
            latest, supporting_observations=supporting_observations
        ),
        timeline=[
            FaultInvestigationSummaryResponse.from_domain(evidence)
            for evidence in lifecycle
        ],
    )
