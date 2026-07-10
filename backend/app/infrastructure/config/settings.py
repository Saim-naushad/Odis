"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the ODIS platform API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "ODIS Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    mqtt_broker_url: str | None = Field(
        default=None,
        validation_alias="MQTT_BROKER_URL",
    )
    kafka_bootstrap_servers: str | None = Field(
        default=None,
        validation_alias="KAFKA_BOOTSTRAP_SERVERS",
    )

    redis_url: str = Field(
        default="redis://redis:6379/0",
        validation_alias="REDIS_URL",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        validation_alias="CACHE_TTL_SECONDS",
    )
    worker_heartbeat_timeout_seconds: int = Field(
        default=30,
        validation_alias="WORKER_HEARTBEAT_TIMEOUT_SECONDS",
    )
    worker_heartbeat_interval_seconds: int = Field(
        default=10,
        validation_alias="WORKER_HEARTBEAT_INTERVAL_SECONDS",
    )
    health_check_timeout_seconds: float = Field(
        default=2.0,
        validation_alias="HEALTH_CHECK_TIMEOUT_SECONDS",
    )

    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_service_name: str | None = Field(
        default=None,
        validation_alias="OTEL_SERVICE_NAME",
    )

    forecast_enabled: bool = Field(
        default=True,
        validation_alias="FORECAST_ENABLED",
    )
    onnx_model_path: str | None = Field(
        default=None,
        validation_alias="ONNX_MODEL_PATH",
    )
    onnx_model_id: str = Field(
        default="persistence_drift_v1",
        validation_alias="ONNX_MODEL_ID",
    )
    forecast_context_length: int = Field(
        default=24,
        validation_alias="FORECAST_CONTEXT_LENGTH",
    )
    forecast_horizon_steps: int = Field(
        default=12,
        validation_alias="FORECAST_HORIZON_STEPS",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
