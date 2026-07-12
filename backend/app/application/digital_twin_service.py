"""Application service for assembling Digital Twins on demand."""

from __future__ import annotations

import time

from backend.app.application.digital_twin_cache import DigitalTwinCache
from backend.app.application.forecast_inference_service import ForecastInferenceService
from backend.app.application.monitoring_service import MonitoringService
from backend.app.application.plant_alpha_catalog import (
    DEFAULT_PLANT_ALPHA_CATALOG,
    PlantAlphaCatalog,
)
from backend.app.domain.digital_twin import DigitalTwin
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.metrics.reasoning_metrics import (
    record_digital_twin_build_duration,
)
from backend.app.infrastructure.tracing import business_span
from domain.entities.asset import Asset
from domain.value_objects.location import Location
from domain.value_objects.telemetry_bucket import TelemetryBucket
from domain.value_objects.telemetry_forecast import TelemetryForecast


class DigitalTwinAssetNotFoundError(Exception):
    pass


class DigitalTwinNoReasoningHistoryError(Exception):
    pass


def _derive_unknown_asset(asset_id: str) -> Asset:
    # Fallback for ids outside the known Plant Alpha catalog: a stable,
    # deterministic placeholder derived from the identifier only.
    derived_name = asset_id.replace("-", " ").strip() or asset_id
    return Asset(
        id=asset_id,
        name=derived_name,
        type="unknown",
        location=Location(identifier="unknown"),
    )


class DigitalTwinService:
    """Single place responsible for assembling a Digital Twin.

    It composes results from existing services/models. It must not recompute
    Operational State, Recommendation, or Notification.
    """

    def __init__(
        self,
        *,
        monitoring_service: MonitoringService,
        cache: DigitalTwinCache,
        forecast_inference_service: ForecastInferenceService | None = None,
        asset_catalog: PlantAlphaCatalog = DEFAULT_PLANT_ALPHA_CATALOG,
        timeline_preview_limit: int = 5,
    ) -> None:
        self._monitoring = monitoring_service
        self._cache = cache
        self._forecast_inference_service = forecast_inference_service
        self._asset_catalog = asset_catalog
        self._timeline_preview_limit = timeline_preview_limit

    def get_for_asset(self, asset_id: str) -> DigitalTwin:
        cached = self._cache.get(asset_id)
        if cached is not None:
            return cached

        twin = self._assemble(asset_id)
        self._cache.set(twin)
        return twin

    def _assemble(self, asset_id: str) -> DigitalTwin:
        with business_span("build_digital_twin", attributes={"asset_id": asset_id}):
            build_start = time.perf_counter()
            if not self._monitoring.asset_exists(asset_id):
                raise DigitalTwinAssetNotFoundError(asset_id)

            latest = self._monitoring.get_latest_for_asset(asset_id)
            if latest is None:
                raise DigitalTwinNoReasoningHistoryError(asset_id)

            operational_state = self._monitoring.get_operational_state(asset_id)
            recommendation = self._monitoring.get_recommendation(asset_id)
            # If the asset has a latest run, state and recommendation should exist;
            # still guard to keep service defensive.
            if operational_state is None or recommendation is None:
                raise DigitalTwinNoReasoningHistoryError(asset_id)

            notification = self._monitoring.get_latest_notification(asset_id)
            timeline = self._monitoring.get_timeline_for_asset(asset_id) or []
            timeline_preview = self._preview_timeline(timeline)

            asset = self._asset_catalog.get(asset_id) or _derive_unknown_asset(
                asset_id
            )
            telemetry_forecasts = self._load_telemetry_forecasts(asset_id)

            twin = DigitalTwin(
                asset_id=asset.id,
                asset_name=asset.name,
                asset_type=asset.type,
                location=asset.location,
                operational_state=operational_state,
                recommendation=recommendation,
                notification=notification,
                latest_reasoning_run_id=latest.run.id,
                timeline_preview=tuple(timeline_preview),
                telemetry_forecasts=tuple(telemetry_forecasts),
                last_updated=operational_state.last_updated,
            )
            record_digital_twin_build_duration(time.perf_counter() - build_start)
            return twin

    def _preview_timeline(self, timeline: list[TimelineEvent]) -> list[TimelineEvent]:
        if self._timeline_preview_limit <= 0:
            return []
        # Timeline is oldest → newest; preview should return the most recent N
        # while preserving chronological order.
        return timeline[-self._timeline_preview_limit :]

    def _load_telemetry_forecasts(self, asset_id: str) -> list[TelemetryForecast]:
        if self._forecast_inference_service is None:
            return []
        if not self._forecast_inference_service.asset_exists(asset_id):
            return []
        try:
            return self._forecast_inference_service.get_forecasts_for_asset(
                asset_id,
                bucket=TelemetryBucket.ONE_HOUR,
            )
        except ValueError:
            return []

