"""Run-level split assignment specifications."""

import collections
from pathlib import Path
from typing import Any

from backend.simulator.dataset.dataset_spec import (
    DatasetSpec,
    ScenarioRunSpec,
    SplitProportions,
)
from backend.simulator.dataset.generate import load_spec
from backend.simulator.dataset.run_config import DatasetScenario
from backend.simulator.dataset.run_plan import plan_runs
from backend.simulator.dataset.splits import assign_splits

from .conftest import SpecFactory

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PILOT_SPEC_PATH = _REPO_ROOT / "examples" / "dataset_specs" / "pem_faults_pilot.json"

_ASSETS = (
    "fuel-cell-stack-01",
    "fuel-cell-stack-02",
    "fuel-cell-stack-03",
)


def _bigger_spec(spec_factory: SpecFactory, **overrides: Any) -> DatasetSpec:
    plans = (
        ScenarioRunSpec(scenario_name=DatasetScenario.NORMAL_OPERATION, run_count=9),
        ScenarioRunSpec(
            scenario_name=DatasetScenario.COOLING_DEGRADATION,
            run_count=9,
            fault_start_sim_seconds=60.0,
            fault_duration_sim_seconds=120.0,
            fault_severity=1.0,
        ),
    )
    seeds = tuple(range(1, 19))
    overrides.setdefault(
        "split_proportions", SplitProportions(train=0.6, validation=0.2, test=0.2)
    )
    return spec_factory(
        scenario_plans=plans,
        seeds=seeds,
        target_asset_ids=_ASSETS,
        **overrides,
    )


def test_splits_are_pairwise_disjoint(spec_factory: SpecFactory) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    train_set = set(assignment.train)
    validation_set = set(assignment.validation)
    test_set = set(assignment.test)

    assert train_set.isdisjoint(validation_set)
    assert train_set.isdisjoint(test_set)
    assert validation_set.isdisjoint(test_set)


def test_split_union_equals_all_planned_runs(spec_factory: SpecFactory) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    all_ids = {run.simulation_run_id for run in planned_runs}
    union = set(assignment.train) | set(assignment.validation) | set(assignment.test)
    assert union == all_ids
    assert len(assignment.train) + len(assignment.validation) + len(
        assignment.test
    ) == len(planned_runs)


def test_class_stratification_is_preserved_when_counts_permit(
    spec_factory: SpecFactory
) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    class_by_run_id = {run.simulation_run_id: run.class_label for run in planned_runs}
    for split in (assignment.train, assignment.validation, assignment.test):
        classes_present = {class_by_run_id[run_id] for run_id in split}
        assert classes_present == {"normal_operation", "cooling_degradation"}


def test_split_assignment_is_deterministic(spec_factory: SpecFactory) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)

    first = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )
    second = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    assert first.train == second.train
    assert first.validation == second.validation
    assert first.test == second.test


def test_different_dataset_id_can_shuffle_differently(
    spec_factory: SpecFactory
) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)

    a = assign_splits(planned_runs, spec.split_proportions, dataset_id="dataset-a")
    b = assign_splits(planned_runs, spec.split_proportions, dataset_id="dataset-b")

    assert a.train != b.train or a.validation != b.validation


def test_zero_proportion_split_never_receives_a_run(spec_factory: SpecFactory) -> None:
    spec = _bigger_spec(
        spec_factory,
        split_proportions=SplitProportions(train=0.7, validation=0.3, test=0.0),
    )
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    assert assignment.test == ()


def test_target_asset_balance_is_preserved_across_splits(
    spec_factory: SpecFactory
) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    asset_by_run_id = {
        run.simulation_run_id: run.run_config.target_asset_id for run in planned_runs
    }
    for split in (assignment.train, assignment.validation, assignment.test):
        assets_present = {asset_by_run_id[run_id] for run_id in split}
        assert assets_present == set(_ASSETS)


def test_splits_json_round_trip_shape(spec_factory: SpecFactory) -> None:
    spec = _bigger_spec(spec_factory)
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    data = assignment.to_json_dict()
    assert set(data["train"]) == set(assignment.train)
    assert set(data["validation"]) == set(assignment.validation)
    assert set(data["test"]) == set(assignment.test)
    assert data["dataset_id"] == spec.dataset_id


# --- Pilot spec split coverage ------------------------------------------------


def test_pilot_spec_populates_every_split_for_every_class_asset_stratum() -> None:
    """4 runs per (class, target_asset) stratum at 0.6/0.2/0.2 resolves to
    exactly 2 train / 1 validation / 1 test per stratum (see
    `splits._split_counts`) — the pilot's whole reason for using 4 runs per
    stratum instead of the tiny dataset's 2 (which left validation/test
    empty).
    """
    spec = load_spec(_PILOT_SPEC_PATH)
    planned_runs = plan_runs(spec)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    assert len(assignment.train) == 32
    assert len(assignment.validation) == 16
    assert len(assignment.test) == 16

    class_by_run_id = {run.simulation_run_id: run.class_label for run in planned_runs}
    asset_by_run_id = {
        run.simulation_run_id: run.run_config.target_asset_id for run in planned_runs
    }
    expected_classes = {
        "normal_operation",
        "cooling_degradation",
        "hydrogen_supply_issue",
        "sensor_anomaly",
    }
    expected_assets = {
        "fuel-cell-stack-01",
        "fuel-cell-stack-02",
        "fuel-cell-stack-03",
        "fuel-cell-stack-04",
    }
    for split in (assignment.train, assignment.validation, assignment.test):
        assert {class_by_run_id[run_id] for run_id in split} == expected_classes
        assert {asset_by_run_id[run_id] for run_id in split} == expected_assets

    # Per-(class, asset) stratum: exactly 2/1/1.
    stratum_split_counts: dict[tuple[str, str], collections.Counter[str]] = (
        collections.defaultdict(collections.Counter)
    )
    for split_name, run_ids in (
        ("train", assignment.train),
        ("validation", assignment.validation),
        ("test", assignment.test),
    ):
        for run_id in run_ids:
            stratum = (class_by_run_id[run_id], asset_by_run_id[run_id])
            stratum_split_counts[stratum][split_name] += 1

    assert len(stratum_split_counts) == 16  # 4 classes x 4 assets
    for counts in stratum_split_counts.values():
        assert counts == {"train": 2, "validation": 1, "test": 1}
