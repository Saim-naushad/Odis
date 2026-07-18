"""Sample/label alignment specifications for a nontrivial `dt_seconds`.

Independently reconstructs the tick sequence `runner.iter_samples`
documents (apply the fault effect for this sample's own progress, *then*
advance physics) using only public simulator APIs, and cross-checks it
byte-for-byte against `run()`'s real published telemetry at each boundary —
not just `fault_active` — so a wiring regression in the runner (wrong
order, wrong window inequality, wrong progress input) would make this
independently-built reference trajectory diverge from the real one and fail
the test, rather than a test that only checks booleans.

Boundaries checked, per the correction request: `fault_start - dt`,
`fault_start`, `fault_start + dt`, `fault_end - dt`, `fault_end`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.simulator.dataset.fault_effect import apply_fault_effect
from backend.simulator.dataset.ground_truth import GroundTruthRecord
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.runner import RunResult, run
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.telemetry import observations_from_machine

_TARGET_ASSET = "fuel-cell-stack-01"
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)
_DT = 5.0
_FAULT_START = 100.0
_FAULT_DURATION = 200.0
_FAULT_END = _FAULT_START + _FAULT_DURATION
_DURATION = 400.0
_SEVERITY = 1.0

_BOUNDARY_ELAPSED_TIMES = (
    _FAULT_START - _DT,
    _FAULT_START,
    _FAULT_START + _DT,
    _FAULT_END - _DT,
    _FAULT_END,
)


def _config(scenario_name: DatasetScenario) -> RunConfig:
    return RunConfig(
        simulation_run_id="alignment-test",
        seed=1,
        scenario_name=scenario_name,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=_DURATION,
        dt_seconds=_DT,
        run_start_time=_RUN_START,
        fault_start_sim_seconds=_FAULT_START,
        fault_duration_sim_seconds=_FAULT_DURATION,
        fault_severity=_SEVERITY,
    )


def _reference_trajectory(
    config: RunConfig, *, published_measurement: str
) -> dict[float, float]:
    """Replay the documented contract from scratch and record one published
    measurement's value at every sample time, using only public simulator
    APIs — independent of `runner.iter_samples`'s own implementation.
    """
    fault_start = config.fault_start_sim_seconds
    fault_end = config.fault_end_sim_seconds
    fault_duration = config.fault_duration_sim_seconds
    assert fault_start is not None
    assert fault_end is not None
    assert fault_duration is not None

    fleet = PlantAlphaFleet.create(run_id="alignment-reference")
    baseline = NormalOperationScenario()
    values: dict[float, float] = {}
    total_steps = round(config.duration_sim_seconds / config.dt_seconds)

    for _ in range(total_steps):
        predicted_elapsed = fleet.elapsed_sim_seconds + config.dt_seconds
        if fault_start <= predicted_elapsed < fault_end:
            progress = min(1.0, (predicted_elapsed - fault_start) / fault_duration)
            apply_fault_effect(fleet, config, progress=progress)
        baseline.tick(fleet, config.dt_seconds)

        for observation in observations_from_machine(
            fleet.machine(_TARGET_ASSET),
            timestamp=_RUN_START,  # irrelevant to the physical value checked
            context=fleet.telemetry_context(_TARGET_ASSET),
        ):
            if observation.measurement_type.name == published_measurement:
                values[fleet.elapsed_sim_seconds] = observation.value

    return values


def _ground_truth_at(result: RunResult, elapsed: float) -> GroundTruthRecord:
    return next(
        record
        for record in result.ground_truth
        if record.asset_id == _TARGET_ASSET
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


def _assert_boundary_alignment(
    result: RunResult, reference: dict[float, float], measurement: str
) -> None:
    for elapsed in _BOUNDARY_ELAPSED_TIMES:
        record = _ground_truth_at(result, elapsed)
        observed = _observation_at(result, elapsed, measurement)

        assert observed == pytest.approx(reference[elapsed]), (
            f"{measurement} at t={elapsed} diverges from an independent replay "
            "of the documented tick sequence — physics and label are no "
            "longer produced from the same regime/progress"
        )

        expected_active = _FAULT_START <= elapsed < _FAULT_END
        assert record.fault_active is expected_active, f"fault_active at t={elapsed}"

        if expected_active:
            expected_seconds_since_start = elapsed - _FAULT_START
            expected_progress = min(
                1.0, expected_seconds_since_start / _FAULT_DURATION
            )
            assert record.seconds_since_fault_start == pytest.approx(
                expected_seconds_since_start
            ), f"seconds_since_fault_start at t={elapsed}"
            assert record.fault_severity == pytest.approx(
                _SEVERITY * expected_progress
            ), f"fault_severity at t={elapsed}"
        else:
            assert record.seconds_since_fault_start is None
            assert record.fault_severity == 0.0


def test_cooling_degradation_sample_and_label_agree_at_every_boundary() -> None:
    config = _config(DatasetScenario.COOLING_DEGRADATION)
    result = run(config)
    reference = _reference_trajectory(
        config, published_measurement="stack_temperature"
    )
    _assert_boundary_alignment(result, reference, "stack_temperature")


def test_hydrogen_supply_issue_sample_and_label_agree_at_every_boundary() -> None:
    config = _config(DatasetScenario.HYDROGEN_SUPPLY_ISSUE)
    result = run(config)
    reference = _reference_trajectory(config, published_measurement="fuel_flow")
    _assert_boundary_alignment(result, reference, "fuel_flow")
