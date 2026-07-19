"""Offline dataset run kernel specifications."""

import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.simulator.dataset.ground_truth import FaultType, GroundTruthRecord
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.dataset.runner import RunResult, run
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.telemetry import observations_from_machine

_TARGET_ASSET = "fuel-cell-stack-01"
_RUN_START = datetime(2026, 1, 1, tzinfo=UTC)


def _cooling_config(run_id: str = "run-1") -> RunConfig:
    return RunConfig(
        simulation_run_id=run_id,
        seed=1,
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=1200.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
        fault_start_sim_seconds=300.0,
        fault_duration_sim_seconds=600.0,
        fault_severity=1.0,
    )


def _hydrogen_config(run_id: str = "run-1") -> RunConfig:
    return RunConfig(
        simulation_run_id=run_id,
        seed=1,
        scenario_name=DatasetScenario.HYDROGEN_SUPPLY_ISSUE,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=1200.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
        fault_start_sim_seconds=300.0,
        fault_duration_sim_seconds=600.0,
        fault_severity=1.0,
    )


def _healthy_config(run_id: str = "run-1") -> RunConfig:
    return RunConfig(
        simulation_run_id=run_id,
        seed=1,
        scenario_name=DatasetScenario.NORMAL_OPERATION,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=600.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
    )


def _target_ground_truth_by_elapsed(
    result: RunResult, elapsed: float
) -> GroundTruthRecord:
    return next(
        record
        for record in result.ground_truth
        if record.asset_id == _TARGET_ASSET
        and record.elapsed_sim_seconds == pytest.approx(elapsed)
    )


# --- Determinism -----------------------------------------------------------


def test_identical_configuration_produces_identical_observations() -> None:
    first = run(_cooling_config())
    second = run(_cooling_config())

    assert len(first.observations) == len(second.observations)
    for a, b in zip(first.observations, second.observations, strict=True):
        assert a.id == b.id
        assert a.asset_id == b.asset_id
        assert a.timestamp == b.timestamp
        assert a.measurement_type == b.measurement_type
        assert a.value == b.value
        assert a.unit == b.unit


def test_identical_configuration_produces_identical_ground_truth() -> None:
    first = run(_cooling_config())
    second = run(_cooling_config())

    assert first.ground_truth == second.ground_truth


def test_timestamps_equal_run_start_plus_simulated_offset() -> None:
    result = run(_cooling_config())
    for observation in result.observations:
        offset = (observation.timestamp - _RUN_START).total_seconds()
        assert offset > 0
        assert offset % 30.0 == 0.0

    for record in result.ground_truth:
        assert record.timestamp == _RUN_START + timedelta(
            seconds=record.elapsed_sim_seconds
        )


def test_execution_never_calls_time_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dataset runner must not sleep")

    monkeypatch.setattr(time, "sleep", _fail_if_called)
    run(_cooling_config())


# --- Fault timeline: cooling degradation -----------------------------------


def test_cooling_degradation_inactive_before_fault_start() -> None:
    result = run(_cooling_config())
    record = _target_ground_truth_by_elapsed(result, 270.0)
    assert record.fault_active is False
    assert record.fault_severity == 0.0
    assert record.seconds_since_fault_start is None


def test_cooling_degradation_active_exactly_at_fault_start() -> None:
    result = run(_cooling_config())
    record = _target_ground_truth_by_elapsed(result, 300.0)
    assert record.fault_active is True
    assert record.seconds_since_fault_start == 0.0


def test_cooling_degradation_active_during_window() -> None:
    result = run(_cooling_config())
    record = _target_ground_truth_by_elapsed(result, 600.0)
    assert record.fault_active is True
    assert record.fault_type is FaultType.COOLING_DEGRADATION
    assert 0.0 < record.fault_severity < 1.0


def test_cooling_degradation_active_at_ramp_end() -> None:
    # ramp_end = fault_start (300) + fault_duration (600) = 900 — the run's
    # last sample. No-recovery policy: still active, at maximum severity.
    result = run(_cooling_config())
    record = _target_ground_truth_by_elapsed(result, 900.0)
    assert record.fault_active is True
    assert record.fault_severity == pytest.approx(1.0)
    assert record.seconds_since_fault_start == pytest.approx(600.0)


