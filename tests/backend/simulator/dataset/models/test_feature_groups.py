"""Feature-set ablation group correctness (PR168 spec section 13,
"Feature ablation" test group)."""

from __future__ import annotations

from backend.simulator.dataset.features.config import DEFAULT_MEASUREMENTS
from backend.simulator.dataset.features.cross_signal import CROSS_SIGNAL_FEATURES
from backend.simulator.dataset.features.residuals import RESIDUAL_SPECS
from backend.simulator.dataset.features.schema import feature_column_order
from backend.simulator.dataset.models.feature_groups import (
    FEATURE_GROUPS,
    group_a_columns,
    group_b_columns,
    group_c_columns,
    group_d_columns,
)

_RESIDUAL_NAMES = {spec.name for spec in RESIDUAL_SPECS}


def test_group_a_is_exactly_current_raw_measurements() -> None:
    assert group_a_columns() == list(DEFAULT_MEASUREMENTS)
    assert len(group_a_columns()) == 7


def test_group_b_adds_only_temporal_columns() -> None:
    a, b = set(group_a_columns()), set(group_b_columns())
    assert a <= b
    added = b - a
    assert added, "group B must add something over group A"
    for column in added:
        assert column.startswith(tuple(DEFAULT_MEASUREMENTS))
        stats = ("mean", "std", "min", "max", "slope", "delta")
        assert (
            "__diff_10s" in column
            or "__roc_per_s" in column
            or any(f"__{stat}_" in column for stat in stats)
        )
    assert not (set(CROSS_SIGNAL_FEATURES) & b)
    assert not (_RESIDUAL_NAMES & b)


def test_group_c_adds_exactly_the_cross_signal_columns() -> None:
    assert set(group_c_columns()) - set(group_b_columns()) == set(CROSS_SIGNAL_FEATURES)


def test_group_d_adds_exactly_the_residual_columns() -> None:
    assert set(group_d_columns()) - set(group_c_columns()) == _RESIDUAL_NAMES


def test_group_d_full_feature_set_order_matches_manifest_order() -> None:
    """The full feature set (group D) must match
    `features.schema.feature_column_order()` column-for-column, in order —
    not just as a set — since `experiment.py` indexes `X` positionally."""
    assert FEATURE_GROUPS["D"] == feature_column_order() == group_d_columns()


def test_groups_are_strictly_nested_by_size() -> None:
    sizes = [len(FEATURE_GROUPS[name]) for name in "ABCD"]
    assert sizes == sorted(sizes)
    assert sizes[0] < sizes[1] < sizes[2] < sizes[3]
    assert sizes == [7, 147, 149, 153]


def test_group_columns_contain_no_duplicates() -> None:
    for name in "ABCD":
        columns = FEATURE_GROUPS[name]
        assert len(columns) == len(set(columns))
