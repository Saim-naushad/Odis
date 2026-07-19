"""Feature-exclusion policy is enforced automatically, not just by
convention (PR167 spec sections 7 and 12)."""

from __future__ import annotations

import pytest

from backend.simulator.dataset.features.exclusions import (
    FORBIDDEN_FEATURE_FIELDS,
    ForbiddenFeatureError,
    assert_no_forbidden_features,
)
from backend.simulator.dataset.features.schema import feature_column_order


def test_default_feature_column_order_contains_no_forbidden_fields() -> None:
    columns = feature_column_order()
    assert FORBIDDEN_FEATURE_FIELDS.isdisjoint(columns)
    # assert_no_forbidden_features must not raise for the real column list.
    assert_no_forbidden_features(columns)


def test_assert_no_forbidden_features_raises_on_poisoned_list() -> None:
    poisoned = [*feature_column_order(), "fault_severity"]
    with pytest.raises(ForbiddenFeatureError) as exc_info:
        assert_no_forbidden_features(poisoned)
    assert "fault_severity" in exc_info.value.violations


def test_metadata_columns_are_forbidden_as_model_features() -> None:
    # timestamp/elapsed_sim_seconds/asset_id are legitimate feature-row
    # metadata but must never appear in a *model* feature column list.
    for column in ("timestamp", "elapsed_sim_seconds", "asset_id"):
        assert column in FORBIDDEN_FEATURE_FIELDS
