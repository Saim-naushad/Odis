"""Validates the committed OOD v1 specification (spec section 14,
"Specification").
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend.simulator.dataset.generate import load_spec
from backend.simulator.dataset.run_plan import plan_runs

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PILOT_SPEC_PATH = _REPO_ROOT / "examples" / "dataset_specs" / "pem_faults_pilot.json"
_OOD_SPEC_PATH = _REPO_ROOT / "examples" / "dataset_specs" / "pem_faults_ood_v1.json"


def test_ood_spec_loads() -> None:
    spec = load_spec(_OOD_SPEC_PATH)
    assert spec.dataset_id == "pem-faults-ood-v1"
    assert spec.total_run_count == 64


def test_all_64_runs_plan_successfully() -> None:
    spec = load_spec(_OOD_SPEC_PATH)
    planned = plan_runs(spec)
    assert len(planned) == 64


def test_seeds_are_disjoint_from_the_pilot() -> None:
    pilot_seeds = set(json.loads(_PILOT_SPEC_PATH.read_text())["seeds"])
    ood_seeds = set(json.loads(_OOD_SPEC_PATH.read_text())["seeds"])
    assert pilot_seeds & ood_seeds == set()
    assert len(ood_seeds) == 64


def test_all_four_classes_and_assets_are_balanced() -> None:
    spec = load_spec(_OOD_SPEC_PATH)
    planned = plan_runs(spec)

    class_counts = Counter(p.class_label for p in planned)
    assert class_counts == {
        "normal_operation": 16,
        "cooling_degradation": 16,
        "hydrogen_supply_issue": 16,
        "sensor_anomaly": 16,
    }

    asset_counts = Counter(p.run_config.target_asset_id for p in planned)
    assert set(asset_counts.values()) == {16}
    assert len(asset_counts) == 4

    # Each class independently round-robins evenly over the 4 assets.
    fault_classes = ("cooling_degradation", "hydrogen_supply_issue", "sensor_anomaly")
    for class_label in fault_classes:
        per_asset = Counter(
            p.run_config.target_asset_id
            for p in planned
            if p.class_label == class_label
        )
        assert set(per_asset.values()) == {4}


def test_later_fault_start_range_fits_within_duration() -> None:
    spec = load_spec(_OOD_SPEC_PATH)
    for plan in spec.scenario_plans:
        if plan.fault_start_range is None:
            continue
        assert plan.fault_duration_sim_seconds is not None
        max_start = max(plan.fault_start_range.grid_values())
        ramp_end = max_start + plan.fault_duration_sim_seconds
        assert ramp_end <= spec.duration_sim_seconds
        # The ramp completes with a nonzero post-ramp window left to evaluate.
        assert ramp_end < spec.duration_sim_seconds

    starts = spec.scenario_plans[1].fault_start_range
    assert starts is not None
    assert starts.minimum_seconds == 500.0
    assert starts.maximum_seconds == 600.0
    assert starts.step_seconds == 10.0
    # On the 10-second sampling grid.
    assert all(value % 10.0 == 0.0 for value in starts.grid_values())


def test_ood_noise_levels_are_higher_than_pilot() -> None:
    pilot_noise = {
        n["measurement_name"]: n["standard_deviation"]
        for n in json.loads(_PILOT_SPEC_PATH.read_text())["sensor_noise"]
    }
    ood_noise = {
        n["measurement_name"]: n["standard_deviation"]
        for n in json.loads(_OOD_SPEC_PATH.read_text())["sensor_noise"]
    }
    assert set(pilot_noise) == set(ood_noise)
    for name, pilot_std in pilot_noise.items():
        assert ood_noise[name] > pilot_std


def test_operating_ranges_are_shifted_from_pilot() -> None:
    pilot = load_spec(_PILOT_SPEC_PATH).operating_condition_ranges
    ood = load_spec(_OOD_SPEC_PATH).operating_condition_ranges

    assert ood.load_baseline_percent[0] > pilot.load_baseline_percent[0]
    assert ood.load_baseline_percent[1] > pilot.load_baseline_percent[1]
    assert (
        ood.initial_stack_temperature_offset_celsius[0]
        > pilot.initial_stack_temperature_offset_celsius[1]
    )


def test_ood_operating_condition_combinations_all_resolve_validly() -> None:
    """Every sampled `(load_baseline_percent, load_amplitude_percent)`
    combination must stay within the simulator's safety bounds — this is
    exactly what `plan_runs` exercises for all 64 runs already, but this
    test pins the extreme corners explicitly so a future edit that widens
    either range cannot silently reintroduce an invalid combination."""
    spec = load_spec(_OOD_SPEC_PATH)
    ranges = spec.operating_condition_ranges
    for baseline in ranges.load_baseline_percent:
        for amplitude in ranges.load_amplitude_percent:
            floor = baseline - amplitude
            ceiling = baseline + amplitude
            assert floor >= 5.0
            assert ceiling <= 95.0
