"""SQLAlchemy-backed telemetry aggregate repository."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from domain.repositories.telemetry_aggregate_repository import (
    TelemetryAggregateRepository,
)
from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_bucket import TelemetryBucket

_VIEW_BY_BUCKET = {
    TelemetryBucket.ONE_HOUR: "observations_hourly",
    TelemetryBucket.ONE_DAY: "observations_daily",
}


class SqlAlchemyTelemetryAggregateRepository(
    SqlAlchemyRepository,
    TelemetryAggregateRepository,
):
    """Read pre-computed rollups from TimescaleDB continuous aggregates."""

    def list_by_asset(
        self,
        asset_id: str,
        *,
        bucket: TelemetryBucket,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
    ) -> list[TelemetryAggregatePoint]:
        view_name = _VIEW_BY_BUCKET[bucket]
        clauses = ["asset_id = :asset_id"]
        params: dict[str, object] = {"asset_id": asset_id}

        if start is not None:
            clauses.append("bucket >= :start")
            params["start"] = start
        if end is not None:
            clauses.append("bucket <= :end")
            params["end"] = end
        if measurement_type is not None:
            clauses.append("measurement_type_name = :measurement_type")
            params["measurement_type"] = measurement_type

        where_sql = " AND ".join(clauses)
        statement = sa.text(
            f"""
            SELECT
                bucket,
                measurement_type_name,
                avg_value,
                min_value,
                max_value,
                sample_count,
                unit
            FROM {view_name}
            WHERE {where_sql}
            ORDER BY bucket ASC, measurement_type_name ASC
            """
        )

        rows = self._session.execute(statement, params).mappings().all()
        return [
            TelemetryAggregatePoint(
                bucket=row["bucket"],
                measurement_type=row["measurement_type_name"],
                avg_value=float(row["avg_value"]),
                min_value=float(row["min_value"]),
                max_value=float(row["max_value"]),
                sample_count=int(row["sample_count"]),
                unit=row["unit"],
            )
            for row in rows
        ]
