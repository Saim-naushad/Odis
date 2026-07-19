"""Current-sample raw features (PR167 spec section 3 and section 4).

Three features per measurement at the current sample: the raw observed
value, the first difference from the immediately preceding sample, and
the rate of change per second (the first difference divided by
`config.DT_SECONDS`). The first difference requires exactly one prior
sample — already guaranteed by the longest-window warm-up drop (12 prior
samples are required, which is far more than the 1 this needs), so it
never needs its own separate availability check.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.simulator.dataset.features.config import DT_SECONDS


@dataclass(frozen=True)
class RawSampleFeatures:
    value: float
    diff: float
    rate_of_change_per_second: float


def compute_raw_features(
    current_value: float, previous_value: float
) -> RawSampleFeatures:
    diff = current_value - previous_value
    return RawSampleFeatures(
        value=current_value,
        diff=diff,
        rate_of_change_per_second=diff / DT_SECONDS,
    )
