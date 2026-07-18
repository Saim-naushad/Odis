"""End-to-end dataset generation, CLI, and failure-handling specifications."""

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

import backend.simulator.dataset.generate as generate_module
from backend.simulator.dataset.dataset_spec import DatasetSpec
from backend.simulator.dataset.export import RunExportResult
from backend.simulator.dataset.generate import (
    DatasetGenerationError,
    DatasetOutputExistsError,
    generate_dataset,
    load_spec,
    main,
)
from backend.simulator.dataset.operating_conditions import SensorNoiseConfig
from backend.simulator.dataset.run_plan import PlannedRun

from .conftest import SpecFactory


def _noisy_spec(
    spec_factory: SpecFactory, tmp_path: Path, **overrides: Any
) -> DatasetSpec:
    overrides.setdefault(
        "sensor_noise",
        (SensorNoiseConfig(measurement_name="voltage", standard_deviation=0.005),),
    )
    overrides.setdefault("output_directory", str(tmp_path / "dataset-output"))
    return spec_factory(**overrides)


# --- Full successful generation ----------------------------------------------


def test_full_generation_produces_the_expected_file_set(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    result = generate_dataset(spec, generation_command="test")

    expected_files = {
        "telemetry.parquet",
        "ground_truth.parquet",
        "runs.parquet",
        "splits.json",
        "dataset_manifest.json",
        "data_dictionary.md",
    }
    assert {p.name for p in result.output_directory.iterdir()} == expected_files


def test_generation_result_counts_match_parquet_metadata(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    result = generate_dataset(spec, generation_command="test")

    telemetry = pq.read_table(result.output_directory / "telemetry.parquet")
    ground_truth = pq.read_table(result.output_directory / "ground_truth.parquet")
    runs = pq.read_table(result.output_directory / "runs.parquet")

    assert telemetry.num_rows == result.telemetry_row_count
    assert ground_truth.num_rows == result.ground_truth_row_count
    assert runs.num_rows == result.run_count == spec.total_run_count


def test_every_row_refers_to_a_known_run(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    result = generate_dataset(spec, generation_command="test")

    known_run_ids = set(
        pq.read_table(result.output_directory / "runs.parquet")
        .column("simulation_run_id")
        .to_pylist()
    )
    telemetry_run_ids = set(
        pq.read_table(result.output_directory / "telemetry.parquet")
        .column("simulation_run_id")
        .to_pylist()
    )
    ground_truth_run_ids = set(
        pq.read_table(result.output_directory / "ground_truth.parquet")
        .column("simulation_run_id")
        .to_pylist()
    )

    assert telemetry_run_ids <= known_run_ids
    assert ground_truth_run_ids <= known_run_ids
    assert telemetry_run_ids == known_run_ids  # every run contributed telemetry
    assert ground_truth_run_ids == known_run_ids


def test_splits_reference_only_known_runs(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    result = generate_dataset(spec, generation_command="test")

    known_run_ids = set(
        pq.read_table(result.output_directory / "runs.parquet")
        .column("simulation_run_id")
        .to_pylist()
    )
    splits = json.loads((result.output_directory / "splits.json").read_text())
    split_run_ids = (
        set(splits["train"]) | set(splits["validation"]) | set(splits["test"])
    )

    assert split_run_ids == known_run_ids


def test_manifest_hashes_match_the_written_files(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    import hashlib

    spec = _noisy_spec(spec_factory, tmp_path)
    result = generate_dataset(spec, generation_command="test")

    manifest_path = result.output_directory / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        path = result.output_directory / entry["name"]
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_hash == entry["sha256"]
        assert path.stat().st_size == entry["size_bytes"]


# --- Overwrite / safety -------------------------------------------------------


def test_existing_nonempty_output_is_rejected_without_overwrite(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    output = tmp_path / "dataset-output"
    output.mkdir()
    (output / "leftover.txt").write_text("pre-existing content")

    with pytest.raises(DatasetOutputExistsError):
        generate_dataset(spec, overwrite=False, generation_command="test")

    # the pre-existing content must be untouched
    assert (output / "leftover.txt").read_text() == "pre-existing content"


def test_overwrite_replaces_existing_output(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    output = tmp_path / "dataset-output"
    output.mkdir()
    (output / "leftover.txt").write_text("stale")

    result = generate_dataset(spec, overwrite=True, generation_command="test")

    assert not (result.output_directory / "leftover.txt").exists()
    assert (result.output_directory / "dataset_manifest.json").exists()


def test_empty_existing_directory_does_not_require_overwrite(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    output = tmp_path / "dataset-output"
    output.mkdir()  # exists but empty

    result = generate_dataset(spec, overwrite=False, generation_command="test")
    assert (result.output_directory / "dataset_manifest.json").exists()


# --- Failure handling ----------------------------------------------------------


def test_generation_failure_identifies_the_failed_run_and_leaves_no_output(
    tmp_path: Path, spec_factory: SpecFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    call_count = 0
    real_export_run = generate_module.export_run

    def _flaky_export_run(
        planned_run: PlannedRun, **kwargs: Any
    ) -> RunExportResult:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated export failure")
        return real_export_run(planned_run, **kwargs)

    monkeypatch.setattr(generate_module, "export_run", _flaky_export_run)

    with pytest.raises(DatasetGenerationError) as exc_info:
        generate_dataset(spec, generation_command="test")

    assert exc_info.value.run_id  # identifies which run failed
    output_dir = tmp_path / "dataset-output"
    assert not output_dir.exists()

    # no leftover temp directory in the parent
    leftovers = [
        p for p in tmp_path.iterdir() if p.name.startswith(".dataset-output.tmp-")
    ]
    assert leftovers == []


def test_rerunning_after_a_failure_succeeds(
    tmp_path: Path, spec_factory: SpecFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    call_count = 0
    real_export_run = generate_module.export_run

    def _fail_once(planned_run: PlannedRun, **kwargs: Any) -> RunExportResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated export failure")
        return real_export_run(planned_run, **kwargs)

    monkeypatch.setattr(generate_module, "export_run", _fail_once)
    with pytest.raises(DatasetGenerationError):
        generate_dataset(spec, generation_command="test")

    monkeypatch.setattr(generate_module, "export_run", real_export_run)
    result = generate_dataset(spec, generation_command="test")
    assert result.run_count == spec.total_run_count


# --- CLI -----------------------------------------------------------------------


def _write_spec_json(path: Path, spec: DatasetSpec) -> None:
    path.write_text(json.dumps(spec.to_json_dict()))


def test_cli_success_prints_summary_and_returns_zero(
    tmp_path: Path, spec_factory: SpecFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    spec_path = tmp_path / "spec.json"
    _write_spec_json(spec_path, spec)

    exit_code = main(["--spec", str(spec_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dataset written to" in out
    assert f"runs={spec.total_run_count}" in out


def test_cli_output_flag_overrides_spec_output_directory(
    tmp_path: Path, spec_factory: SpecFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _noisy_spec(
        spec_factory, tmp_path, output_directory=str(tmp_path / "unused")
    )
    spec_path = tmp_path / "spec.json"
    _write_spec_json(spec_path, spec)
    override_output = tmp_path / "explicit-output"

    exit_code = main(["--spec", str(spec_path), "--output", str(override_output)])

    assert exit_code == 0
    assert (override_output / "dataset_manifest.json").exists()
    assert not (tmp_path / "unused").exists()


def test_cli_rejects_invalid_spec_before_generation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = tmp_path / "bad_spec.json"
    spec_path.write_text(json.dumps({"dataset_id": "incomplete"}))

    exit_code = main(["--spec", str(spec_path)])

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "invalid dataset specification" in err
    assert not (tmp_path / "datasets").exists()


def test_cli_refuses_to_overwrite_without_the_flag(
    tmp_path: Path, spec_factory: SpecFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    spec_path = tmp_path / "spec.json"
    _write_spec_json(spec_path, spec)
    output = tmp_path / "dataset-output"
    output.mkdir()
    (output / "leftover.txt").write_text("stale")

    exit_code = main(["--spec", str(spec_path)])

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "already exists" in err


def test_cli_progress_is_printed_once_per_run_not_per_sample(
    tmp_path: Path, spec_factory: SpecFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    spec_path = tmp_path / "spec.json"
    _write_spec_json(spec_path, spec)

    main(["--spec", str(spec_path)])

    err_lines = [
        line for line in capsys.readouterr().err.splitlines() if line.startswith("[")
    ]
    assert len(err_lines) == spec.total_run_count


def test_load_spec_reads_a_valid_json_file(
    tmp_path: Path, spec_factory: SpecFactory
) -> None:
    spec = _noisy_spec(spec_factory, tmp_path)
    spec_path = tmp_path / "spec.json"
    _write_spec_json(spec_path, spec)

    loaded = load_spec(spec_path)
    assert loaded == spec
