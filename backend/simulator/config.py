"""Simulator configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    """Environment-driven settings for the fuel cell simulator."""

    model_config = SettingsConfigDict(
        env_prefix="SIMULATOR_",
        env_file=".env",
        extra="ignore",
    )

    api_base_url: str = "http://localhost:8000"
    publish_interval_seconds: float = 5.0
    asset_id: str = "fuel-cell-stack-01"
