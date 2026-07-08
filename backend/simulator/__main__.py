"""Run the fuel cell simulator against a live ODIS platform API."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from backend.simulator.config import SimulatorSettings
from backend.simulator.machine import FuelCellMachine
from backend.simulator.publisher import ObservationPublisher
from backend.simulator.scenarios.normal_operation import NormalOperationScenario
from backend.simulator.telemetry import observations_from_machine


def main() -> None:
    settings = SimulatorSettings()
    scenario = NormalOperationScenario(
        machine=FuelCellMachine.default(asset_id=settings.asset_id),
    )

    print(
        f"Starting fuel cell simulator for asset '{settings.asset_id}' "
        f"→ {settings.api_base_url} every {settings.publish_interval_seconds}s"
    )

    with ObservationPublisher(settings.api_base_url) as publisher:
        try:
            while True:
                machine = scenario.tick(settings.publish_interval_seconds)
                observations = observations_from_machine(
                    machine,
                    timestamp=datetime.now(UTC),
                )
                publisher.publish(observations)
                time.sleep(settings.publish_interval_seconds)
        except KeyboardInterrupt:
            print("Simulator stopped.")


if __name__ == "__main__":
    main()
