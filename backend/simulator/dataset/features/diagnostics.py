"""Reporting-only diagnostics that don't feed the feature matrix itself.

`efficiency_clamp_stats` re-derives, for *this* generation run, the same
kind of clamp evidence the PR166 audit used to justify excluding
`efficiency` from `config.DEFAULT_MEASUREMENTS` — restricted to the actual
feature-eligible rows (post warm-up-drop) so the manifest's evidence
matches exactly what a feature consumer would see, not the full dataset.
"""

from __future__ import annotations

import statistics
from typing import Any

import pyarrow as pa

_CLAMP_VALUE = 100.0
_CLAMP_TOLERANCE = 1e-4


def efficiency_clamp_stats(
    telemetry_rows: list[dict[str, Any]], features_table: pa.Table
) -> dict[str, Any]:
    eligible_keys = set(
        zip(
            features_table.column("simulation_run_id").to_pylist(),
            features_table.column("asset_id").to_pylist(),
            features_table.column("elapsed_sim_seconds").to_pylist(),
            strict=True,
        )
    )
    values = [
        row["value"]
        for row in telemetry_rows
        if row["measurement_type"] == "efficiency"
        and (row["simulation_run_id"], row["asset_id"], row["elapsed_sim_seconds"])
        in eligible_keys
    ]
    if not values:
        return {"eligible_sample_count": 0}

    clamped = sum(1 for v in values if v >= _CLAMP_VALUE - _CLAMP_TOLERANCE)
    return {
        "eligible_sample_count": len(values),
        "clamped_at_100_percent": clamped,
        "clamped_percentage": round(100.0 * clamped / len(values), 3),
        "variance": statistics.pvariance(values),
        "stdev": statistics.pstdev(values),
        "unique_value_count": len({round(v, 4) for v in values}),
        "min": min(values),
        "max": max(values),
    }
