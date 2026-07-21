"""Validates the PR174 broader-regime training specification
(`examples/dataset_specs/pem_faults_robust_training_v1.json`).

Mirrors `shift_study/test_shift_specs.py`'s spec-contract conventions, but
for the training-side spec rather than an isolated-shift evaluation cohort.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend.simulator.dataset.generate import load_spec
from backend.simulator.dataset.run_plan import plan_runs

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SPEC_DIR = _REPO_ROOT / "examples" / "dataset_specs"
_ROBUST_PATH = _SPEC_DIR / "pem_faults_robust_training_v1.json"

_OTHER_SPEC_PATHS = (
    "pem_faults_pilot.json",
    "pem_faults_ood_v1.json",
    "pem_faults_shift_high_load.json",
    "pem_faults_shift_hot_start.json",
    "pem_faults_shift_late_onset.json",
    "pem_faults_shift_high_noise.json",
)


def test_spec_loads_and_plans_192_runs() -> None:
    spec = load_spec(_ROBUST_PATH)
    assert spec.total_run_count == 192
    assert len(plan_runs(spec)) == 192


def test_class_and_asset_balance() -> None:
    spec = load_spec(_ROBUST_PATH)
    planned = plan_runs(spec)

    class_counts = Counter(p.class_label for p in planned)
    assert class_counts == {
        "normal_operation": 48,
        "cooling_degradation": 48,
        "hydrogen_supply_issue": 48,
        "sensor_anomaly": 48,
    }

    asset_counts = Counter(p.run_config.target_asset_id for p in planned)
    assert set(asset_counts.values()) == {48}
    assert len(asset_counts) == 4

    # Every (class, asset) stratum gets exactly 12 runs -- the PR174
    # rationale (12/stratum x 4 classes x 4 assets = 192).
    stratum_counts = Counter(
        (p.class_label, p.run_config.target_asset_id) for p in planned
    )
    assert set(stratum_counts.values()) == {12}
    assert len(stratum_counts) == 16


def test_seeds_are_disjoint_from_every_other_committed_spec() -> None:
    robust_seeds = set(json.loads(_ROBUST_PATH.read_text())["seeds"])
    assert len(robust_seeds) == 192  # no internal duplicates

    for name in _OTHER_SPEC_PATHS:
        other_seeds = set(json.loads((_SPEC_DIR / name).read_text())["seeds"])
        overlap = robust_seeds & other_seeds
        assert not overlap, f"robust training spec shares seeds with {name}: {overlap}"


def test_fault_windows_fit_within_duration() -> None:
    spec = load_spec(_ROBUST_PATH)
    for plan in spec.scenario_plans:
        if plan.fault_start_range is None:
            continue
        assert plan.fault_duration_sim_seconds is not None
        max_start = max(plan.fault_start_range.grid_values())
        assert max_start + plan.fault_duration_sim_seconds <= spec.duration_sim_seconds


def test_load_range_is_broader_than_pilot_but_not_the_high_load_cohort_alone() -> None:
    pilot = load_spec(_SPEC_DIR / "pem_faults_pilot.json")
    high_load = load_spec(_SPEC_DIR / "pem_faults_shift_high_load.json")
    robust = load_spec(_ROBUST_PATH)

    robust_range = robust.operating_condition_ranges.load_baseline_percent
    pilot_range = pilot.operating_condition_ranges.load_baseline_percent
    high_load_range = high_load.operating_condition_ranges.load_baseline_percent

    # Covers the original mid-load regime...
    assert robust_range[0] <= pilot_range[0]
    assert robust_range[1] >= pilot_range[0]
    # ...and some elevated-load operation overlapping the high-load cohort...
    assert robust_range[1] > pilot_range[1]
    assert robust_range[1] <= high_load_range[1]
    # ...but is not identical to the isolated high-load evaluation range.
    assert robust_range != high_load_range


def test_load_amplitude_stays_within_the_profile_constraint_across_the_range() -> None:
    """`OperatingConditions.__post_init__` requires baseline +/- amplitude to
    stay within [5, 95] for every resolved run -- verify the chosen
    amplitude range can never violate that at either end of the broadened
    baseline range, rather than relying on catching it at generation time.
    """
    spec = load_spec(_ROBUST_PATH)
    ranges = spec.operating_condition_ranges
    baseline_min, baseline_max = ranges.load_baseline_percent
    _amp_min, amp_max = ranges.load_amplitude_percent

    assert baseline_max + amp_max <= 95.0
    assert baseline_min - amp_max >= 5.0


def test_initial_temperature_offset_broadened_beyond_pilot_and_hot_start() -> None:
    pilot = load_spec(_SPEC_DIR / "pem_faults_pilot.json")
    hot_start = load_spec(_SPEC_DIR / "pem_faults_shift_hot_start.json")
    robust = load_spec(_ROBUST_PATH)

    robust_offset = (
        robust.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )
    pilot_offset = (
        pilot.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )
    hot_start_offset = (
        hot_start.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )

    assert robust_offset[0] < pilot_offset[0]  # colder than pilot's low end
    assert robust_offset[1] > pilot_offset[1]  # hotter than pilot's high end
    assert robust_offset != hot_start_offset  # not a copy of the isolated cohort


def test_fault_onset_range_spans_earlier_and_later_than_pilot() -> None:
    pilot = load_spec(_SPEC_DIR / "pem_faults_pilot.json")
    robust = load_spec(_ROBUST_PATH)

    pilot_plan = next(
        p for p in pilot.scenario_plans if p.fault_start_range is not None
    )
    robust_plan = next(
        p for p in robust.scenario_plans if p.fault_start_range is not None
    )

    robust_range = robust_plan.fault_start_range
    pilot_range = pilot_plan.fault_start_range
    assert robust_range is not None
    assert pilot_range is not None
    assert robust_range.minimum_seconds == pilot_range.minimum_seconds
    assert robust_range.maximum_seconds > pilot_range.maximum_seconds


def test_sensor_noise_uses_regimes_not_a_single_fixed_configuration() -> None:
    spec = load_spec(_ROBUST_PATH)
    assert spec.sensor_noise == ()
    assert len(spec.sensor_noise_regimes) == 3

    names = {regime.name for regime in spec.sensor_noise_regimes}
    assert names == {"nominal", "moderate", "high_bounded"}


def test_every_run_resolves_to_exactly_one_of_the_declared_noise_regimes() -> None:
    spec = load_spec(_ROBUST_PATH)
    planned = plan_runs(spec)

    regime_signatures = {
        regime.name: tuple(
            sorted(c.standard_deviation for c in regime.sensor_noise)
        )
        for regime in spec.sensor_noise_regimes
    }

    resolved_signatures = Counter(
        tuple(
            sorted(
                c.standard_deviation
                for c in p.run_config.operating_conditions.sensor_noise
            )
        )
        for p in planned
    )

    assert set(resolved_signatures) == set(regime_signatures.values())
    # Each regime should be represented with non-trivial coverage across 192
    # runs -- not one regime dominating and the others near-empty.
    for count in resolved_signatures.values():
        assert count >= 30
