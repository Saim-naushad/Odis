"""dataset_manifest.json construction specifications."""

import hashlib
import subprocess
from pathlib import Path

import pytest

import backend.simulator.dataset.manifest as manifest_module
from backend.simulator.dataset.export import RunExportResult
from backend.simulator.dataset.manifest import build_manifest, resolve_git_commit
from backend.simulator.dataset.run_plan import PlannedRun, plan_runs
from backend.simulator.dataset.splits import assign_splits

from .conftest import SpecFactory

_REQUIRED_FIELDS = {
    "dataset_id",
    "schema_version",
    "created_at",
    "generator_version",
    "git_commit",
    "git_commit_status",
    "simulator_version",
    "dataset_spec",
    "run_count",
    "row_counts",
    "class_distribution",
    "split_counts",
    "sampling_interval_seconds",
    "simulated_duration_summary",
    "files",
    "generation_command",
    "reproducibility",
}


def _fake_results(
    planned_runs: tuple[PlannedRun, ...],
    *,
    observations: int = 10,
    ground_truth: int = 5,
    samples: int = 2,
) -> tuple[RunExportResult, ...]:
    return tuple(
        RunExportResult(
            planned_run=run,
            observation_count=observations,
            ground_truth_row_count=ground_truth,
            sample_count=samples,
        )
        for run in planned_runs
    )


def test_manifest_has_all_required_fields(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory()
    planned_runs = plan_runs(spec)
    results = _fake_results(planned_runs)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )
    dummy_file = tmp_path / "dummy.parquet"
    dummy_file.write_bytes(b"dummy-content")

    manifest = build_manifest(
        spec=spec,
        run_results=results,
        split_assignment=assignment,
        files=(dummy_file,),
        generation_command="test-command",
    )

    assert _REQUIRED_FIELDS.issubset(manifest.keys())


def test_manifest_file_hashes_and_sizes_match_disk(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory()
    planned_runs = plan_runs(spec)
    results = _fake_results(planned_runs)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )

    content = b"hello world, this is a fake parquet file for hashing"
    dummy_file = tmp_path / "telemetry.parquet"
    dummy_file.write_bytes(content)

    manifest = build_manifest(
        spec=spec,
        run_results=results,
        split_assignment=assignment,
        files=(dummy_file,),
        generation_command="test-command",
    )

    entry = manifest["files"][0]
    assert entry["name"] == "telemetry.parquet"
    assert entry["size_bytes"] == len(content)
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()


def test_manifest_row_counts_match_run_results(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory()
    planned_runs = plan_runs(spec)
    results = _fake_results(planned_runs, observations=10, ground_truth=5, samples=2)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )
    dummy_file = tmp_path / "dummy.parquet"
    dummy_file.write_bytes(b"x")

    manifest = build_manifest(
        spec=spec,
        run_results=results,
        split_assignment=assignment,
        files=(dummy_file,),
        generation_command="test-command",
    )

    assert manifest["row_counts"]["telemetry"] == 10 * len(planned_runs)
    assert manifest["row_counts"]["ground_truth"] == 5 * len(planned_runs)
    assert manifest["row_counts"]["runs"] == len(planned_runs)
    assert manifest["run_count"] == len(planned_runs)
    assert manifest["split_counts"]["train"] == len(assignment.train)
    assert manifest["split_counts"]["validation"] == len(assignment.validation)
    assert manifest["split_counts"]["test"] == len(assignment.test)


def test_manifest_class_distribution_matches_scenario_plans(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory()  # 2 normal_operation + 2 cooling_degradation
    planned_runs = plan_runs(spec)
    results = _fake_results(planned_runs)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )
    dummy_file = tmp_path / "dummy.parquet"
    dummy_file.write_bytes(b"x")

    manifest = build_manifest(
        spec=spec,
        run_results=results,
        split_assignment=assignment,
        files=(dummy_file,),
        generation_command="test-command",
    )

    assert manifest["class_distribution"] == {
        "cooling_degradation": 2,
        "normal_operation": 2,
    }


def test_resolve_git_commit_handles_a_missing_git_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _raise)

    commit, status = resolve_git_commit()

    assert commit is None
    assert status == "unavailable"


def test_resolve_git_commit_handles_a_non_repo_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailedResult:
        returncode = 128
        stdout = ""

    def _fake_run(*_args: object, **_kwargs: object) -> _FailedResult:
        return _FailedResult()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    commit, status = resolve_git_commit()

    assert commit is None
    assert status == "unavailable"


def test_build_manifest_succeeds_when_git_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spec_factory: SpecFactory
) -> None:
    monkeypatch.setattr(
        manifest_module, "resolve_git_commit", lambda: (None, "unavailable")
    )
    spec = spec_factory()
    planned_runs = plan_runs(spec)
    results = _fake_results(planned_runs)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )
    dummy_file = tmp_path / "dummy.parquet"
    dummy_file.write_bytes(b"x")

    manifest = build_manifest(
        spec=spec,
        run_results=results,
        split_assignment=assignment,
        files=(dummy_file,),
        generation_command="test-command",
    )

    assert manifest["git_commit"] is None
    assert manifest["git_commit_status"] == "unavailable"
    assert manifest["dataset_id"] == spec.dataset_id  # generation still succeeded


def test_reproducibility_section_distinguishes_semantic_from_byte_level(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = spec_factory()
    planned_runs = plan_runs(spec)
    results = _fake_results(planned_runs)
    assignment = assign_splits(
        planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
    )
    dummy_file = tmp_path / "dummy.parquet"
    dummy_file.write_bytes(b"x")

    manifest = build_manifest(
        spec=spec,
        run_results=results,
        split_assignment=assignment,
        files=(dummy_file,),
        generation_command="test-command",
    )

    assert "semantic" in manifest["reproducibility"]
    assert "byte_level" in manifest["reproducibility"]
    assert "guaranteed" in manifest["reproducibility"]["semantic"].lower()
    assert "not guaranteed" in manifest["reproducibility"]["byte_level"].lower()
