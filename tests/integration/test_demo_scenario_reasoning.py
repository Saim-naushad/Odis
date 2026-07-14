"""Characterize demo scenarios through the real reasoning pipeline."""

from __future__ import annotations

import statistics
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from backend.simulator.scenarios.cooling_degradation import CoolingDegradationScenario
from backend.simulator.scenarios.hydrogen_supply_issue import (
    HydrogenSupplyIssueScenario,
)
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.scenarios.recovery import RecoveryScenario
from backend.simulator.scenarios.sensor_anomaly import SensorAnomalyScenario
from tests.integration.demo_helpers import TARGET_ASSET_ID, PipelineDriver


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

    baseline_temperatures = driver.telemetry("stack_temperature")

    cooling = CoolingDegradationScenario(duration_sim_seconds=18 * 60.0)
    driver.run(cooling.tick, ticks=24)

    degraded = driver.operational_state()
    degraded_twin = driver.digital_twin()
    degraded_timeline = set(driver.timeline_event_types())
    machine = driver.machine_state()
    degraded_temperatures = driver.telemetry("stack_temperature")

    assert machine.cooling_efficiency < 0.75

    # The physics-level fault is real and shows up directly in raw telemetry
    # - the signal an operator would actually inspect. It does not reliably
    # move the reasoning pipeline's *classified* health/risk state within
    # this window: Plant Alpha's reasoning session has a single fixed
    # primary measurement (`current` - see VariationDetector's own comment
    # on primary_measurement_observations), and cooling_degradation is a
    # temperature-only fault. This is the already-documented "single primary
    # measurement per run" limitation (docs/architecture.md), not something
    # this test should rely on classifier noise to paper over.
    #
    # Compare mean-of-window rather than single points: normal load cycling
    # oscillates enough that any two individual samples can land on either
    # side of the mean, but the fault visibly shifts the oscillation's
    # center.
    baseline_mean = statistics.fmean(
        sample["value"] for sample in baseline_temperatures
    )
    degraded_recent_mean = statistics.fmean(
        sample["value"] for sample in degraded_temperatures[-10:]
    )
    assert degraded_recent_mean > baseline_mean

    assert degraded_twin["recommendation"]["category"] in {
        "mitigate",
        "investigate",
        "monitor",
    }
    if degraded["health_status"] in {"CRITICAL", "WARNING"}:
        assert degraded_twin["notification"] is not None

    assert "reasoning_completed" in degraded_timeline

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

    driver.run(
        HydrogenSupplyIssueScenario(duration_sim_seconds=12 * 60.0).tick, ticks=20
    )
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
    anomaly_driver.run(
        SensorAnomalyScenario(duration_sim_seconds=12 * 60.0).tick, ticks=20
    )
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
        item["title"]
        for item in baseline_run["decision_plan"]["alternative_hypotheses"]
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

