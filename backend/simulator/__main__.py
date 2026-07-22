"""Run the fuel cell simulator against a live ODIS platform."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import UTC, datetime

from backend.simulator.config import SimulatorSettings
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.publishers.composite_publisher import (
    CompositeObservationPublisher,
)
from backend.simulator.publishers.http_publisher import HttpObservationPublisher
from backend.simulator.publishers.kafka_publisher import KafkaObservationPublisher
from backend.simulator.publishers.mqtt_publisher import MqttObservationPublisher
from backend.simulator.scenario_registry import build_scenario
from backend.simulator.scenario_script import cadence_for_script
from backend.simulator.scenarios.base import Scenario
from backend.simulator.telemetry import (
    core_observations_from_machine,
    derived_observations_from_state,
)

_Publisher = (
    HttpObservationPublisher
    | MqttObservationPublisher
    | KafkaObservationPublisher
    | CompositeObservationPublisher
)

# Transports whose publish loop must use `_run_kafka_loop`'s single-tick,
# single-timestamp snapshot semantics — required whenever Kafka is one of
# the sinks, since `TelemetrySample.from_observations` (fault inference)
# needs every measurement in a sample to share one exact timestamp.
_KAFKA_LOOP_TRANSPORTS = ("kafka", "kafka+http")

_DEFAULT_CORE_INTERVAL = SimulatorSettings.model_fields[
    "core_publish_interval_seconds"
].default
_DEFAULT_DERIVED_INTERVAL = SimulatorSettings.model_fields[
    "derived_publish_interval_seconds"
].default
_DEFAULT_SIM_DT = SimulatorSettings.model_fields["sim_dt_seconds"].default
_TRAINED_INFERENCE_CADENCE_SECONDS = SimulatorSettings.model_fields[
    "kafka_sample_interval_seconds"
].default


def _apply_script_cadence(
    settings: SimulatorSettings,
    scenario_name: str,
) -> SimulatorSettings:
    """Let a scripted scenario set its own cadence unless the operator
    explicitly overrode one of the cadence settings away from the platform
    default, in which case that explicit choice wins.
    """
    cadence = cadence_for_script(scenario_name)
    if cadence is None:
        return settings

    updates: dict[str, float] = {}
    if settings.core_publish_interval_seconds == _DEFAULT_CORE_INTERVAL:
        updates["core_publish_interval_seconds"] = (
            cadence.core_publish_interval_seconds
        )
    if settings.derived_publish_interval_seconds == _DEFAULT_DERIVED_INTERVAL:
        updates["derived_publish_interval_seconds"] = (
            cadence.derived_publish_interval_seconds
        )
    if settings.sim_dt_seconds == _DEFAULT_SIM_DT:
        updates["sim_dt_seconds"] = cadence.sim_dt_seconds

    return settings.model_copy(update=updates) if updates else settings


def _build_publisher(settings: SimulatorSettings) -> _Publisher:
    if settings.transport.lower() == "http":
        return HttpObservationPublisher(settings.api_base_url)
    if settings.transport.lower() == "mqtt":
        return MqttObservationPublisher(
            broker_url=settings.mqtt_broker_url,
            site_id=settings.site_id,
            topic_prefix=settings.mqtt_topic_prefix,
            qos=settings.mqtt_qos,
        )
    if settings.transport.lower() == "kafka":
        return KafkaObservationPublisher(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.kafka_topic,
        )
    if settings.transport.lower() == "kafka+http":
        # Single-source provenance (PR178 correction): one tick's
        # already-constructed observations are fanned out to both sinks
        # by `CompositeObservationPublisher`, never recomputed per
        # transport. Kafka first, then HTTP — a fixed, documented order,
        # not a distributed transaction (see composite_publisher.py).
        return CompositeObservationPublisher(
            KafkaObservationPublisher(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                topic=settings.kafka_topic,
            ),
            HttpObservationPublisher(settings.api_base_url),
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


def _publish_kafka_snapshot(
    fleet: PlantAlphaFleet,
    scenario: Scenario,
    publisher: _Publisher,
    interval: float,
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> datetime:
    """One synchronized tick+publish iteration for the Kafka transport
    (PR177 correction) — the unit of work `_run_kafka_loop` repeats.

    `TelemetrySample.from_observations` requires every measurement in a
    sample to share one *exact* timestamp — the dual-cadence core/derived
    loop (`_run_dual_cadence_loop`) cannot satisfy that, since it calls
    `datetime.now(UTC)` separately for core and derived, on independent
    cadences. This function instead ticks the fleet once and builds
    *both* core and derived observations from that one resulting machine
    state and one captured timestamp, so a complete sample is always
    assembleable downstream. See `docs/kafka-fault-inference-worker.md`'s
    "Live simulator synchronization" section.

    `scenario.tick(fleet, interval)` advances *simulated* time by exactly
    `interval` — the quantity the promoted runtime's features actually
    depend on (`FaultInferenceSession`'s `elapsed_sim_seconds` clock
    advances by sample *count*, never by real timestamp gaps; see that
    module's docstring). `now_fn` is injectable so tests can drive many
    iterations deterministically without real sleeps or real-clock
    timestamp jitter.

    Returns the timestamp used, for logging/testing.
    """
    scenario.tick(fleet, interval)
    timestamp = now_fn()

    for asset_id in fleet.asset_ids:
        machine = fleet.machine(asset_id)
        context = fleet.telemetry_context(asset_id)
        core_observations = core_observations_from_machine(
            machine,
            timestamp=timestamp,
            context=context,
        )
        derived_observations = derived_observations_from_state(
            machine.state,
            asset_id=asset_id,
            timestamp=timestamp,
            context=context,
        )
        publisher.publish(core_observations + derived_observations)

    return timestamp


def _run_kafka_loop(
    fleet: PlantAlphaFleet,
    scenario: Scenario,
    publisher: _Publisher,
    settings: SimulatorSettings,
) -> None:
    """Kafka transport's dedicated publish loop — repeatedly calls
    `_publish_kafka_snapshot` with `kafka_sample_interval_seconds` as the
    *simulated* `dt_seconds` per tick (the quantity feature correctness
    depends on), independent of `sim_dt_seconds`/`core_publish_interval_
    seconds`/`derived_publish_interval_seconds`, which remain HTTP/MQTT-
    only. Real (wall-clock) pacing between publishes is the separate
    `kafka_publish_interval_seconds` — decoupled deliberately, since
    `FaultInferenceSession.ingest` derives its feature-timing clock from
    sample count and `dt_seconds`, never from wall-clock gaps (see that
    module's docstring): a faster wall-clock pace only changes how
    quickly a fixed number of correctly-spaced samples are produced in
    real time, never what the model computes from them.
    """
    sim_interval = settings.kafka_sample_interval_seconds
    publish_interval = settings.kafka_publish_interval_seconds
    if sim_interval != _TRAINED_INFERENCE_CADENCE_SECONDS:
        print(
            f"WARNING: kafka_sample_interval_seconds={sim_interval}s differs "
            "from the promoted runtime's trained cadence "
            f"({_TRAINED_INFERENCE_CADENCE_SECONDS}s) — features computed "
            "from this stream will not match the model's trained window "
            "semantics."
        )

    print(
        f"Kafka transport: one synchronized snapshot every "
        f"{publish_interval}s wall-clock (logical cadence {sim_interval}s)"
    )

    try:
        while True:
            iteration_start = time.monotonic()
            _publish_kafka_snapshot(fleet, scenario, publisher, sim_interval)
            elapsed = time.monotonic() - iteration_start
            time.sleep(max(0.0, publish_interval - elapsed))
    except KeyboardInterrupt:
        print("Simulator stopped.")


def _run_dual_cadence_loop(
    fleet: PlantAlphaFleet,
    scenario: Scenario,
    publisher: _Publisher,
    settings: SimulatorSettings,
    *,
    core_interval: float,
    derived_interval: float,
) -> None:
    """HTTP/MQTT transports' existing independent core/derived cadence
    loop — unchanged behavior from before this PR's Kafka correction."""
    next_core_at = time.monotonic()
    next_derived_at = time.monotonic()

    try:
        while True:
            now = time.monotonic()

            if now < next_core_at and now < next_derived_at:
                time.sleep(
                    _seconds_until_next_deadline(now, next_core_at, next_derived_at)
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
    settings = _apply_script_cadence(settings, scenario_name)
    scenario = build_scenario(scenario_name)
    run_id = settings.resolved_run_id()
    fleet = PlantAlphaFleet.create(
        run_id=run_id,
        asset_ids=settings.resolved_asset_ids(),
    )

    core_interval = settings.resolved_core_publish_interval_seconds()
    derived_interval = settings.derived_publish_interval_seconds

    if settings.transport.lower() in _KAFKA_LOOP_TRANSPORTS:
        print(
            f"Starting demo plant run_id={run_id} scenario={scenario_name} "
            f"transport={settings.transport} site={settings.site_id} "
            f"assets={','.join(fleet.asset_ids)} "
            f"kafka_sample_interval={settings.kafka_sample_interval_seconds}s"
        )
    else:
        print(
            f"Starting demo plant run_id={run_id} scenario={scenario_name} "
            f"transport={settings.transport} site={settings.site_id} "
            f"assets={','.join(fleet.asset_ids)} "
            f"core_interval={core_interval}s derived_interval={derived_interval}s "
            f"sim_dt={settings.sim_dt_seconds}s"
        )

    with _build_publisher(settings) as publisher:
        if settings.transport.lower() in _KAFKA_LOOP_TRANSPORTS:
            _run_kafka_loop(fleet, scenario, publisher, settings)
        else:
            _run_dual_cadence_loop(
                fleet,
                scenario,
                publisher,
                settings,
                core_interval=core_interval,
                derived_interval=derived_interval,
            )


if __name__ == "__main__":
    main()
