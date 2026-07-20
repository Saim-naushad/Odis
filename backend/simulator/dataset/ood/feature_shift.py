"""Feature-distribution shift analysis, without fitting any new model
(spec section 10).

Two stable, well-documented descriptive measures per feature — no
Evidently, no drift-monitoring framework:

- **Standardized mean difference (SMD)**: `(mean_ood - mean_train) /
  pooled_std`, pooled as `sqrt((std_train**2 + std_ood**2) / 2)`. Zero for
  identical distributions, signed (direction of the shift), stable for a
  near-constant feature (falls back to the raw mean difference when
  pooled std is ~0, rather than dividing by zero).
- **Wasserstein distance** (`scipy.stats.wasserstein_distance`, already a
  transitive dependency via `scikit-learn`): a second, non-parametric
  cross-check that does not assume near-Gaussian shape.

The reference distribution is the pilot's own **training split** — the
only feature distribution `StandardScaler`/`LogisticRegression` actually
fit on — not the whole pilot dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.stats import wasserstein_distance

from backend.simulator.dataset.features.cross_signal import CROSS_SIGNAL_FEATURES
from backend.simulator.dataset.features.residuals import RESIDUAL_SPECS
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.feature_groups import group_a_columns
from backend.simulator.dataset.ood.config import TOP_SHIFTED_FEATURES_PER_GROUP

FeatureGroupName = Literal["raw", "temporal", "cross_signal", "residual"]

_RAW_COLUMNS = frozenset(group_a_columns())
_CROSS_SIGNAL_COLUMNS = frozenset(CROSS_SIGNAL_FEATURES)
_RESIDUAL_COLUMNS = frozenset(spec.name for spec in RESIDUAL_SPECS)


def _feature_group(name: str) -> FeatureGroupName:
    if name in _RESIDUAL_COLUMNS:
        return "residual"
    if name in _CROSS_SIGNAL_COLUMNS:
        return "cross_signal"
    if name in _RAW_COLUMNS:
        return "raw"
    return "temporal"


@dataclass(frozen=True)
class FeatureShiftEntry:
    name: str
    group: FeatureGroupName
    standardized_mean_difference: float
    wasserstein_distance: float
    train_mean: float
    train_std: float
    ood_mean: float
    ood_std: float
    train_min: float
    train_max: float
    ood_out_of_range_fraction: float
    """Fraction of OOD values strictly outside `[train_min, train_max]`."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "standardized_mean_difference": self.standardized_mean_difference,
            "wasserstein_distance": self.wasserstein_distance,
            "train_mean": self.train_mean,
            "train_std": self.train_std,
            "ood_mean": self.ood_mean,
            "ood_std": self.ood_std,
            "train_min": self.train_min,
            "train_max": self.train_max,
            "ood_out_of_range_fraction": self.ood_out_of_range_fraction,
        }


@dataclass(frozen=True)
class FeatureShiftReport:
    entries: dict[str, FeatureShiftEntry]

    def ranked(self, group: FeatureGroupName | None = None) -> list[FeatureShiftEntry]:
        """Descending by `|standardized_mean_difference|`, tie-broken by
        feature name — deterministic regardless of dict iteration order."""
        candidates = [
            e for e in self.entries.values() if group is None or e.group == group
        ]
        return sorted(
            candidates,
            key=lambda e: (-abs(e.standardized_mean_difference), e.name),
        )

    def to_json_dict(self) -> dict[str, Any]:
        top_by_group = {
            group: [
                e.to_json_dict()
                for e in self.ranked(group)[:TOP_SHIFTED_FEATURES_PER_GROUP]
            ]
            for group in ("raw", "temporal", "cross_signal", "residual")
        }
        out_of_range = sorted(
            (
                e.to_json_dict()
                for e in self.entries.values()
                if e.ood_out_of_range_fraction > 0.0
            ),
            key=lambda d: (-d["ood_out_of_range_fraction"], d["name"]),
        )
        return {
            "feature_count": len(self.entries),
            "top_shifted_by_group": top_by_group,
            "top_shifted_overall": [
                e.to_json_dict()
                for e in self.ranked()[:TOP_SHIFTED_FEATURES_PER_GROUP]
            ],
            "features_with_out_of_range_ood_values": out_of_range,
        }


def _entry_for_column(
    name: str, train_values: np.ndarray, ood_values: np.ndarray
) -> FeatureShiftEntry:
    train_mean = float(train_values.mean())
    train_std = float(train_values.std())
    ood_mean = float(ood_values.mean())
    ood_std = float(ood_values.std())
    pooled_std = float(np.sqrt((train_std**2 + ood_std**2) / 2.0))
    mean_diff = ood_mean - train_mean
    smd = mean_diff / pooled_std if pooled_std > 1e-9 else mean_diff
    train_min = float(train_values.min())
    train_max = float(train_values.max())
    out_of_range = (ood_values < train_min) | (ood_values > train_max)
    return FeatureShiftEntry(
        name=name,
        group=_feature_group(name),
        standardized_mean_difference=float(smd),
        wasserstein_distance=float(wasserstein_distance(train_values, ood_values)),
        train_mean=train_mean,
        train_std=train_std,
        ood_mean=ood_mean,
        ood_std=ood_std,
        train_min=train_min,
        train_max=train_max,
        ood_out_of_range_fraction=float(out_of_range.mean()),
    )


def compute_feature_shift(
    train_dataset: ExperimentDataset, ood_dataset: ExperimentDataset
) -> FeatureShiftReport:
    entries = {
        name: _entry_for_column(
            name, train_dataset.X[:, i], ood_dataset.X[:, i]
        )
        for i, name in enumerate(train_dataset.feature_columns)
    }
    return FeatureShiftReport(entries=entries)
