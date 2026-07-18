"""Run-plan determinism specifications."""

import collections
from dataclasses import replace
from pathlib import Path

from backend.simulator.dataset.generate import load_spec
from backend.simulator.dataset.run_plan import plan_runs

from .conftest import SpecFactory

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PILOT_SPEC_PATH = _REPO_ROOT / "examples" / "dataset_specs" / "pem_faults_pilot.json"


def test_run_ids_are_deterministic_from_the_spec(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    first = plan_runs(spec)
    second = plan_runs(spec)

    assert [run.simulation_run_id for run in first] == [
        run.simulation_run_id for run in second
    ]


def test_run_ids_encode_dataset_id_class_and_index(spec_factory: SpecFactory) -> None:
    spec = spec_factory(dataset_id="my-dataset")
    planned = plan_runs(spec)

    assert planned[0].simulation_run_id == "my-dataset-normal_operation-0000"
    assert planned[1].simulation_run_id == "my-dataset-normal_operation-0001"
    assert planned[2].simulation_run_id == "my-dataset-cooling_degradation-0000"
    assert planned[3].simulation_run_id == "my-dataset-cooling_degradation-0001"


def test_identical_spec_produces_identical_resolved_configs(
    spec_factory: SpecFactory
) -> None:
    spec = spec_factory()
    first = plan_runs(spec)
    second = plan_runs(spec)

    for a, b in zip(first, second, strict=True):
        assert a.run_config == b.run_config


def test_seeds_are_assigned_sequentially_across_scenario_plans(
    spec_factory: SpecFactory
) -> None:
    spec = spec_factory(seeds=(11, 12, 13, 14))
    planned = plan_runs(spec)

    assert [run.run_config.seed for run in planned] == [11, 12, 13, 14]


def test_target_assets_round_robin_within_each_scenario_plan(
    spec_factory: SpecFactory
) -> None:
    spec = spec_factory(
        target_asset_ids=("fuel-cell-stack-01", "fuel-cell-stack-02"),
    )
    planned = plan_runs(spec)

    # 2 normal_operation runs, then 2 cooling_degradation runs — each
    # scenario plan restarts the round-robin from index 0.
    assert [run.run_config.target_asset_id for run in planned] == [
        "fuel-cell-stack-01",
        "fuel-cell-stack-02",
        "fuel-cell-stack-01",
        "fuel-cell-stack-02",
    ]


def test_different_seeds_produce_different_resolved_operating_conditions(
    spec_factory: SpecFactory,
) -> None:
    spec_a = spec_factory(seeds=(1, 2, 3, 4))
    spec_b = spec_factory(seeds=(5, 6, 7, 8))

    planned_a = plan_runs(spec_a)
    planned_b = plan_runs(spec_b)

    load_baselines_a = [
        run.run_config.operating_conditions.load_baseline_percent for run in planned_a
    ]
    load_baselines_b = [
        run.run_config.operating_conditions.load_baseline_percent for run in planned_b
    ]
    assert load_baselines_a != load_baselines_b


def test_class_label_matches_scenario_name(spec_factory: SpecFactory) -> None:
    spec = spec_factory()
    planned = plan_runs(spec)

    assert planned[0].class_label == "normal_operation"
    assert planned[2].class_label == "cooling_degradation"


def test_plan_runs_raises_for_invalid_fault_window_before_any_output(
    spec_factory: SpecFactory,
) -> None:
    """Fault-window validation (RunConfig's own rules) surfaces during
    planning — before `generate_dataset` ever touches the filesystem.
    """
    from backend.simulator.dataset.dataset_spec import ScenarioRunSpec
    from backend.simulator.dataset.run_config import DatasetScenario

    bad_plan = ScenarioRunSpec(
        scenario_name=DatasetScenario.COOLING_DEGRADATION,
        run_count=1,
        fault_start_sim_seconds=290.0,
        fault_duration_sim_seconds=100.0,  # window extends past duration_sim_seconds
        fault_severity=1.0,
    )
    spec = spec_factory(scenario_plans=(bad_plan,), seeds=(1,))

    try:
        plan_runs(spec)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for an out-of-range fault window")


def test_plan_runs_does_not_depend_on_wall_clock_identity(
    spec_factory: SpecFactory
) -> None:
    """No `uuid4()`/`datetime.now()`-derived identity anywhere in planning —
    proven by re-planning the identical spec and getting identical run IDs
    and identical `run_start_time` on every resolved config.
    """
    spec = spec_factory()
    planned = plan_runs(spec)

    for run in planned:
        assert run.run_config.run_start_time == spec.run_start_time

    replanned = plan_runs(replace(spec))
    assert [r.simulation_run_id for r in planned] == [
        r.simulation_run_id for r in replanned
    ]


# --- Pilot spec (examples/dataset_specs/pem_faults_pilot.json) integrity ----


def test_pilot_spec_plans_all_64_runs_with_unique_ids() -> None:
    spec = load_spec(_PILOT_SPEC_PATH)
    planned = plan_runs(spec)

    assert len(planned) == 64
    run_ids = [run.simulation_run_id for run in planned]
    assert len(set(run_ids)) == 64  # no run-ID collisions across plans


def test_pilot_spec_has_16_runs_per_class() -> None:
    spec = load_spec(_PILOT_SPEC_PATH)
    planned = plan_runs(spec)

    counts = collections.Counter(run.class_label for run in planned)
    assert counts == {
        "normal_operation": 16,
        "cooling_degradation": 16,
        "hydrogen_supply_issue": 16,
        "sensor_anomaly": 16,
    }


def test_pilot_spec_gives_each_target_asset_exactly_4_runs_per_class() -> None:
    spec = load_spec(_PILOT_SPEC_PATH)
    planned = plan_runs(spec)

    per_class_asset_counts: dict[str, collections.Counter[str]] = (
        collections.defaultdict(collections.Counter)
    )
    for run in planned:
        per_class_asset_counts[run.class_label][run.run_config.target_asset_id] += 1

    for class_label, asset_counts in per_class_asset_counts.items():
        assert set(asset_counts) == {
            "fuel-cell-stack-01",
            "fuel-cell-stack-02",
            "fuel-cell-stack-03",
            "fuel-cell-stack-04",
        }, class_label
        assert all(count == 4 for count in asset_counts.values()), class_label


def test_pilot_spec_fault_starts_and_severities_vary_and_stay_in_range() -> None:
    spec = load_spec(_PILOT_SPEC_PATH)
    planned = plan_runs(spec)

    fault_runs = [run for run in planned if run.class_label != "normal_operation"]
    starts = [run.run_config.fault_start_sim_seconds for run in fault_runs]
    severities = [run.run_config.fault_severity for run in fault_runs]

    assert all(start is not None for start in starts)
    assert len(set(starts)) > 1
    assert all(90.0 <= start <= 420.0 for start in starts)  # type: ignore[operator]
    # discrete 10-second grid
    assert all((start - 90.0) % 10.0 == 0 for start in starts)  # type: ignore[operator]

    assert len(set(severities)) > 1
    assert all(0.15 <= severity <= 1.0 for severity in severities)


def test_pilot_spec_every_run_resolves_without_a_fault_window_violation() -> None:
    """Every one of the 64 runs plans successfully — i.e. every resolved
    fault window (whatever start the RNG drew) fits inside
    `duration_sim_seconds`, enforced by `RunConfig.__post_init__` on each
    resolved run.
    """
    spec = load_spec(_PILOT_SPEC_PATH)
    planned = plan_runs(spec)  # raises if any resolved run is invalid
    assert len(planned) == 64


def test_pilot_spec_is_deterministic_across_replans() -> None:
    spec = load_spec(_PILOT_SPEC_PATH)
    first = plan_runs(spec)
    second = plan_runs(spec)

    assert [r.simulation_run_id for r in first] == [r.simulation_run_id for r in second]
    for a, b in zip(first, second, strict=True):
        assert a.run_config == b.run_config
