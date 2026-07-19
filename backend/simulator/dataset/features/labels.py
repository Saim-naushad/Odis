"""Per-row label construction (PR167 spec section 8).

Labels are derived entirely from `ground_truth.parquet` at the same
`(simulation_run_id, asset_id, timestamp)` as each feature row — never
from `runs.parquet`'s `class_label` (the run's *configured* scenario).
This distinction is exactly what the PR166 audit's ground-truth checks
already guarantee holds for every row:

- a non-target asset in a fault run is always `fault_active=False` with
  `fault_type="none"`/`sensor_corruption_type="none"` (PR161's
  single-target-per-run design), so it maps to `"healthy"` here with no
  special-casing needed;
- pre-fault and post-fault samples on the target asset are
  `fault_active=False` (the fault window is `[start, end)`), so they also
  map to `"healthy"`;
- `fault_type`/`sensor_corruption_type` are mutually exclusive and exactly
  one is non-`"none"` whenever `fault_active` is `True` for the target
  asset (see `ground_truth.compute_ground_truth`).

Because of these existing invariants, `derive_label` is a direct,
un-special-cased read of three ground-truth fields — it never consults
`runs.parquet`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

HEALTHY_LABEL = "healthy"
PRIMARY_CLASSES: tuple[str, ...] = (
    HEALTHY_LABEL,
    "cooling_degradation",
    "hydrogen_supply_issue",
    "sensor_anomaly",
)

_SENSOR_CORRUPTION_TO_CLASS = {"bias": "sensor_anomaly"}


def derive_label(
    *, fault_active: bool, fault_type: str, sensor_corruption_type: str
) -> str:
    """The per-row multiclass target — see module docstring for why this
    never needs to know which asset is the run's configured target."""
    if not fault_active:
        return HEALTHY_LABEL
    if fault_type != "none":
        return fault_type
    return _SENSOR_CORRUPTION_TO_CLASS.get(sensor_corruption_type, HEALTHY_LABEL)


@dataclass(frozen=True)
class LabelRow:
    simulation_run_id: str
    asset_id: str
    timestamp: datetime
    split: str
    class_label: str
    is_anomalous: bool
    fault_severity: float | None
    """Evaluation-only: the instantaneous ground-truth severity for this
    row (0.0 or null when healthy — null exactly when inactive, matching
    `ground_truth.GroundTruthRecord`'s own convention). Never a model
    feature — see `feature_dictionary.md`."""


def _split_by_run_id(splits: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        for run_id in splits.get(split_name, []):
            result[run_id] = split_name
    return result


def build_label_rows(
    ground_truth_rows: list[dict[str, Any]], splits: dict[str, Any]
) -> list[LabelRow]:
    split_by_run_id = _split_by_run_id(splits)
    rows: list[LabelRow] = []
    for row in ground_truth_rows:
        label = derive_label(
            fault_active=row["fault_active"],
            fault_type=row["fault_type"],
            sensor_corruption_type=row["sensor_corruption_type"],
        )
        rows.append(
            LabelRow(
                simulation_run_id=row["simulation_run_id"],
                asset_id=row["asset_id"],
                timestamp=row["timestamp"],
                split=split_by_run_id[row["simulation_run_id"]],
                class_label=label,
                is_anomalous=label != HEALTHY_LABEL,
                fault_severity=(
                    row["fault_severity"] if row["fault_active"] else None
                ),
            )
        )
    return rows
