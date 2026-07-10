"""Sensor anomaly scenario for Plant Alpha."""

from __future__ import annotations

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario


class SensorAnomalyScenario:
    """Inject temperature sensor bias while machine physics remain healthy."""

    name = "sensor_anomaly"

    def __init__(
        self,
        *,
        target_asset_id: str = "fuel-cell-stack-01",
        duration_sim_seconds: float = 12 * 60.0,
        end_bias_celsius: float = 12.0,
    ) -> None:
        self._target_asset_id = target_asset_id
        self._duration_sim_seconds = duration_sim_seconds
        self._end_bias_celsius = end_bias_celsius
        self._baseline = NormalOperationScenario()
        self._elapsed = 0.0

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        self._elapsed += dt_seconds
        self._baseline.tick(fleet, dt_seconds)
        progress = min(1.0, self._elapsed / self._duration_sim_seconds)
        bias = self._end_bias_celsius * progress
        fleet.telemetry_context(self._target_asset_id).sensor_bias[
            "stack_temperature"
        ] = bias
