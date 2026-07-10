"""Feature builder specifications."""

from datetime import UTC, datetime

import pytest

from backend.app.application.feature_builder import FeatureBuilder
from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_series import TelemetrySample, TelemetrySeries


@pytest.fixture
def feature_builder() -> FeatureBuilder:
    return FeatureBuilder(context_length=4)


def test_build_from_series_pads_and_normalizes(
    feature_builder: FeatureBuilder,
) -> None:
    series = TelemetrySeries(
        asset_id="asset-1",
        measurement_type="temperature",
        unit="celsius",
        samples=(
            TelemetrySample(
                timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                value=10.0,
            ),
            TelemetrySample(
                timestamp=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
                value=14.0,
            ),
        ),
    )

    features = feature_builder.build_from_series(series)

    assert len(features.values) == 4
    assert features.values[0] == features.values[1]
    assert features.denormalize((0.0,)) == (11.0,)


def test_build_from_aggregate_points_uses_chronological_avg_values(
    feature_builder: FeatureBuilder,
) -> None:
    points = [
        TelemetryAggregatePoint(
            bucket=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
            measurement_type="temperature",
            avg_value=14.0,
            min_value=12.0,
            max_value=16.0,
            sample_count=2,
            unit="celsius",
        ),
        TelemetryAggregatePoint(
            bucket=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            measurement_type="temperature",
            avg_value=10.0,
            min_value=9.0,
            max_value=11.0,
            sample_count=2,
            unit="celsius",
        ),
    ]

    features = feature_builder.build_from_aggregate_points(points)

    assert len(features.values) == 4
    assert features.mean == pytest.approx(11.0)
