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

    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    mqtt_broker_url: str | None = Field(
        default=None,
        validation_alias="MQTT_BROKER_URL",
    )
    kafka_bootstrap_servers: str | None = Field(
        default=None,
        validation_alias="KAFKA_BOOTSTRAP_SERVERS",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
