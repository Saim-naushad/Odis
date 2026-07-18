"""`apply_fault_effect` specifications.

For cooling degradation and hydrogen supply issue, the applied value is a
lag *target*, not an immediately-visible reading, so verification ticks the
fleet once with a very large `dt_seconds` — large enough relative to the
machine's lag time constants that `_lag_toward` converges to the target
almost exactly — letting the assertion check the target itself without
reaching into private machine state. Sensor anomaly bias has no lag (it is
applied directly to `TelemetryContext.sensor_bias`), so it is checked
directly.
"""

from datetime import UTC, datetime

import pytest

from backend.simulator.dataset.fault_effect import apply_fault_effect
from backend.simulator.dataset.run_config import DatasetScenario, RunConfig
from backend.simulator.plant import PlantAlphaFleet

_TARGET_ASSET = "fuel-cell-stack-01"
_OTHER_ASSET = "fuel-cell-stack-02"
_FORCE_CONVERGENCE_DT = 100_000.0


def _fault_config(scenario_name: DatasetScenario, severity: float = 1.0) -> RunConfig:
    return RunConfig(
        simulation_run_id="run-1",
        seed=1,
        scenario_name=scenario_name,
        target_asset_id=_TARGET_ASSET,
        duration_sim_seconds=1200.0,
        dt_seconds=30.0,
        run_start_time=datetime(2026, 1, 1, tzinfo=UTC),
        fault_start_sim_seconds=300.0,
        fault_duration_sim_seconds=600.0,
        fault_severity=severity,
    )


def test_cooling_degradation_effect_converges_to_expected_target() -> None:
    fleet = PlantAlphaFleet.create(run_id="fault-effect-test")
    apply_fault_effect(
        fleet, _fault_config(DatasetScenario.COOLING_DEGRADATION), progress=0.5
    )
    fleet.machine(_TARGET_ASSET).tick(_FORCE_CONVERGENCE_DT)

    expected = 0.85 + (0.55 - 0.85) * 0.5
    assert fleet.machine(_TARGET_ASSET).state.cooling_efficiency == pytest.approx(
        expected, abs=1e-3
    )


def test_hydrogen_supply_issue_effect_converges_to_expected_target() -> None:
    fleet = PlantAlphaFleet.create(run_id="fault-effect-test")
    apply_fault_effect(
        fleet, _fault_config(DatasetScenario.HYDROGEN_SUPPLY_ISSUE), progress=0.5
    )
    fleet.machine(_TARGET_ASSET).tick(_FORCE_CONVERGENCE_DT)

    expected = 1.0 + (0.6 - 1.0) * 0.5
    assert fleet.machine(_TARGET_ASSET).state.fuel_supply_factor == pytest.approx(
        expected, abs=1e-3
    )


def test_sensor_anomaly_effect_is_applied_immediately_with_no_lag() -> None:
    fleet = PlantAlphaFleet.create(run_id="fault-effect-test")
    apply_fault_effect(
        fleet, _fault_config(DatasetScenario.SENSOR_ANOMALY), progress=0.5
    )

    bias = fleet.telemetry_context(_TARGET_ASSET).sensor_bias["stack_temperature"]
    assert bias == pytest.approx(0.5 * 12.0)


def test_progress_zero_reproduces_the_healthy_starting_value() -> None:
    fleet = PlantAlphaFleet.create(run_id="fault-effect-test")
    apply_fault_effect(
        fleet, _fault_config(DatasetScenario.COOLING_DEGRADATION), progress=0.0
    )
    fleet.machine(_TARGET_ASSET).tick(_FORCE_CONVERGENCE_DT)

    assert fleet.machine(_TARGET_ASSET).state.cooling_efficiency == pytest.approx(
        0.85, abs=1e-3
    )


def test_progress_one_reproduces_the_configured_maximum_effect() -> None:
    fleet = PlantAlphaFleet.create(run_id="fault-effect-test")
    apply_fault_effect(
        fleet, _fault_config(DatasetScenario.COOLING_DEGRADATION), progress=1.0
    )
    fleet.machine(_TARGET_ASSET).tick(_FORCE_CONVERGENCE_DT)

    assert fleet.machine(_TARGET_ASSET).state.cooling_efficiency == pytest.approx(
        0.55, abs=1e-3
    )


def test_only_target_asset_is_affected() -> None:
    fleet = PlantAlphaFleet.create(run_id="fault-effect-test")
    apply_fault_effect(
        fleet, _fault_config(DatasetScenario.COOLING_DEGRADATION), progress=1.0
    )
    fleet.machine(_OTHER_ASSET).tick(_FORCE_CONVERGENCE_DT)

    assert fleet.machine(_OTHER_ASSET).state.cooling_efficiency == pytest.approx(
        0.87, abs=1e-3
    )  # fuel-cell-stack-02's own healthy baseline, untouched
