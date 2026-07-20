"""Validates the four committed isolated-shift specifications (spec
section 13, "Specifications")."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend.simulator.dataset.generate import load_spec
from backend.simulator.dataset.run_plan import plan_runs

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SPEC_DIR = _REPO_ROOT / "examples" / "dataset_specs"
_PILOT_PATH = _SPEC_DIR / "pem_faults_pilot.json"
_OOD_V1_PATH = _SPEC_DIR / "pem_faults_ood_v1.json"

_ISOLATED_SPECS = {
    "high_load": _SPEC_DIR / "pem_faults_shift_high_load.json",
    "hot_start": _SPEC_DIR / "pem_faults_shift_hot_start.json",
    "late_onset": _SPEC_DIR / "pem_faults_shift_late_onset.json",
    "high_noise": _SPEC_DIR / "pem_faults_shift_high_noise.json",
}


def test_all_four_specs_load() -> None:
    for name, path in _ISOLATED_SPECS.items():
        spec = load_spec(path)
        assert spec.total_run_count == 64, name


def test_each_plans_64_runs() -> None:
    for name, path in _ISOLATED_SPECS.items():
        spec = load_spec(path)
        assert len(plan_runs(spec)) == 64, name


def test_class_and_asset_balance() -> None:
    for name, path in _ISOLATED_SPECS.items():
        spec = load_spec(path)
        planned = plan_runs(spec)
        class_counts = Counter(p.class_label for p in planned)
        assert class_counts == {
            "normal_operation": 16,
            "cooling_degradation": 16,
            "hydrogen_supply_issue": 16,
            "sensor_anomaly": 16,
        }, name
        asset_counts = Counter(p.run_config.target_asset_id for p in planned)
        assert set(asset_counts.values()) == {16}, name
        assert len(asset_counts) == 4, name


def test_seeds_fully_disjoint_across_pilot_ood_v1_and_all_isolated_specs() -> None:
    all_paths = {"pilot": _PILOT_PATH, "ood_v1": _OOD_V1_PATH, **_ISOLATED_SPECS}
    seed_sets = {
        name: set(json.loads(path.read_text())["seeds"])
        for name, path in all_paths.items()
    }
    names = list(seed_sets)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            overlap = seed_sets[names[i]] & seed_sets[names[j]]
            assert not overlap, f"{names[i]} and {names[j]} share seeds: {overlap}"


def test_fault_windows_fit_within_duration() -> None:
    for name, path in _ISOLATED_SPECS.items():
        spec = load_spec(path)
        for plan in spec.scenario_plans:
            if plan.fault_start_range is None:
                continue
            assert plan.fault_duration_sim_seconds is not None
            max_start = max(plan.fault_start_range.grid_values())
            assert (
                max_start + plan.fault_duration_sim_seconds
                <= spec.duration_sim_seconds
            ), name


def test_each_spec_changes_exactly_its_intended_dimension_from_pilot() -> None:
    pilot = load_spec(_PILOT_PATH)

    high_load = load_spec(_ISOLATED_SPECS["high_load"])
    assert high_load.operating_condition_ranges.load_baseline_percent != (
        pilot.operating_condition_ranges.load_baseline_percent
    )
    assert (
        high_load.operating_condition_ranges.initial_stack_temperature_offset_celsius
        == pilot.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )
    assert high_load.sensor_noise == pilot.sensor_noise
    assert _fault_start_ranges(high_load) == _fault_start_ranges(pilot)

    hot_start = load_spec(_ISOLATED_SPECS["hot_start"])
    assert (
        hot_start.operating_condition_ranges.initial_stack_temperature_offset_celsius
        != pilot.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )
    assert (
        hot_start.operating_condition_ranges.load_baseline_percent
        == pilot.operating_condition_ranges.load_baseline_percent
    )
    assert (
        hot_start.operating_condition_ranges.load_amplitude_percent
        == pilot.operating_condition_ranges.load_amplitude_percent
    )
    assert hot_start.sensor_noise == pilot.sensor_noise
    assert _fault_start_ranges(hot_start) == _fault_start_ranges(pilot)

    late_onset = load_spec(_ISOLATED_SPECS["late_onset"])
    assert _fault_start_ranges(late_onset) != _fault_start_ranges(pilot)
    assert (
        late_onset.operating_condition_ranges.load_baseline_percent
        == pilot.operating_condition_ranges.load_baseline_percent
    )
    assert (
        late_onset.operating_condition_ranges.initial_stack_temperature_offset_celsius
        == pilot.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )
    assert late_onset.sensor_noise == pilot.sensor_noise

    high_noise = load_spec(_ISOLATED_SPECS["high_noise"])
    assert high_noise.sensor_noise != pilot.sensor_noise
    for noise in high_noise.sensor_noise:
        pilot_noise = next(
            n
            for n in pilot.sensor_noise
            if n.measurement_name == noise.measurement_name
        )
        assert noise.standard_deviation > pilot_noise.standard_deviation
    assert (
        high_noise.operating_condition_ranges.load_baseline_percent
        == pilot.operating_condition_ranges.load_baseline_percent
    )
    assert (
        high_noise.operating_condition_ranges.initial_stack_temperature_offset_celsius
        == pilot.operating_condition_ranges.initial_stack_temperature_offset_celsius
    )
    assert _fault_start_ranges(high_noise) == _fault_start_ranges(pilot)


def _fault_start_ranges(spec) -> set:  # type: ignore[no-untyped-def]
    return {
        (plan.fault_start_range.minimum_seconds, plan.fault_start_range.maximum_seconds)
        for plan in spec.scenario_plans
        if plan.fault_start_range is not None
    }
