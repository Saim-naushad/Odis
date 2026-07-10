"""ONNX forecast engine specifications."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from backend.app.application.feature_builder import FeatureBuilder
from backend.app.application.forecast_inference_engine import ForecastModelSpec
from backend.app.infrastructure.inference.onnx_forecast_engine import (
    OnnxForecastInferenceEngine,
)
from domain.value_objects.telemetry_series import TelemetrySample, TelemetrySeries

pytest.importorskip("onnxruntime")

MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "app"
    / "infrastructure"
    / "inference"
    / "models"
    / "persistence_drift_v1.onnx"
)
MODEL_SPEC = ForecastModelSpec(
    model_id="persistence_drift_v1",
    context_length=24,
    horizon_steps=12,
)


@pytest.fixture
def engine() -> OnnxForecastInferenceEngine:
    return OnnxForecastInferenceEngine.from_model_path(
        MODEL_PATH,
        model_spec=MODEL_SPEC,
    )


def test_onnx_engine_extrapolates_linear_drift(
    engine: OnnxForecastInferenceEngine,
) -> None:
    context = np.linspace(10.0, 33.0, 24, dtype=np.float32)
    builder = FeatureBuilder(context_length=24)
    series = TelemetrySeries(
        asset_id="asset-1",
        measurement_type="temperature",
        unit="celsius",
        samples=tuple(
            TelemetrySample(
                timestamp=datetime(2026, 1, 1, index, tzinfo=UTC),
                value=float(value),
            )
            for index, value in enumerate(context.tolist())
        ),
    )
    features = builder.build_from_series(series)

    predictions = engine.predict(features.values)
    denormalized = features.denormalize(predictions)

    assert len(predictions) == 12
    assert denormalized[0] == pytest.approx(34.0, rel=1e-3)
    assert denormalized[1] == pytest.approx(35.0, rel=1e-3)
