"""Feature-set ablation groups (PR168 spec section 2).

Each group is a deterministic subset of `features.schema.feature_column_
order()`, derived from the same `DEFAULT_MEASUREMENTS` /
`CROSS_SIGNAL_FEATURES` / `RESIDUAL_SPECS` building blocks the feature
pipeline itself uses — never a hand-copied column-name list — so an
ablation group can never silently drift out of sync with what
`feature_manifest.json` actually contains.

- **A — current raw telemetry**: just the current value per measurement.
- **B — raw + temporal**: A plus first differences/rates and every
  trailing-window statistic.
- **C — + cross-signal**: B plus the two ratio features.
- **D — full feature set**: C plus the four physics-residual features.
  `group_d_columns()` must equal `feature_column_order()` exactly (tested).
"""

from __future__ import annotations

from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    WINDOW_SECONDS,
    WINDOW_STATS,
)
from backend.simulator.dataset.features.cross_signal import CROSS_SIGNAL_FEATURES
from backend.simulator.dataset.features.residuals import RESIDUAL_SPECS
from backend.simulator.dataset.features.schema import feature_column_order


def group_a_columns() -> list[str]:
    """Current raw telemetry only, one column per selected measurement."""
    return list(DEFAULT_MEASUREMENTS)


def group_b_columns() -> list[str]:
    """Group A plus first differences/rates and trailing-window statistics."""
    columns: list[str] = []
    for measurement in DEFAULT_MEASUREMENTS:
        columns.append(measurement)
        columns.append(f"{measurement}__diff_10s")
        columns.append(f"{measurement}__roc_per_s")
        for window_seconds in WINDOW_SECONDS:
            for stat in WINDOW_STATS:
                columns.append(f"{measurement}__{stat}_{window_seconds}s")
    return columns


def group_c_columns() -> list[str]:
    """Group B plus the cross-signal ratio features."""
    return group_b_columns() + list(CROSS_SIGNAL_FEATURES)


def group_d_columns() -> list[str]:
    """The full feature set: group C plus the physics-residual features."""
    return group_c_columns() + [spec.name for spec in RESIDUAL_SPECS]


FEATURE_GROUPS: dict[str, list[str]] = {
    "A": group_a_columns(),
    "B": group_b_columns(),
    "C": group_c_columns(),
    "D": group_d_columns(),
}

FEATURE_GROUP_DESCRIPTIONS: dict[str, str] = {
    "A": "current raw telemetry only",
    "B": "A + first differences/rates + trailing-window statistics",
    "C": "B + cross-signal ratio features",
    "D": "C + fixed-reference physics residuals (full feature set)",
}


def assert_group_d_matches_manifest_order() -> None:
    """`group_d_columns()` must equal `feature_column_order()` exactly.

    Enforced at import/use time (also directly tested) so a future change
    to either module's column order cannot silently desynchronize the
    "full feature set" ablation group from what `feature_manifest.json`
    actually documents.
    """
    expected = feature_column_order()
    actual = FEATURE_GROUPS["D"]
    if actual != expected:
        raise AssertionError(
            "group D column order does not match features.schema."
            f"feature_column_order(): {actual} != {expected}"
        )


assert_group_d_matches_manifest_order()
