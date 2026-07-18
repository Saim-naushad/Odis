"""Ground-truth computation specifications.

Exercises `compute_ground_truth` directly — a pure function of `RunConfig`
and an elapsed time — to pin down interval and severity semantics precisely,
independent of the runner's tick loop.
"""

from datetime import UTC, datetime

import pytest

from backend.simulator.dataset.ground_truth import (
    FaultType,
    SensorCorruptionType,
    compute_ground_truth,
)
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig

_TARGET_ASSET = "fuel-cell-stack-01"
_OTHER_ASSET = "fuel-cell-stack-02"
_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _cooling_config(severity: float = 1.0) -> RunConfig:
    return RunConfig(
        simulation_run_id="run-1",
        seed=1,
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=1200.0,
        dt_seconds=30.0,
        run_start_time=_TIMESTAMP,
        fault_start_sim_seconds=300.0,
        fault_duration_sim_seconds=600.0,
        fault_severity=severity,
    )


def _healthy_config() -> RunConfig:
    return RunConfig(
        simulation_run_id="run-1",
        seed=1,
        scenario_name=DatasetScenario.NORMAL_OPERATION,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=600.0,
        dt_seconds=30.0,
        run_start_time=_TIMESTAMP,
    )


def test_sample_before_fault_start_is_inactive() -> None:
    record = compute_ground_truth(
        _cooling_config(),
        asset_id=_TARGET_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=270.0,
    )
    assert record.fault_active is False
    assert record.fault_severity == 0.0
    assert record.seconds_since_fault_start is None
    assert record.fault_type is FaultType.COOLING_DEGRADATION


def test_sample_exactly_at_fault_start_is_active() -> None:
    record = compute_ground_truth(
        _cooling_config(),
        asset_id=_TARGET_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=300.0,
    )
    assert record.fault_active is True
    assert record.seconds_since_fault_start == 0.0
    assert record.fault_severity == 0.0  # progress is 0 at the instant of start


def test_final_active_sample_just_before_fault_end() -> None:
    record = compute_ground_truth(
        _cooling_config(),
        asset_id=_TARGET_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=870.0,
    )
    assert record.fault_active is True
    assert record.seconds_since_fault_start == 570.0
    assert record.fault_severity == pytest.approx(1.0 * (570.0 / 600.0))


def test_first_sample_after_fault_end_is_inactive() -> None:
    record = compute_ground_truth(
        _cooling_config(),
        asset_id=_TARGET_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=900.0,
    )
    assert record.fault_active is False
    assert record.fault_severity == 0.0
    assert record.seconds_since_fault_start is None
    # fault_type stays constant for the run even once the window has closed.
    assert record.fault_type is FaultType.COOLING_DEGRADATION


def test_severity_scales_configured_maximum() -> None:
    record = compute_ground_truth(
        _cooling_config(severity=0.5),
        asset_id=_TARGET_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=600.0,  # halfway through the 600s window
    )
    assert record.fault_severity == pytest.approx(0.5 * 0.5)


def test_non_target_asset_is_always_healthy() -> None:
    record = compute_ground_truth(
        _cooling_config(),
        asset_id=_OTHER_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=600.0,  # inside the target asset's active window
    )
    assert record.fault_active is False
    assert record.fault_type is FaultType.NONE
    assert record.fault_severity == 0.0
    assert record.seconds_since_fault_start is None


def test_healthy_run_never_reports_a_fault() -> None:
    for elapsed in (0.0, 300.0, 600.0):
        record = compute_ground_truth(
            _healthy_config(),
            asset_id=_TARGET_ASSET,
            timestamp=_TIMESTAMP,
            elapsed_sim_seconds=elapsed,
        )
        assert record.fault_active is False
        assert record.fault_type is FaultType.NONE
        assert record.fault_severity == 0.0
        assert record.seconds_since_fault_start is None


def test_sensor_anomaly_populates_sensor_corruption_not_fault_type() -> None:
    config = RunConfig(
        simulation_run_id="run-1",
        seed=1,
        scenario_name=DatasetScenario.SENSOR_ANOMALY,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=1200.0,
        dt_seconds=30.0,
        run_start_time=_TIMESTAMP,
        fault_start_sim_seconds=300.0,
        fault_duration_sim_seconds=600.0,
        fault_severity=1.0,
    )
    record = compute_ground_truth(
        config,
        asset_id=_TARGET_ASSET,
        timestamp=_TIMESTAMP,
        elapsed_sim_seconds=600.0,
    )
    assert record.fault_type is FaultType.NONE
    assert record.sensor_corruption_type is SensorCorruptionType.BIAS
    assert record.fault_active is True
