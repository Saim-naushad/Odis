"""Run the fuel cell simulator against a live ODIS platform."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime

from backend.simulator.config import SimulatorSettings
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.publishers.http_publisher import HttpObservationPublisher
from backend.simulator.publishers.mqtt_publisher import MqttObservationPublisher
from backend.simulator.scenario_registry import build_scenario
from backend.simulator.telemetry import (
    core_observations_from_machine,
    derived_observations_from_state,
)


def _build_publisher(settings: SimulatorSettings):
    if settings.transport.lower() == "http":
        return HttpObservationPublisher(settings.api_base_url)
    if settings.transport.lower() == "mqtt":
        return MqttObservationPublisher(
            broker_url=settings.mqtt_broker_url,
            site_id=settings.site_id,
            topic_prefix=settings.mqtt_topic_prefix,
            qos=settings.mqtt_qos,
        )
    msg = f"unsupported transport: {settings.transport}"
    raise ValueError(msg)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--scenario-script", default=None)
    parser.add_argument("--transport", default=None)
    return parser.parse_args()


def _advance_publish_deadline(
    deadline: float,
    interval: float,
    now: float,
) -> float:
    """Move a publish deadline forward, preserving cadence after overruns."""
    if now < deadline:
        return deadline
    missed_slots = int((now - deadline) // interval) + 1
    return deadline + missed_slots * interval


def _seconds_until_next_deadline(
    now: float,
    next_core_at: float,
    next_derived_at: float,
) -> float:
    """Return positive sleep duration until the earliest due publish."""
    return min(next_core_at, next_derived_at) - now


def main() -> None:
    args = _parse_args()
    settings = SimulatorSettings()
    if args.scenario is not None:
        settings = settings.model_copy(update={"scenario": args.scenario})
    if args.scenario_script is not None:
        settings = settings.model_copy(
            update={"scenario_script": args.scenario_script},
        )
    if args.transport is not None:
        settings = settings.model_copy(update={"transport": args.transport})

    scenario_name = settings.scenario_script or settings.scenario
    scenario = build_scenario(scenario_name)
    run_id = settings.resolved_run_id()
    fleet = PlantAlphaFleet.create(
        run_id=run_id,
        asset_ids=settings.resolved_asset_ids(),
    )

    core_interval = settings.resolved_core_publish_interval_seconds()
    derived_interval = settings.derived_publish_interval_seconds

    print(
        f"Starting demo plant run_id={run_id} scenario={scenario_name} "
        f"transport={settings.transport} site={settings.site_id} "
        f"assets={','.join(fleet.asset_ids)} "
        f"core_interval={core_interval}s derived_interval={derived_interval}s "
        f"sim_dt={settings.sim_dt_seconds}s"
    )

    next_core_at = time.monotonic()
    next_derived_at = time.monotonic()

    with _build_publisher(settings) as publisher:
        try:
            while True:
                now = time.monotonic()

                if now < next_core_at and now < next_derived_at:
                    time.sleep(
                        _seconds_until_next_deadline(
                            now, next_core_at, next_derived_at
                        )
                    )
                    continue

                core_due = now >= next_core_at
                derived_due = now >= next_derived_at

                if core_due:
                    scenario.tick(fleet, settings.sim_dt_seconds)
                    timestamp = datetime.now(UTC)

                    for asset_id in fleet.asset_ids:
                        machine = fleet.machine(asset_id)
                        core_observations = core_observations_from_machine(
                            machine,
                            timestamp=timestamp,
                            context=fleet.telemetry_context(asset_id),
                        )
                        publisher.publish(core_observations)

                if derived_due:
                    timestamp = datetime.now(UTC)
                    for asset_id in fleet.asset_ids:
                        machine = fleet.machine(asset_id)
                        derived_observations = derived_observations_from_state(
                            machine.state,
                            asset_id=asset_id,
                            timestamp=timestamp,
                            context=fleet.telemetry_context(asset_id),
                        )
                        publisher.publish(derived_observations)

                finished = time.monotonic()
                if core_due:
                    next_core_at = _advance_publish_deadline(
                        next_core_at,
                        core_interval,
                        finished,
                    )
                if derived_due:
                    next_derived_at = _advance_publish_deadline(
                        next_derived_at,
                        derived_interval,
                        finished,
                    )
        except KeyboardInterrupt:
            print("Simulator stopped.")


if __name__ == "__main__":
    main()
