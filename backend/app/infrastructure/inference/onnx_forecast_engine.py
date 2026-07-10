"""ONNX Runtime forecast inference adapter."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort

from backend.app.application.forecast_inference_engine import ForecastModelSpec
from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)


class OnnxForecastInferenceEngine:
    """Infrastructure adapter that hides ONNX Runtime behind a narrow interface."""

    def __init__(
        self,
        *,
        model_path: Path,
        model_spec: ForecastModelSpec,
        session: ort.InferenceSession | None = None,
    ) -> None:
        self._model_spec = model_spec
        self._model_path = model_path
        self._session = session or self._create_session(model_path)

    @property
    def model_spec(self) -> ForecastModelSpec:
        return self._model_spec

    def predict(self, features: tuple[float, ...]) -> tuple[float, ...]:
        if len(features) != self._model_spec.context_length:
            msg = (
                f"expected {self._model_spec.context_length} feature values; "
                f"received {len(features)}"
            )
            raise ValueError(msg)

        input_array = np.asarray([features], dtype=np.float32)
        outputs = self._session.run(
            [self._model_spec.output_name],
            {self._model_spec.input_name: input_array},
        )
        predictions = outputs[0][0]
        horizon = self._model_spec.horizon_steps
        return tuple(float(value) for value in predictions[:horizon])

    @classmethod
    def from_model_path(
        cls,
        model_path: Path,
        *,
        model_spec: ForecastModelSpec,
    ) -> OnnxForecastInferenceEngine:
        """Load an ONNX model once and reuse the inference session."""
        resolved = model_path.resolve()
        if not resolved.is_file():
            msg = f"ONNX model not found at {resolved}"
            raise FileNotFoundError(msg)

        session = cls._create_session(resolved)
        engine = cls(model_path=resolved, model_spec=model_spec, session=session)
        logger.info(
            "forecast_model_loaded",
            model_id=model_spec.model_id,
            model_path=str(resolved),
            context_length=model_spec.context_length,
            horizon_steps=model_spec.horizon_steps,
        )
        return engine

    @staticmethod
    def _create_session(model_path: Path) -> ort.InferenceSession:
        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
        )
        return ort.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
