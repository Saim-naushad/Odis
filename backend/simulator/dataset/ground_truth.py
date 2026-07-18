"""Ground-truth contract for dataset simulation runs.

Ground truth is derived only from the configured run/scenario timeline —
`RunConfig` plus the simulated elapsed time of a sample — never from
generated observation values, measurement thresholds, or reasoning-engine
output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from backend.simulator.dataset.run_config import DatasetScenario, RunConfig


class FaultType(StrEnum):
    """The physical-plant fault a run is configured for, constant per run.

    Distinct from `GroundTruthRecord.fault_active`: `fault_type` names *what*
    fault a run represents (or `NONE`), while `fault_active` marks *when* it
    is within its configured window. A sample can have a non-`NONE`
    `fault_type` while `fault_active` is `False` — before or after the fault
    window.

    `sensor_anomaly` is intentionally excluded here — it corrupts telemetry,
    not the plant, so it is represented by `SensorCorruptionType` instead.
    See the repository audit's fault feasibility matrix for why that split
    matters.
    """

    NONE = "none"
    COOLING_DEGRADATION = "cooling_degradation"
    HYDROGEN_SUPPLY_ISSUE = "hydrogen_supply_issue"


class SensorCorruptionType(StrEnum):
    """The sensor-telemetry corruption a run is configured for, constant per run.

    Sensor corruption is telemetry-layer, not a physical-plant fault (see
    `backend.simulator.scenarios.sensor_anomaly.SensorAnomalyScenario`, which
    only ever mutates `TelemetryContext.sensor_bias`), so it is tracked
    separately from `FaultType` rather than overloading it. PR161 only
    implements the bias ramp `SensorAnomalyScenario` already has.
    """

    NONE = "none"
    BIAS = "bias"


_FAULT_TYPE_BY_SCENARIO: dict[DatasetScenario, FaultType] = {
    DatasetScenario.COOLING_DEGRADATION: FaultType.COOLING_DEGRADATION,
    DatasetScenario.HYDROGEN_SUPPLY_ISSUE: FaultType.HYDROGEN_SUPPLY_ISSUE,
}
_SENSOR_CORRUPTION_BY_SCENARIO: dict[DatasetScenario, SensorCorruptionType] = {
    DatasetScenario.SENSOR_ANOMALY: SensorCorruptionType.BIAS,
}


@dataclass(frozen=True)
class GroundTruthRecord:
    """One asset's labeled state at one sample time within a run.

    Immutable fields: all.

    `fault_severity` is the instantaneous, ramped *effective* severity at
    this sample (0.0 outside the fault window) — not the run's configured
    maximum severity. It is computed from `elapsed_sim_seconds` and
    `RunConfig` alone, independent of the physical scenario object's own
    internal ramp state, and so may lag that object's ramp by up to one
    `dt_seconds` (see `runner.iter_samples`).
    """

    simulation_run_id: str
    timestamp: datetime
    elapsed_sim_seconds: float
    asset_id: str
    fault_type: FaultType
    fault_active: bool
    fault_severity: float
    seconds_since_fault_start: float | None
    sensor_corruption_type: SensorCorruptionType

    def __post_init__(self) -> None:
        if not self.simulation_run_id:
            raise ValueError("simulation_run_id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if self.fault_active and self.seconds_since_fault_start is None:
            raise ValueError(
                "active samples must report seconds_since_fault_start"
            )
        if not self.fault_active and self.seconds_since_fault_start is not None:
            raise ValueError(
                "inactive samples must not report seconds_since_fault_start"
            )
        if not self.fault_active and self.fault_severity != 0.0:
            raise ValueError("inactive samples must report fault_severity=0.0")


def compute_ground_truth(
    config: RunConfig,
    *,
    asset_id: str,
    timestamp: datetime,
    elapsed_sim_seconds: float,
) -> GroundTruthRecord:
    """Compute one asset's ground truth at one sample time.

    Uses `fault_start <= elapsed_sim_seconds < fault_end` (start inclusive,
    end exclusive) as the single documented interval convention for
    `fault_active`. Only `config.target_asset_id` can ever be active; every
    other asset is reported healthy, since PR161 only injects one fault on
    one asset per run.
    """
    fault_type = _FAULT_TYPE_BY_SCENARIO.get(config.scenario_name, FaultType.NONE)
    sensor_corruption_type = _SENSOR_CORRUPTION_BY_SCENARIO.get(
        config.scenario_name, SensorCorruptionType.NONE
    )
    if asset_id != config.target_asset_id:
        fault_type = FaultType.NONE
        sensor_corruption_type = SensorCorruptionType.NONE

    seconds_since_fault_start: float | None = None
    severity = 0.0
    active = False

    fault_start = config.fault_start_sim_seconds
    fault_end = config.fault_end_sim_seconds
    fault_duration = config.fault_duration_sim_seconds
    if (
        asset_id == config.target_asset_id
        and fault_start is not None
        and fault_end is not None
        and fault_duration is not None
        and fault_start <= elapsed_sim_seconds < fault_end
    ):
        active = True
        seconds_since_fault_start = elapsed_sim_seconds - fault_start
        progress = min(1.0, seconds_since_fault_start / fault_duration)
        severity = config.fault_severity * progress

    return GroundTruthRecord(
        simulation_run_id=config.simulation_run_id,
        timestamp=timestamp,
        elapsed_sim_seconds=elapsed_sim_seconds,
        asset_id=asset_id,
        fault_type=fault_type,
        fault_active=active,
        fault_severity=severity,
        seconds_since_fault_start=seconds_since_fault_start,
        sensor_corruption_type=sensor_corruption_type,
    )
