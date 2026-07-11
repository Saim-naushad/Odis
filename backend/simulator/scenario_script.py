"""Timed scenario scripts for presentation and realistic demos."""

from __future__ import annotations

from dataclasses import dataclass

from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.scenarios.base import Scenario
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import (
    HydrogenSupplyIssueScenario,
)
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.scenarios.recovery import RecoveryScenario
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario


@dataclass(frozen=True)
class ScenarioPhase:
    name: str
    duration_sim_seconds: float
    target_asset_id: str = "fuel-cell-stack-01"


PRESENTATION_PHASES: tuple[ScenarioPhase, ...] = (
    ScenarioPhase("normal_operation", 6 * 60),
    ScenarioPhase("cooling_degradation", 18 * 60),
    ScenarioPhase("recovery", 12 * 60),
    ScenarioPhase("hydrogen_supply_issue", 12 * 60),
    ScenarioPhase("recovery", 6 * 60),
)

REALISTIC_PHASES: tuple[ScenarioPhase, ...] = (
    ScenarioPhase("normal_operation", 30 * 60),
    ScenarioPhase("cooling_degradation", 45 * 60),
    ScenarioPhase("recovery", 30 * 60),
    ScenarioPhase("hydrogen_supply_issue", 30 * 60),
    ScenarioPhase("recovery", 30 * 60),
    ScenarioPhase("sensor_anomaly", 30 * 60, "fuel-cell-stack-02"),
    ScenarioPhase("recovery", 30 * 60, "fuel-cell-stack-02"),
)


class ScenarioScriptRunner:
    """Advance through scripted scenario phases using simulation time."""

    name: str

    def __init__(self, *, script_name: str, phases: tuple[ScenarioPhase, ...]) -> None:
        self.name = script_name
        self._phases = phases
        self._phase_index = 0
        self._phase_elapsed = 0.0
        self._active = self._build_phase(self._phases[0])

    @property
    def current_phase_name(self) -> str:
        return self._phases[self._phase_index].name

    def _build_phase(self, phase: ScenarioPhase) -> Scenario:
        if phase.name == "normal_operation":
            return NormalOperationScenario()
        if phase.name == "cooling_degradation":
            return CoolingDegradationScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        if phase.name == "hydrogen_supply_issue":
            return HydrogenSupplyIssueScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        if phase.name == "sensor_anomaly":
            return SensorAnomalyScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        if phase.name == "recovery":
            return RecoveryScenario(
                target_asset_id=phase.target_asset_id,
                duration_sim_seconds=phase.duration_sim_seconds,
            )
        msg = f"unsupported scenario phase: {phase.name}"
        raise ValueError(msg)

    def tick(self, fleet: PlantAlphaFleet, dt_seconds: float) -> None:
        self._active.tick(fleet, dt_seconds)
        self._phase_elapsed += dt_seconds
        current = self._phases[self._phase_index]
        if self._phase_elapsed < current.duration_sim_seconds:
            return
        if self._phase_index >= len(self._phases) - 1:
            return
        self._phase_index += 1
        self._phase_elapsed = 0.0
        self._active = self._build_phase(self._phases[self._phase_index])


def build_script_runner(script_name: str) -> ScenarioScriptRunner:
    if script_name == "demo_presentation":
        return ScenarioScriptRunner(
            script_name=script_name,
            phases=PRESENTATION_PHASES,
        )
    if script_name == "demo_realistic":
        return ScenarioScriptRunner(
            script_name=script_name,
            phases=REALISTIC_PHASES,
        )
    msg = f"unsupported scenario script: {script_name}"
    raise ValueError(msg)
