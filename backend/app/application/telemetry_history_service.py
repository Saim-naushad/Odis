"""Application service for historical telemetry retrieval."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from domain.entities.observation import Observation
from domain.repositories.observation_repository import ObservationRepository
from domain.value_objects.telemetry_series import TelemetrySample, TelemetrySeries

DEFAULT_TELEMETRY_LIMIT = 1000
MAX_TELEMETRY_LIMIT = 10_000


class TelemetryHistoryService:
    """Assemble immutable telemetry series from persisted observations.

    This is the single place historical telemetry is retrieved, filtered, and
    grouped for operator-facing APIs.
    """

    def __init__(self, *, observation_repository: ObservationRepository) -> None:
        self._observation_repository = observation_repository

    def asset_exists(self, asset_id: str) -> bool:
        """Return whether any observations exist for the asset."""
        return bool(self._observation_repository.list_by_asset(asset_id))

    def get_history(
        self,
        asset_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
        limit: int = DEFAULT_TELEMETRY_LIMIT,
    ) -> list[TelemetrySeries]:
        """Return chronological telemetry series within an optional window."""
        observations = self._observation_repository.list_by_asset_in_time_range(
            asset_id,
            start=start,
            end=end,
            measurement_type=measurement_type,
            limit=limit,
            newest_first=False,
        )
        return self._build_series(asset_id, observations)

    def get_latest(
        self,
        asset_id: str,
        *,
        measurement_type: str | None = None,
        limit: int = 1,
    ) -> list[TelemetrySeries]:
        """Return the newest samples grouped by measurement type."""
        if measurement_type is not None:
            observations = self._observation_repository.list_by_asset_in_time_range(
                asset_id,
                measurement_type=measurement_type,
                limit=limit,
                newest_first=True,
            )
            return self._build_series(asset_id, observations)

        all_observations = self._observation_repository.list_by_asset_in_time_range(
            asset_id,
            newest_first=True,
        )
        grouped: dict[str, list[Observation]] = defaultdict(list)
        for observation in all_observations:
            metric = observation.measurement_type.name
            if len(grouped[metric]) < limit:
                grouped[metric].append(observation)

        series: list[TelemetrySeries] = []
        for metric in sorted(grouped):
            observations = grouped[metric]
            observations.sort(key=lambda item: (item.timestamp, item.id))
            series.extend(self._build_series(asset_id, observations))
        return series

    def _build_series(
        self,
        asset_id: str,
        observations: list[Observation],
    ) -> list[TelemetrySeries]:
        grouped: dict[str, list[Observation]] = defaultdict(list)
        for observation in observations:
            grouped[observation.measurement_type.name].append(observation)

        series: list[TelemetrySeries] = []
        for measurement_type in sorted(grouped):
            metric_observations = grouped[measurement_type]
            metric_observations.sort(key=lambda item: (item.timestamp, item.id))
            unit = metric_observations[-1].unit
            samples = tuple(
                TelemetrySample(timestamp=item.timestamp, value=item.value)
                for item in metric_observations
            )
            series.append(
                TelemetrySeries(
                    asset_id=asset_id,
                    measurement_type=measurement_type,
                    unit=unit,
                    samples=samples,
                )
            )
        return series
