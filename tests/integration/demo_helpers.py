"""Shared helpers for demo scenario characterization tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.simulator.machine import FuelCellMachineState
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.telemetry import (
    core_observations_from_machine,
    observation_to_payload,
)
from tests.backend.helpers import drain_reasoning_jobs

TARGET_ASSET_ID = "fuel-cell-stack-01"
_BASE_TIMESTAMP = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class PipelineDriver:
    """Publish scenario telemetry through the real API and worker.

    Keeps a monotonically increasing tick counter so observation timestamps
    stay strictly ordered across scenario phases.
    """

    def __init__(
        self,
        api_client: TestClient,
        *,
        run_id: str = "characterization",
        asset_id: str = TARGET_ASSET_ID,
    ) -> None:
        self.api_client = api_client
        self.asset_id = asset_id
        self.fleet = PlantAlphaFleet.create(run_id=run_id, asset_ids=(asset_id,))
        self._tick_index = 0

    def run(
        self,
        tick_fn: Callable[[PlantAlphaFleet, float], None],
        *,
        ticks: int,
        dt_seconds: float = 45.0,
    ) -> None:
        for _ in range(ticks):
            tick_fn(self.fleet, dt_seconds)
            timestamp = _BASE_TIMESTAMP + timedelta(seconds=15 * self._tick_index)
            self._tick_index += 1
            observations = core_observations_from_machine(
                self.fleet.machine(self.asset_id),
                timestamp=timestamp,
                context=self.fleet.telemetry_context(self.asset_id),
            )
            for observation in observations:
                response = self.api_client.post(
                    "/observations",
                    json=observation_to_payload(observation),
                )
                response.raise_for_status()
        drain_reasoning_jobs(self.api_client)

    def digital_twin(self) -> dict[str, Any]:
        response = self.api_client.get(
            f"/monitoring/assets/{self.asset_id}/digital-twin",
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def operational_state(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.digital_twin()["operational_state"])

    def timeline_event_types(self) -> list[str]:
        response = self.api_client.get(
            f"/monitoring/assets/{self.asset_id}/timeline",
        )
        response.raise_for_status()
        return [event["event_type"] for event in response.json()]

    def machine_state(self) -> FuelCellMachineState:
        return self.fleet.machine(self.asset_id).state

    def telemetry(self, measurement_type: str) -> list[dict[str, Any]]:
        response = self.api_client.get(
            f"/monitoring/assets/{self.asset_id}/telemetry",
            params={"measurement_type": measurement_type},
        )
        response.raise_for_status()
        payload = response.json()
        return cast(list[dict[str, Any]], payload[0]["samples"] if payload else [])

    def run_details(self) -> dict[str, Any]:
        twin = self.digital_twin()
        response = self.api_client.get(
            f"/monitoring/runs/{twin['latest_reasoning_run_id']}",
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
