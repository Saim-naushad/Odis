"""MQTT ingestion bridge configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MqttBridgeSettings(BaseSettings):
    """Environment-driven settings for the MQTT ingestion bridge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    broker_url: str | None = Field(default=None, validation_alias="MQTT_BROKER_URL")
    api_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="MQTT_API_BASE_URL",
    )
    topic_prefix: str = Field(default="odis/v1", validation_alias="MQTT_TOPIC_PREFIX")
    subscribe_pattern: str = Field(
        default="odis/v1/+/+/telemetry/+",
        validation_alias="MQTT_SUBSCRIBE_PATTERN",
    )
    client_id: str = Field(
        default="odis-mqtt-bridge",
        validation_alias="MQTT_CLIENT_ID",
    )
    qos: int = Field(default=1, validation_alias="MQTT_QOS")
    clean_session: bool = Field(default=False, validation_alias="MQTT_CLEAN_SESSION")
    keepalive_seconds: int = Field(
        default=60,
        validation_alias="MQTT_KEEPALIVE_SECONDS",
    )
    reconnect_delay_min_seconds: int = Field(
        default=1,
        validation_alias="MQTT_RECONNECT_DELAY_MIN_SECONDS",
    )
    reconnect_delay_max_seconds: int = Field(
        default=128,
        validation_alias="MQTT_RECONNECT_DELAY_MAX_SECONDS",
    )
    request_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="MQTT_REQUEST_TIMEOUT_SECONDS",
    )
