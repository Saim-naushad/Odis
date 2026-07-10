"""Forecast inference interface.

Concrete ONNX Runtime implementations live in infrastructure. Application code
depends only on this protocol so models can be swapped without changing
``ForecastInferenceService``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ForecastModelSpec:
    """Metadata describing a loaded forecast model."""

    model_id: str
    context_length: int
    horizon_steps: int
    input_name: str = "context"
    output_name: str = "forecast"


class ForecastInferenceEngine(Protocol):
    """Runs model inference from normalized feature vectors."""

    @property
    def model_spec(self) -> ForecastModelSpec:
        """Return metadata for the loaded model."""

    def predict(self, features: tuple[float, ...]) -> tuple[float, ...]:
        """Return normalized horizon predictions for one feature window."""
