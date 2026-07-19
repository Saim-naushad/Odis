"""Writes every PR168 output artifact (spec section 11).

Output lifecycle mirrors `features/generate.py`: everything is written to
a fresh temporary directory next to the requested output directory, and
only atomically renamed into place once every file has been produced
successfully. `experiment.run_experiment` (pure computation) and
`data.load_experiment_dataset` (pure loading) are both already fully
complete before any file is written here.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib

from backend.simulator.dataset.manifest import resolve_git_commit
from backend.simulator.dataset.models.config import MODEL_SCHEMA_VERSION, RANDOM_SEED
from backend.simulator.dataset.models.data import (
    ExperimentDataset,
    load_experiment_dataset,
)
from backend.simulator.dataset.models.experiment import ExperimentResult, run_experiment
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUPS
from backend.simulator.dataset.models.plots import generate_plots
from backend.simulator.dataset.models.report import (
    build_experiment_summary,
    build_test_metrics_json,
    build_validation_metrics_json,
    render_evaluation_report,
)
from backend.simulator.dataset.models.runtime_metrics import (
    RuntimeMetrics,
    artifact_size_bytes,
)


class ModelOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class ModelGenerationResult:
    output_directory: Path
    selected_model_type: str
    selected_feature_group: str
    validation_balanced_accuracy: float
    test_balanced_accuracy: float


def _build_model_metadata(dataset: ExperimentDataset, result: ExperimentResult) -> dict:
    git_commit, git_status = resolve_git_commit()
    selected = result.ablation.selected
    return {
        "model_schema_version": MODEL_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "git_commit_status": git_status,
        "random_seed": RANDOM_SEED,
        "model_type": selected.model_type,
        "feature_group": selected.feature_group,
        "feature_columns": list(FEATURE_GROUPS[selected.feature_group]),
        "hyperparameters": selected.hyperparameters,
        "persistence_samples": result.persistence_policy.selected_persistence_samples,
        "source_feature_schema_version": dataset.manifest.get("feature_schema_version"),
        "source_dataset_id": dataset.manifest["source_dataset"]["dataset_id"],
    }


def generate_models(
    features_dir: Path,
    output_directory: Path,
    *,
    dataset_directory: Path | None = None,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.models",
) -> ModelGenerationResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise ModelOutputExistsError(output_directory)

    dataset = load_experiment_dataset(features_dir, dataset_directory)
    result = run_experiment(dataset)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )

    try:
        metrics_dir = tmp_dir / "metrics"
        plots_dir = tmp_dir / "plots"
        artifacts_dir = tmp_dir / "artifacts"
        metrics_dir.mkdir(parents=True)
        artifacts_dir.mkdir(parents=True)

        pipeline_path = artifacts_dir / "selected_pipeline.joblib"
        joblib.dump(result.pipeline, pipeline_path)

        runtime = RuntimeMetrics(
            training_seconds=result.training_seconds,
            mean_prediction_latency_ms=result.mean_prediction_latency_ms,
            p95_prediction_latency_ms=result.p95_prediction_latency_ms,
            artifact_size_bytes=artifact_size_bytes(pipeline_path),
        )

        model_metadata = _build_model_metadata(dataset, result)
        (artifacts_dir / "model_metadata.json").write_text(
            json.dumps(model_metadata, indent=2, default=str)
        )

        plots = generate_plots(result, plots_dir)

        validation_metrics = build_validation_metrics_json(result)
        (metrics_dir / "validation_metrics.json").write_text(
            json.dumps(validation_metrics, indent=2, default=str)
        )
        test_metrics = build_test_metrics_json(result, runtime)
        (metrics_dir / "test_metrics.json").write_text(
            json.dumps(test_metrics, indent=2, default=str)
        )

        summary = build_experiment_summary(
            dataset=dataset,
            result=result,
            runtime=runtime,
            plots=plots,
            generation_command=generation_command,
        )
        (tmp_dir / "experiment_summary.json").write_text(
            json.dumps(summary, indent=2, default=str)
        )

        report_markdown = render_evaluation_report(
            dataset=dataset,
            result=result,
            runtime=runtime,
            plots=plots,
            generation_command=generation_command,
        )
        (tmp_dir / "evaluation_report.md").write_text(report_markdown)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    return ModelGenerationResult(
        output_directory=output_directory,
        selected_model_type=result.ablation.selected.model_type,
        selected_feature_group=result.ablation.selected.feature_group,
        validation_balanced_accuracy=result.validation_metrics.balanced_accuracy,
        test_balanced_accuracy=result.test_metrics.balanced_accuracy,
    )
