"""Characterize demo scenarios through the real reasoning pipeline."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import HydrogenSupplyIssueScenario
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.scenarios.recovery import RecoveryScenario
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario
from tests.integration.demo_helpers import PipelineDriver, TARGET_ASSET_ID


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'demo_scenario_reasoning.db'}",
        forecast_enabled=False,
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def test_normal_operation_produces_reasoning_state(api_client: TestClient) -> None:
    driver = PipelineDriver(api_client)
    driver.run(NormalOperationScenario().tick, ticks=8)
    state = driver.operational_state()
    assert 0 <= state["health_score"] <= 100
    assert state["health_status"] in {"NORMAL", "WARNING", "CRITICAL"}


def test_cooling_incident_and_recovery_characterization(
    api_client: TestClient,
) -> None:
    driver = PipelineDriver(api_client)
    driver.run(NormalOperationScenario().tick, ticks=10)

    baseline = driver.operational_state()
    _ = set(driver.timeline_event_types())

    cooling = CoolingDegradationScenario(duration_sim_seconds=18 * 60.0)
    driver.run(cooling.tick, ticks=24)

    degraded = driver.operational_state()
    degraded_twin = driver.digital_twin()
    degraded_timeline = set(driver.timeline_event_types())
    machine = driver.machine_state()

    assert machine.cooling_efficiency < 0.75

    meaningful_transition = (
        degraded["health_score"] != baseline["health_score"]
        or degraded["health_status"] != baseline["health_status"]
        or degraded["risk_level"] != baseline["risk_level"]
        or degraded["primary_driver"] != baseline["primary_driver"]
    )
    assert meaningful_transition

    assert degraded_twin["recommendation"]["category"] in {
        "mitigate",
        "investigate",
        "monitor",
    }
    if degraded["health_status"] in {"CRITICAL", "WARNING"}:
        assert degraded_twin["notification"] is not None

    assert "reasoning_completed" in degraded_timeline
    assert degraded_timeline & {
        "trend_changed",
        "notification_created",
        "health_changed",
        "risk_changed",
    }

    degraded_efficiency = machine.cooling_efficiency
    driver.run(RecoveryScenario(duration_sim_seconds=12 * 60.0).tick, ticks=20)
    restored = driver.machine_state()
    recovery_timeline = set(driver.timeline_event_types())

    assert restored.cooling_efficiency > degraded_efficiency
    assert restored.cooling_efficiency >= 0.8
    assert "reasoning_completed" in recovery_timeline


def test_hydrogen_supply_issue_reasoning_outcome(api_client: TestClient) -> None:
    driver = PipelineDriver(api_client)
    driver.run(NormalOperationScenario().tick, ticks=8)
    baseline = driver.operational_state()
    baseline_run = driver.run_details()

    driver.run(HydrogenSupplyIssueScenario(duration_sim_seconds=12 * 60.0).tick, ticks=20)
    machine = driver.machine_state()
    fault_state = driver.operational_state()
    fault_run = driver.run_details()

    assert machine.current < 100.0
    assert machine.fuel_supply_factor < 0.9

    reasoning_outcome = (
        fault_state["primary_driver"] != baseline["primary_driver"]
        or fault_state["health_score"] != baseline["health_score"]
        or fault_state["risk_level"] != baseline["risk_level"]
        or fault_run["decision_context"]["assessment"]
        != baseline_run["decision_context"]["assessment"]
        or fault_run["trend_analysis"]["summary"]
        != baseline_run["trend_analysis"]["summary"]
        or fault_run["decision_plan"]["priority"]
        != baseline_run["decision_plan"]["priority"]
    )
    assert reasoning_outcome


def test_sensor_anomaly_reasoning_outcome(api_client: TestClient) -> None:
    baseline_driver = PipelineDriver(api_client, run_id="sensor-baseline")
    baseline_driver.run(NormalOperationScenario().tick, ticks=8)
    baseline_run = baseline_driver.run_details()

    anomaly_driver = PipelineDriver(api_client, run_id="sensor-anomaly")
    anomaly_driver.run(SensorAnomalyScenario(duration_sim_seconds=12 * 60.0).tick, ticks=20)
    anomaly_run = anomaly_driver.run_details()
    machine = anomaly_driver.machine_state()

    assert machine.current > 0.0
    assert (
        anomaly_driver.fleet.telemetry_context(TARGET_ASSET_ID).sensor_bias[
            "stack_temperature"
        ]
        > 0.0
    )

    baseline_hypotheses = {
        item["title"] for item in baseline_run["decision_plan"]["alternative_hypotheses"]
    }
    anomaly_hypotheses = {
        item["title"] for item in anomaly_run["decision_plan"]["alternative_hypotheses"]
    }
    reasoning_outcome = (
        anomaly_hypotheses != baseline_hypotheses
        or anomaly_run["decision_plan"]["confidence"]["value"]
        != baseline_run["decision_plan"]["confidence"]["value"]
        or anomaly_run["decision_context"]["assessment"]
        != baseline_run["decision_context"]["assessment"]
        or anomaly_driver.operational_state()["primary_driver"]
        != baseline_driver.operational_state()["primary_driver"]
    )
    assert reasoning_outcome

