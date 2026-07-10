"""Scenario registry for the fuel cell simulator."""

from __future__ import annotations

from backend.simulator.scenario_script import build_script_runner
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import HydrogenSupplyIssueScenario
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.scenarios.recovery import RecoveryScenario
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario


def build_scenario(name: str):
    if name == "normal_operation":
        return NormalOperationScenario()
    if name == "cooling_degradation":
        return CoolingDegradationScenario()
    if name == "hydrogen_supply_issue":
        return HydrogenSupplyIssueScenario()
    if name == "sensor_anomaly":
        return SensorAnomalyScenario()
    if name == "recovery":
        return RecoveryScenario()
    if name in {"demo_presentation", "demo_realistic"}:
        return build_script_runner(name)
    msg = f"unsupported scenario: {name}"
    raise ValueError(msg)