def test_cooling_degradation_remains_active_and_at_maximum_severity_past_ramp_end() -> (
    None
):
    # A longer run than the ramp needs, so there are real post-ramp samples
    # to check remain fault-labeled at maximum severity (not healthy).
    config = replace(_cooling_config(), duration_sim_seconds=1500.0)
    result = run(config)
    record = _target_ground_truth_by_elapsed(result, 1200.0)  # 300s past ramp_end
    assert record.fault_active is True
    assert record.fault_type is FaultType.COOLING_DEGRADATION
    assert record.fault_severity == pytest.approx(1.0)
    assert record.seconds_since_fault_start == pytest.approx(900.0)

    last_record = _target_ground_truth_by_elapsed(result, 1500.0)
    assert last_record.fault_active is True
    assert last_record.fault_severity == pytest.approx(1.0)


def test_cooling_degradation_seconds_since_start_tracks_elapsed() -> None:
    result = run(_cooling_config())
    record = _target_ground_truth_by_elapsed(result, 630.0)
    assert record.seconds_since_fault_start == pytest.approx(330.0)


# --- Fault timeline: hydrogen supply issue ----------------------------------


def test_hydrogen_supply_issue_inactive_before_fault_start() -> None:
    result = run(_hydrogen_config())
    record = _target_ground_truth_by_elapsed(result, 270.0)
    assert record.fault_active is False


def test_hydrogen_supply_issue_active_exactly_at_fault_start() -> None:
    result = run(_hydrogen_config())
    record = _target_ground_truth_by_elapsed(result, 300.0)
    assert record.fault_active is True
    assert record.fault_type is FaultType.HYDROGEN_SUPPLY_ISSUE


def test_hydrogen_supply_issue_active_at_ramp_end() -> None:
    result = run(_hydrogen_config())
    record = _target_ground_truth_by_elapsed(result, 900.0)
    assert record.fault_active is True
    assert record.fault_severity == pytest.approx(1.0)


def test_hydrogen_supply_issue_remains_active_past_ramp_end() -> None:
    config = replace(_hydrogen_config(), duration_sim_seconds=1500.0)
    result = run(config)
    record = _target_ground_truth_by_elapsed(result, 1200.0)
    assert record.fault_active is True
    assert record.fault_type is FaultType.HYDROGEN_SUPPLY_ISSUE
    assert record.fault_severity == pytest.approx(1.0)


# --- Healthy runs ------------------------------------------------------------


def test_healthy_run_reports_no_faulty_samples() -> None:
    result = run(_healthy_config())
    assert result.sample_count > 0
    for record in result.ground_truth:
        assert record.fault_active is False
        assert record.fault_type is FaultType.NONE
        assert record.fault_severity == 0.0


def test_healthy_run_still_produces_observations() -> None:
    result = run(_healthy_config())
    assert len(result.observations) > 0


# --- Invalid target asset ----------------------------------------------------


def test_unknown_target_asset_is_rejected_at_execution() -> None:
    config = RunConfig(
        simulation_run_id="run-1",
        seed=1,
        scenario_name=DatasetScenario.NORMAL_OPERATION,
        target_asset_id="fuel-cell-stack-99",
        duration_sim_seconds=60.0,
        dt_seconds=30.0,
        run_start_time=_RUN_START,
    )
    with pytest.raises(ValueError):
        run(config)


# --- Canonical telemetry reuse ------------------------------------------------


def test_generated_observations_match_canonical_telemetry_mapping() -> None:
    """The runner must not reinvent telemetry construction — it must reuse
    `observations_from_machine` and produce the same measurement vocabulary
    the live simulator does for an equivalent fleet state.
    """
    result = run(_healthy_config())
    target_observations = [
        obs for obs in result.observations if obs.asset_id == _TARGET_ASSET
    ]
    first_sample_names = {
        obs.measurement_type.name
        for obs in target_observations
        if obs.timestamp == _RUN_START + timedelta(seconds=30.0)
    }

    reference_fleet = PlantAlphaFleet.create(run_id="reference")
    reference_names = {
        obs.measurement_type.name
        for obs in observations_from_machine(
            reference_fleet.machine(_TARGET_ASSET),
            timestamp=_RUN_START,
            context=reference_fleet.telemetry_context(_TARGET_ASSET),
        )
    }

    assert first_sample_names == reference_names


def test_all_fleet_assets_are_represented_in_ground_truth() -> None:
    result = run(_cooling_config())
    asset_ids = {record.asset_id for record in result.ground_truth}
    assert asset_ids == {
        "fuel-cell-stack-01",
        "fuel-cell-stack-02",
        "fuel-cell-stack-03",
        "fuel-cell-stack-04",
    }


def test_only_target_asset_ever_reports_active_fault() -> None:
    result = run(_cooling_config())
    for record in result.ground_truth:
        if record.fault_active:
            assert record.asset_id == _TARGET_ASSET
