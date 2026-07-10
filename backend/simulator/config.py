"""Simulator configuration."""

from __future__ import annotations

from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    """Environment-driven settings for the fuel cell simulator."""

    model_config = SettingsConfigDict(
        env_prefix="SIMULATOR_",
        env_file=".env",
        extra="ignore",
    )

    api_base_url: str = "http://localhost:8000"
    mqtt_broker_url: str = "mqtt://localhost:1883"
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
