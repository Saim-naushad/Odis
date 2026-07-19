"""Fixed feature-pipeline policy (PR167).

Every constant here is deliberately fixed, not user-configurable via CLI
flags, for this first baseline release — the PR166 audit's findings
(cooling degradation's weak coupling, hydrogen's severity-scaled voltage
response, sensor_anomaly's temperature-only signature, no single threshold
above 0.80 balanced accuracy) motivate a small, high-value feature set
rather than an exhaustive one. Feature order is entirely determined by the
tuple order below, so changing these tuples changes the schema — do not
reorder without bumping `FEATURE_SCHEMA_VERSION`.

`efficiency` is deliberately excluded from `DEFAULT_MEASUREMENTS`: the
PR166 audit found it clamped at its 100% ceiling for the large majority of
samples (re-verified for this PR: 89.1% of feature-eligible rows are
exactly 100.0). It remains in `telemetry.parquet` — this module never
touches dataset generation — and is intentionally still a valid
`measurement_type` value, so nothing prevents a future PR from adding it
back if a use case needs it.
"""

from __future__ import annotations

FEATURE_SCHEMA_VERSION = "1.0"

DT_SECONDS = 10.0

DEFAULT_MEASUREMENTS: tuple[str, ...] = (
    "stack_temperature",
    "stack_pressure",
    "current",
    "voltage",
    "fuel_flow",
    "power_output",
    "coolant_flow",
)
"""The eight observable telemetry measurements minus `efficiency` (see
module docstring). Order is part of the deterministic feature-column
order."""

EXCLUDED_MEASUREMENTS: tuple[str, ...] = ("efficiency",)

WINDOW_SECONDS: tuple[int, ...] = (30, 60, 120)
"""Trailing window lengths in seconds. Sample counts are `window // DT_SECONDS`
(3, 6, 12) given the pilot's fixed 10s cadence."""

LONGEST_WINDOW_SECONDS = max(WINDOW_SECONDS)
LONGEST_WINDOW_SAMPLES = int(LONGEST_WINDOW_SECONDS / DT_SECONDS)

WINDOW_STATS: tuple[str, ...] = ("mean", "std", "min", "max", "slope", "delta")
"""One canonical set of trailing-window statistics — see `windows.py` for
each one's exact definition. Deliberately not "every possible statistic":
mean/std/min/max/slope/delta are the high-value set the spec calls for."""
