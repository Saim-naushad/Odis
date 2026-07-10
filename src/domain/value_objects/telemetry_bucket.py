"""Telemetry aggregate bucket granularity for operator-facing rollups."""

from __future__ import annotations

from enum import StrEnum


class TelemetryBucket(StrEnum):
    """Supported continuous-aggregate bucket widths."""

    ONE_HOUR = "1h"
    ONE_DAY = "1d"

    @classmethod
    def from_query(cls, value: str) -> TelemetryBucket:
        """Parse an API query value into a bucket granularity."""
        normalized = value.strip().lower()
        for bucket in cls:
            if bucket.value == normalized:
                return bucket
        supported = ", ".join(item.value for item in cls)
        raise ValueError(f"bucket must be one of: {supported}")
