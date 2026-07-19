"""No-recovery fault policy specifications (PR167 blocking-review correction).

PR161 never reset `cooling_efficiency`/`fuel_supply_factor`/`sensor_bias`
once a fault ramp finished — but until this correction, `ground_truth.py`
still reported `fault_active=False` (and `fault_severity=0.0`) once
`elapsed_sim_seconds` passed `fault_start + fault_duration`, mislabeling
samples whose telemetry still reflected the persisted fault as healthy.

This module checks, for all three fault classes: the fault stays active
and at maximum severity from ramp completion through the end of the run,
non-target assets are unaffected, healthy runs are unaffected, and —
critically — the *observable telemetry* (not just the ground-truth label)
still reflects the fault after ramp completion, cross-checked against a
telemetry snapshot from well before the fault started.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.simulator.dataset.ground_truth import (
    FaultType,
    GroundTruthRecord,
    SensorCorruptionType,
)
from backend.simulator.dataset.operating_conditions import OperatingConditions
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.runner import RunResult, run

_TARGET_ASSET = "fuel-cell-stack-01"
_OTHER_ASSET = "fuel-cell-stack-02"
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)
_DT = 10.0
_FAULT_START = 120.0
_FAULT_DURATION = 240.0
_RAMP_END = _FAULT_START + _FAULT_DURATION
_DURATION = 900.0
_SEVERITY = 1.0

# (scenario, primary telemetry proxy, direction the proxy moves once the
# fault is applied — "increase" or "decrease"). Chosen to be directly,
# physically driven by the fault's own applied parameter (not a channel
# with no modeled relationship — see PR166's physical-signature audit):
# cooling_degradation's coolant_flow term depends only on cooling_efficiency
# and load; hydrogen's voltage carries the PR162 starvation penalty
# directly; sensor_anomaly's stack_temperature *is* the biased channel.
_SCENARIOS = (
    (DatasetScenario.COOLING_DEGRADATION, "coolant_flow", "increase"),
    (DatasetScenario.HYDROGEN_SUPPLY_ISSUE, "voltage", "decrease"),
    (DatasetScenario.SENSOR_ANOMALY, "stack_temperature", "increase"),
)


def _config(scenario_name: DatasetScenario) -> RunConfig:
    return RunConfig(
        simulation_run_id="persistence-test",
        seed=7,
        scenario_name=scenario_name,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=_DURATION,
        dt_seconds=_DT,
        run_start_time=_RUN_START,
        fault_start_sim_seconds=_FAULT_START,
        fault_duration_sim_seconds=_FAULT_DURATION,
        fault_severity=_SEVERITY,
        # Zero load oscillation: the persistence check below compares one
        # telemetry sample well before the fault to one well after ramp
        # end, so it must not be confounded by the load's own independent
        # sinusoidal variation (see machine.py: coolant_flow, for example,
        # depends on both cooling_efficiency *and* load_fraction).
        operating_conditions=OperatingConditions(load_amplitude_percent=0.0),
    )


def _ground_truth_at(
    result: RunResult, elapsed: float, asset_id: str = _TARGET_ASSET
) -> GroundTruthRecord:
    return next(
        record
        for record in result.ground_truth
        if record.asset_id == asset_id
        and record.elapsed_sim_seconds == pytest.approx(elapsed)
    )


def _observation_at(result: RunResult, elapsed: float, measurement: str) -> float:
    timestamp = _RUN_START + timedelta(seconds=elapsed)
    return next(
        obs.value
        for obs in result.observations
        if obs.asset_id == _TARGET_ASSET
        and obs.timestamp == timestamp
        and obs.measurement_type.name == measurement
    )


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_inactive_before_fault_start(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    record = _ground_truth_at(result, _FAULT_START - _DT)
    assert record.fault_active is False
    assert record.fault_severity == 0.0
    assert record.seconds_since_fault_start is None


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_active_exactly_at_fault_start(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    record = _ground_truth_at(result, _FAULT_START)
    assert record.fault_active is True
    assert record.seconds_since_fault_start == pytest.approx(0.0)
    assert record.fault_severity == pytest.approx(0.0)  # progress=0 at onset


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_severity_increases_during_ramp(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    early = _ground_truth_at(result, _FAULT_START + _DT)
    later = _ground_truth_at(result, _FAULT_START + _FAULT_DURATION / 2)
    assert 0.0 < early.fault_severity < later.fault_severity < _SEVERITY


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_active_exactly_at_ramp_end(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    record = _ground_truth_at(result, _RAMP_END)
    assert record.fault_active is True
    assert record.fault_severity == pytest.approx(_SEVERITY)


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_severity_equals_maximum_after_ramp_end(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    for elapsed in (_RAMP_END + _DT, _RAMP_END + 200.0, _DURATION):
        record = _ground_truth_at(result, elapsed)
        assert record.fault_active is True, f"elapsed={elapsed}"
        assert record.fault_severity == pytest.approx(_SEVERITY), f"elapsed={elapsed}"


@pytest.mark.parametrize("scenario_name,measurement,direction", _SCENARIOS)
def test_physical_or_sensor_effect_remains_applied_after_ramp_end(
    scenario_name: DatasetScenario, measurement: str, direction: str
) -> None:
    """The critical check: observable telemetry, not just the label, still
    reflects the fault well after the ramp completes."""
    result = run(_config(scenario_name))
    pre_fault_value = _observation_at(result, _FAULT_START - _DT, measurement)
    post_ramp_value = _observation_at(result, _DURATION, measurement)

    if direction == "increase":
        assert post_ramp_value > pre_fault_value, (
            f"{scenario_name}: {measurement} did not remain elevated at "
            f"run end (pre={pre_fault_value}, post={post_ramp_value})"
        )
    else:
        assert post_ramp_value < pre_fault_value, (
            f"{scenario_name}: {measurement} did not remain depressed at "
            f"run end (pre={pre_fault_value}, post={post_ramp_value})"
        )


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_final_sample_remains_fault_labeled(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    record = _ground_truth_at(result, _DURATION)
    assert record.fault_active is True
    if scenario_name is DatasetScenario.SENSOR_ANOMALY:
        assert record.fault_type is FaultType.NONE
        assert record.sensor_corruption_type is SensorCorruptionType.BIAS
    else:
        assert record.fault_type is not FaultType.NONE
        assert record.sensor_corruption_type is SensorCorruptionType.NONE


@pytest.mark.parametrize("scenario_name,_measurement,_direction", _SCENARIOS)
def test_non_target_asset_remains_healthy_for_entire_run(
    scenario_name: DatasetScenario, _measurement: str, _direction: str
) -> None:
    result = run(_config(scenario_name))
    other_asset_records = [
        r for r in result.ground_truth if r.asset_id == _OTHER_ASSET
    ]
    assert other_asset_records
    for record in other_asset_records:
        assert record.fault_active is False
        assert record.fault_type is FaultType.NONE
        assert record.sensor_corruption_type is SensorCorruptionType.NONE
        assert record.fault_severity == 0.0


def test_healthy_run_remains_entirely_healthy_for_every_asset() -> None:
    config = RunConfig(
        simulation_run_id="healthy-persistence-test",
        seed=7,
        scenario_name=DatasetScenario.NORMAL_OPERATION,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=_DURATION,
        dt_seconds=_DT,
        run_start_time=_RUN_START,
    )
    result = run(config)
    assert result.ground_truth
    for record in result.ground_truth:
        assert record.fault_active is False
        assert record.fault_type is FaultType.NONE
        assert record.sensor_corruption_type is SensorCorruptionType.NONE
        assert record.fault_severity == 0.0
