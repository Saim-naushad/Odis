"""`dataset_manifest.json` construction.

Must only be called after every data file it hashes has already been
written — `generate.generate_dataset` enforces this ordering (data files,
then `splits.json`, then `data_dictionary.md`, then the manifest last).
"""

from __future__ import annotations

import hashlib
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.simulator.dataset.dataset_spec import DatasetSpec
from backend.simulator.dataset.export import RunExportResult
from backend.simulator.dataset.parquet_schema import SCHEMA_VERSION
from backend.simulator.dataset.splits import SplitAssignment

GENERATOR_VERSION = "odis-dataset-generator/1.0"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_git_commit() -> tuple[str | None, str]:
    """Best-effort `git rev-parse HEAD`.

    Never raises: an unavailable git binary, a non-repo working directory,
    or any subprocess failure all resolve to `(None, "unavailable")` rather
    than failing dataset generation.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, "unavailable"
    commit = result.stdout.strip()
    if result.returncode != 0 or not commit:
        return None, "unavailable"
    return commit, "resolved"


def _file_manifest_entries(files: tuple[Path, ...]) -> list[dict[str, Any]]:
    entries = []
    for path in files:
        entries.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return entries


def build_manifest(
    *,
    spec: DatasetSpec,
    run_results: tuple[RunExportResult, ...],
    split_assignment: SplitAssignment,
    files: tuple[Path, ...],
    generation_command: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the manifest dict (caller is responsible for `json.dump`).

    `files` must already exist on disk — every entry's size and hash is
    read directly from the filesystem, not assumed.
    """
    git_commit, git_status = resolve_git_commit()
    class_distribution = Counter(
        result.planned_run.class_label for result in run_results
    )
    durations = [
        result.planned_run.run_config.duration_sim_seconds for result in run_results
    ]

    return {
        "dataset_id": spec.dataset_id,
        "schema_version": SCHEMA_VERSION,
        "created_at": (created_at or datetime.now(UTC)).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "git_commit": git_commit,
        "git_commit_status": git_status,
        "simulator_version": spec.simulator_version,
        "dataset_spec": spec.to_json_dict(),
        "run_count": len(run_results),
        "row_counts": {
            "telemetry": sum(r.observation_count for r in run_results),
            "ground_truth": sum(r.ground_truth_row_count for r in run_results),
            "runs": len(run_results),
        },
        "class_distribution": dict(sorted(class_distribution.items())),
        "split_counts": {
            "train": len(split_assignment.train),
            "validation": len(split_assignment.validation),
            "test": len(split_assignment.test),
        },
        "sampling_interval_seconds": spec.dt_seconds,
        "simulated_duration_summary": {
            "min_seconds": min(durations) if durations else 0.0,
            "max_seconds": max(durations) if durations else 0.0,
            "total_seconds": sum(durations),
        },
        "files": _file_manifest_entries(files),
        "generation_command": generation_command,
        "reproducibility": {
            "semantic": (
                "Guaranteed: the same DatasetSpec (including its seed list) "
                "always produces the same run plan, resolved operating "
                "conditions, telemetry values, and ground-truth labels — "
                "see run_plan.plan_runs and runner.iter_samples."
            ),
            "byte_level": (
                "Not guaranteed: PyArrow/Parquet writer metadata (e.g. "
                "footer creation timestamps) and file-level compression "
                "details may differ between two generation runs even when "
                "every row is identical. Compare row content, not file "
                "hashes, to verify reproducibility of a re-generated "
                "dataset."
            ),
        },
    }
