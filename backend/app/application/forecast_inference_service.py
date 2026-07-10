"""Application service for telemetry forecasting."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from backend.app.application.continuous_aggregate_service import (
    ContinuousAggregateService,
)
from backend.app.application.feature_builder import FeatureBuilder
from backend.app.application.forecast_inference_engine import ForecastInferenceEngine
from backend.app.infrastructure.metrics.forecast_metrics import (
    record_forecast_inference_duration,
    record_forecast_inference_failure,
    record_forecast_inference_success,
)
from backend.app.infrastructure.tracing import business_span
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.telemetry_aggregate_repository import (
    TelemetryAggregateRepository,
)
from domain.value_objects.telemetry_bucket import TelemetryBucket
from domain.value_objects.telemetry_forecast import ForecastSample, TelemetryForecast


class ForecastInferenceService:
    """Single application component responsible for telemetry forecasting.

    Loads historical context from continuous aggregates, converts it into model
    features, delegates inference to an infrastructure adapter, and returns
    immutable ``TelemetryForecast`` read models.
    """

    def __init__(
        self,
        *,
        observation_repository: ObservationRepository,
        telemetry_aggregate_repository: TelemetryAggregateRepository,
        feature_builder: FeatureBuilder,
        inference_engine: ForecastInferenceEngine,
    ) -> None:
        self._observation_repository = observation_repository
        self._telemetry_aggregate_repository = telemetry_aggregate_repository
        self._feature_builder = feature_builder
        self._inference_engine = inference_engine
        self._aggregate_service = ContinuousAggregateService(
            observation_repository=observation_repository,
            telemetry_aggregate_repository=telemetry_aggregate_repository,
        )

    @property
    def model_id(self) -> str:
        return self._inference_engine.model_spec.model_id

    def asset_exists(self, asset_id: str) -> bool:
        """Return whether any observations exist for the asset."""
        return bool(self._observation_repository.list_by_asset(asset_id))

    def get_forecast(
        self,
        asset_id: str,
        *,
        measurement_type: str,
        bucket: TelemetryBucket,
        start: datetime | None = None,
        end: datetime | None = None,
        horizon_steps: int | None = None,
    ) -> TelemetryForecast:
        """Forecast one measurement type from aggregate telemetry."""
        with business_span(
            "forecast_inference",
            attributes={
                "asset_id": asset_id,
                "measurement_type": measurement_type,
                "bucket": bucket.value,
            },
        ):
            inference_start = time.perf_counter()
            try:
                forecast = self._build_forecast(
                    asset_id,
                    measurement_type=measurement_type,
                    bucket=bucket,
                    start=start,
                    end=end,
                    horizon_steps=horizon_steps,
                )
            except Exception:
                record_forecast_inference_failure()
                raise
            else:
                record_forecast_inference_success()
                record_forecast_inference_duration(
                    time.perf_counter() - inference_start,
                )
                return forecast

    def get_forecasts_for_asset(
        self,
        asset_id: str,
        *,
        bucket: TelemetryBucket = TelemetryBucket.ONE_HOUR,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
        horizon_steps: int | None = None,
    ) -> list[TelemetryForecast]:
        """Forecast all measurement types with aggregate history for an asset."""
        points = self._telemetry_aggregate_repository.list_by_asset(
            asset_id,
            bucket=bucket,
            start=start,
            end=end,
            measurement_type=measurement_type,
        )
        grouped: dict[str, list] = defaultdict(list)
        for point in points:
            grouped[point.measurement_type].append(point)

        forecasts: list[TelemetryForecast] = []
        for metric in sorted(grouped):
            forecasts.append(
                self.get_forecast(
                    asset_id,
                    measurement_type=metric,
                    bucket=bucket,
                    start=start,
                    end=end,
                    horizon_steps=horizon_steps,
                )
            )
        return forecasts

    def _build_forecast(
        self,
        asset_id: str,
        *,
        measurement_type: str,
        bucket: TelemetryBucket,
        start: datetime | None,
        end: datetime | None,
        horizon_steps: int | None,
    ) -> TelemetryForecast:
        points = self._telemetry_aggregate_repository.list_by_asset(
            asset_id,
            bucket=bucket,
            start=start,
            end=end,
            measurement_type=measurement_type,
        )
        if not points:
            msg = (
                f"no aggregate telemetry available for {measurement_type!r} "
                f"on asset {asset_id!r}"
            )
            raise ValueError(msg)

        ordered_points = sorted(points, key=lambda point: point.bucket)
        features = self._feature_builder.build_from_aggregate_points(ordered_points)
        model_spec = self._inference_engine.model_spec
        resolved_horizon = horizon_steps or model_spec.horizon_steps

        normalized_predictions = self._inference_engine.predict(features.values)
        if len(normalized_predictions) < resolved_horizon:
            msg = (
                f"model returned {len(normalized_predictions)} predictions; "
                f"expected at least {resolved_horizon}"
            )
            raise ValueError(msg)

        predictions = features.denormalize(normalized_predictions[:resolved_horizon])
        horizon_start = ordered_points[-1].bucket
        step = self._bucket_step(bucket)
        generated_at = datetime.now(UTC)
        samples = tuple(
            ForecastSample(
                timestamp=horizon_start + (step * (index + 1)),
                value=predictions[index],
            )
            for index in range(resolved_horizon)
        )

        return TelemetryForecast(
            asset_id=asset_id,
            measurement_type=measurement_type,
            unit=ordered_points[-1].unit,
            model_id=model_spec.model_id,
            horizon_start=horizon_start,
            generated_at=generated_at,
            samples=samples,
        )

    @staticmethod
    def _bucket_step(bucket: TelemetryBucket) -> timedelta:
        if bucket is TelemetryBucket.ONE_DAY:
            return timedelta(days=1)
        return timedelta(hours=1)
