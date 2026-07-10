"""Forecast inference engine factory."""

from __future__ import annotations

from pathlib import Path

from backend.app.application.forecast_inference_engine import (
    ForecastInferenceEngine,
    ForecastModelSpec,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.inference.onnx_forecast_engine import (
    OnnxForecastInferenceEngine,
)

DEFAULT_MODEL_SPEC = ForecastModelSpec(
    model_id="persistence_drift_v1",
    context_length=24,
    horizon_steps=12,
)


def default_model_path() -> Path:
    """Return the bundled validation ONNX model path."""
    return (
        Path(__file__).resolve().parent / "models" / "persistence_drift_v1.onnx"
    )


def create_forecast_inference_engine(
    settings: Settings,
) -> ForecastInferenceEngine | None:
    """Load the configured ONNX model once per process."""
    if not settings.forecast_enabled:
        return None

    model_path = Path(settings.onnx_model_path or default_model_path())
    model_spec = ForecastModelSpec(
        model_id=settings.onnx_model_id,
        context_length=settings.forecast_context_length,
        horizon_steps=settings.forecast_horizon_steps,
    )
    return OnnxForecastInferenceEngine.from_model_path(
        model_path,
        model_spec=model_spec,
    )
