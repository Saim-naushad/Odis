"""Generate a versioned Parquet dataset from a `DatasetSpec`.

CLI usage::

    python -m backend.simulator.dataset.generate \\
        --spec examples/dataset_spec_tiny.json \\
        --output datasets/pem-faults-tiny \\
        [--overwrite]

Requires the `dataset` optional dependency group::

    pip install -e ".[dataset]"

Output lifecycle: everything is written to a fresh temporary directory next
to the requested output directory, and only atomically renamed into place
once every file (including `dataset_manifest.json`, written last) has been
produced successfully. A failure at any point leaves no new or
partially-written directory at the requested output path — the temporary
directory is removed and the error identifies which run failed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pyarrow.parquet as pq

from backend.simulator.dataset.dataset_spec import DatasetSpec
from backend.simulator.dataset.export import (
    RunExportResult,
    build_runs_table,
    export_run,
)
from backend.simulator.dataset.manifest import build_manifest
from backend.simulator.dataset.parquet_schema import (
    GROUND_TRUTH_SCHEMA,
    TELEMETRY_SCHEMA,
)
from backend.simulator.dataset.run_plan import PlannedRun, plan_runs
from backend.simulator.dataset.splits import assign_splits

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_DATA_DICTIONARY_TEMPLATE = _TEMPLATE_DIR / "data_dictionary.md"

ProgressCallback = Callable[[int, int, PlannedRun], None]


class DatasetOutputExistsError(Exception):
    """The requested output directory already exists and is non-empty."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


class DatasetGenerationError(Exception):
    """One planned run failed during export; generation was aborted."""

    def __init__(self, run_id: str, cause: Exception) -> None:
        super().__init__(f"dataset generation failed on run {run_id!r}: {cause}")
        self.run_id = run_id


@dataclass(frozen=True)
class GenerationResult:
    output_directory: Path
    run_count: int
    telemetry_row_count: int
    ground_truth_row_count: int
    split_counts: dict[str, int]


def load_spec(path: Path) -> DatasetSpec:
    """Load and validate a `DatasetSpec` from a JSON file.

    Validation (via `DatasetSpec.__post_init__`) happens here, before
    `generate_dataset` touches the filesystem at all.
    """
    data = json.loads(path.read_text())
    return DatasetSpec.from_json_dict(data)


def generate_dataset(
    spec: DatasetSpec,
    *,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
    generation_command: str = "backend.simulator.dataset.generate",
) -> GenerationResult:
    """Plan, export, split, and manifest one dataset.

    Memory: one run's rows are held at a time (see `export.export_run`);
    across runs, only small `RunExportResult` summaries accumulate, not row
    data — the dataset is never fully materialized in memory.
    """
    output_path = Path(spec.output_directory)
    if output_path.exists() and any(output_path.iterdir()) and not overwrite:
        raise DatasetOutputExistsError(output_path)

    # Planning resolves every RunConfig (and so validates every fault
    # window/severity combination) before any output file is touched.
    planned_runs = plan_runs(spec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    )

    try:
        telemetry_path = tmp_dir / "telemetry.parquet"
        ground_truth_path = tmp_dir / "ground_truth.parquet"
        runs_path = tmp_dir / "runs.parquet"

        run_results: list[RunExportResult] = []
        with (
            pq.ParquetWriter(telemetry_path, TELEMETRY_SCHEMA) as telemetry_writer,
            pq.ParquetWriter(
                ground_truth_path, GROUND_TRUTH_SCHEMA
            ) as ground_truth_writer,
        ):
            for index, planned_run in enumerate(planned_runs, start=1):
                try:
                    result = export_run(
                        planned_run,
                        telemetry_writer=telemetry_writer,
                        ground_truth_writer=ground_truth_writer,
                    )
                except Exception as exc:
                    raise DatasetGenerationError(
                        planned_run.simulation_run_id, exc
                    ) from exc
                run_results.append(result)
                if progress is not None:
                    progress(index, len(planned_runs), planned_run)

        runs_table = build_runs_table(tuple(run_results))
        pq.write_table(runs_table, runs_path)

        split_assignment = assign_splits(
            planned_runs, spec.split_proportions, dataset_id=spec.dataset_id
        )
        splits_path = tmp_dir / "splits.json"
        splits_path.write_text(json.dumps(split_assignment.to_json_dict(), indent=2))

        data_dictionary_path = tmp_dir / "data_dictionary.md"
        shutil.copyfile(_DATA_DICTIONARY_TEMPLATE, data_dictionary_path)

        manifest = build_manifest(
            spec=spec,
            run_results=tuple(run_results),
            split_assignment=split_assignment,
            files=(
                telemetry_path,
                ground_truth_path,
                runs_path,
                splits_path,
                data_dictionary_path,
            ),
            generation_command=generation_command,
        )
        manifest_path = tmp_dir / "dataset_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_path.exists():
        shutil.rmtree(output_path)
    tmp_dir.rename(output_path)

    return GenerationResult(
        output_directory=output_path,
        run_count=len(run_results),
        telemetry_row_count=sum(r.observation_count for r in run_results),
        ground_truth_row_count=sum(r.ground_truth_row_count for r in run_results),
        split_counts={
            "train": len(split_assignment.train),
            "validation": len(split_assignment.validation),
            "test": len(split_assignment.test),
        },
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Overrides the spec's output_directory",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"invalid dataset specification: {exc}", file=sys.stderr)
        return 1

    if args.output is not None:
        spec = replace(spec, output_directory=str(args.output))

    command = "python -m backend.simulator.dataset.generate " + " ".join(
        sys.argv[1:] if argv is None else argv
    )

    def _print_progress(index: int, total: int, planned_run: PlannedRun) -> None:
        print(
            f"[{index}/{total}] {planned_run.simulation_run_id} "
            f"({planned_run.class_label}) done",
            file=sys.stderr,
        )

    try:
        result = generate_dataset(
            spec,
            overwrite=args.overwrite,
            progress=_print_progress,
            generation_command=command,
        )
    except (DatasetOutputExistsError, DatasetGenerationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"invalid dataset specification: {exc}", file=sys.stderr)
        return 1

    print(f"dataset written to {result.output_directory}")
    print(
        f"runs={result.run_count} "
        f"telemetry_rows={result.telemetry_row_count} "
        f"ground_truth_rows={result.ground_truth_row_count} "
        f"splits(train/validation/test)="
        f"{result.split_counts['train']}/"
        f"{result.split_counts['validation']}/"
        f"{result.split_counts['test']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
