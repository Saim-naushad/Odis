"""Central feature-exclusion policy (PR167 spec section 7).

One authoritative set, checked automatically at generation time (see
`builder.build_feature_table`'s call to `assert_no_forbidden_features`) —
never relying on caller discipline alone. Every field here either encodes
the label (directly or via null/non-null pattern — see the PR166 leakage
audit's "missingness pattern" finding), is run/observation bookkeeping, or
is evaluation-only metadata that happens to live in the same source
tables.

`timestamp`, `elapsed_sim_seconds`, and `asset_id` are deliberately *not*
in this set — they are legitimate feature-row metadata (join keys, and a
future PR may build temporal features directly from `elapsed_sim_seconds`)
but must never be copied into the *model* feature-column list. That
distinction is enforced structurally: `FeatureTable.metadata_columns` and
`FeatureTable.feature_columns` are always disjoint (see `builder.py`), so
this set only needs to guard the latter.
"""

from __future__ import annotations

FORBIDDEN_FEATURE_FIELDS: frozenset[str] = frozenset(
    {
        "dataset_id",
        "simulation_run_id",
        "observation_id",
        "class_label",
        "scenario_name",
        "seed",
        "run_start_time",
        "fault_start_sim_seconds",
        "fault_duration_sim_seconds",
        "fault_severity",
        "sensor_corruption_type",
        "fault_type",
        "fault_active",
        "seconds_since_fault_start",
        "target_asset_id",
        "split",
        "status",
        "error_message",
        "sensor_noise_json",
        "observation_count",
        "ground_truth_row_count",
        "sample_count",
        # Legitimate as feature-row metadata, forbidden as *model* features
        # (see module docstring) — listed here too so a caller that
        # accidentally merges metadata into the model matrix still trips
        # this assertion.
        "timestamp",
        "elapsed_sim_seconds",
        "asset_id",
    }
)


class ForbiddenFeatureError(Exception):
    """Raised when a forbidden field appears in a model-feature column list."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__(
            f"forbidden field(s) found in model-feature column list: {violations}"
        )
        self.violations = violations


def assert_no_forbidden_features(feature_columns: list[str]) -> None:
    """Raises `ForbiddenFeatureError` if any forbidden field is present.

    Called automatically by `builder.build_feature_table` — this is a
    runtime safety net, not merely a test assertion.
    """
    violations = sorted(FORBIDDEN_FEATURE_FIELDS & set(feature_columns))
    if violations:
        raise ForbiddenFeatureError(violations)
