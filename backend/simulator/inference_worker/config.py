"""Streaming worker configuration (PR177 spec section 13).

Mirrors `backend.mqtt_bridge.config.MqttBridgeSettings`'s shape (a small,
dedicated `pydantic_settings.BaseSettings` subclass per worker, rather
than growing the platform's shared `Settings`) — this worker is deployed
and run independently of `backend/app`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INPUT_TOPIC = "odis.telemetry.observations.v1"
DEFAULT_RESULTS_TOPIC = "odis.fault.inference-results.v1"
DEFAULT_ALERT_TRANSITIONS_TOPIC = "odis.fault.alert-transitions.v1"
DEFAULT_DATA_QUALITY_TOPIC = "odis.fault.telemetry-data-quality.v1"
DEFAULT_CONSUMER_GROUP_ID = "odis-fault-inference-worker"


class InferenceWorkerSettings(BaseSettings):
    """Environment-driven settings for the Kafka fault-inference worker."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bundle_dir: Path = Field(
        default=Path("artifacts/models/plant_alpha_fault_v1"),
        validation_alias="FAULT_INFERENCE_BUNDLE_DIR",
    )
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS",
    )
    input_topic: str = Field(
        default=DEFAULT_INPUT_TOPIC,
        validation_alias="FAULT_INFERENCE_INPUT_TOPIC",
    )
    results_topic: str = Field(
        default=DEFAULT_RESULTS_TOPIC,
        validation_alias="FAULT_INFERENCE_RESULTS_TOPIC",
    )
    alert_transitions_topic: str = Field(
        default=DEFAULT_ALERT_TRANSITIONS_TOPIC,
        validation_alias="FAULT_INFERENCE_ALERT_TRANSITIONS_TOPIC",
    )
    data_quality_topic: str = Field(
        default=DEFAULT_DATA_QUALITY_TOPIC,
        validation_alias="FAULT_INFERENCE_DATA_QUALITY_TOPIC",
    )
    consumer_group_id: str = Field(
        default=DEFAULT_CONSUMER_GROUP_ID,
        validation_alias="FAULT_INFERENCE_CONSUMER_GROUP_ID",
    )
    assembly_timeout_seconds: float = Field(
        default=30.0,
        validation_alias="FAULT_INFERENCE_ASSEMBLY_TIMEOUT_SECONDS",
    )
    max_buffered_timestamps_per_asset: int = Field(
        default=8,
        validation_alias="FAULT_INFERENCE_MAX_BUFFERED_TIMESTAMPS_PER_ASSET",
    )
    max_tracked_assets: int = Field(
        default=64,
        validation_alias="FAULT_INFERENCE_MAX_TRACKED_ASSETS",
    )
    poll_timeout_ms: int = Field(
        default=1000,
        validation_alias="FAULT_INFERENCE_POLL_TIMEOUT_MS",
    )
    publish_max_retries: int = Field(
        default=3,
        validation_alias="FAULT_INFERENCE_PUBLISH_MAX_RETRIES",
    )
    publish_retry_backoff_seconds: float = Field(
        default=0.5,
        validation_alias="FAULT_INFERENCE_PUBLISH_RETRY_BACKOFF_SECONDS",
    )
    metrics_port: int = Field(
        default=9108,
        validation_alias="FAULT_INFERENCE_METRICS_PORT",
    )

    @field_validator(
        "assembly_timeout_seconds",
        "publish_retry_backoff_seconds",
        mode="after",
    )
    @classmethod
    def _positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator(
        "max_buffered_timestamps_per_asset",
        "max_tracked_assets",
        "poll_timeout_ms",
        "metrics_port",
        mode="after",
    )
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("publish_max_retries", mode="after")
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be zero or greater")
        return value

    @field_validator(
        "input_topic",
        "results_topic",
        "alert_transitions_topic",
        "data_quality_topic",
        "consumer_group_id",
        "kafka_bootstrap_servers",
        mode="after",
    )
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value
