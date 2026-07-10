"""Telemetry forecast domain model specifications."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.value_objects.telemetry_forecast import ForecastSample, TelemetryForecast


def test_telemetry_forecast_requires_chronological_future_samples() -> None:
    horizon_start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="after horizon_start"):
        TelemetryForecast(
            asset_id="asset-1",
            measurement_type="temperature",
            unit="celsius",
            model_id="fake_v1",
            horizon_start=horizon_start,
            generated_at=datetime(2026, 1, 1, 12, 5, tzinfo=UTC),
            samples=(
                ForecastSample(timestamp=horizon_start, value=1.0),
                ForecastSample(
                    timestamp=horizon_start + timedelta(hours=1),
                    value=2.0,
                ),
            ),
        )
