"""Simulator configuration."""

from __future__ import annotations

from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict

# Mirrors `backend.simulator.dataset.features.config.DT_SECONDS` — the
# promoted runtime's trained sample spacing — duplicated here rather than
# imported because that module's package (`backend.simulator.dataset.
# features`) unconditionally imports its pyarrow-dependent `generate`
# submodule at package-init time, and the live simulator/demo-plant image
# otherwise has no dependency on `pyarrow` at all. A dedicated test
# (`tests/backend/simulator/test_kafka_sample_synchronization.py::
# test_default_kafka_sample_interval_matches_trained_cadence`) asserts
# these two values stay equal.
_TRAINED_INFERENCE_CADENCE_SECONDS = 10.0


class SimulatorSettings(BaseSettings):
    """Environment-driven settings for the fuel cell simulator."""

    model_config = SettingsConfigDict(
        env_prefix="SIMULATOR_",
        env_file=".env",
        extra="ignore",
    )

    api_base_url: str = "http://localhost:8000"
    mqtt_broker_url: str = "mqtt://localhost:1883"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "odis.telemetry.observations.v1"
    kafka_sample_interval_seconds: float = _TRAINED_INFERENCE_CADENCE_SECONDS
    """*Simulated* time advanced (`scenario.tick(fleet, dt_seconds=...)`)
    per Kafka snapshot — the quantity the promoted runtime's window/rate
    features actually depend on. Defaults to the model's trained sample
    spacing; overriding it changes the logical cadence those features
    assume (see `docs/kafka-fault-inference-worker.md`'s "Cadence
    contract"). Deliberately independent of `sim_dt_seconds`/`core_
    publish_interval_seconds`/`derived_publish_interval_seconds`, which
    remain HTTP/MQTT-only and are untouched by this setting."""
    kafka_publish_interval_seconds: float = _TRAINED_INFERENCE_CADENCE_SECONDS
    """*Wall-clock* seconds slept between Kafka snapshot publishes —
    independent of `kafka_sample_interval_seconds` (feature correctness
    does not depend on real elapsed time; only the simulated `dt_seconds`
    per tick matters — see `FaultInferenceSession.ingest`'s own docstring).
    Defaults to matching `kafka_sample_interval_seconds` (a realistic,
    real-time-paced stream); lowering it accelerates scripted demos/smoke
    tests without affecting model correctness — only how quickly a fixed
    number of simulated-cadence samples are produced in real time."""
    transport: str = "mqtt"
    site_id: str = "plant-alpha"
    asset_ids: str = (
        "fuel-cell-stack-01,fuel-cell-stack-02,"
        "fuel-cell-stack-03,fuel-cell-stack-04"
    )
    scenario: str = "normal_operation"
    scenario_script: str = ""
    run_id: str = ""
    core_publish_interval_seconds: float = 15.0
    derived_publish_interval_seconds: float = 60.0
    sim_dt_seconds: float = 45.0
    mqtt_qos: int = 1
    mqtt_topic_prefix: str = "odis/v1"

    # Backward-compatible aliases
    publish_interval_seconds: float = 15.0
    asset_id: str = "fuel-cell-stack-01"

    def resolved_asset_ids(self) -> tuple[str, ...]:
        if self.asset_ids.strip():
            return tuple(
                asset_id.strip()
                for asset_id in self.asset_ids.split(",")
                if asset_id.strip()
            )
        return (self.asset_id,)

    def resolved_core_publish_interval_seconds(self) -> float:
        return self.core_publish_interval_seconds or self.publish_interval_seconds

    def resolved_run_id(self) -> str:
        return self.run_id or uuid4().hex[:12]
