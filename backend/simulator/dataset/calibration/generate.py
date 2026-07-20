"""Writes every PR169 output artifact (spec section 9).

Output lifecycle mirrors `models/generate.py`: everything is written to a
fresh temporary directory next to the requested output directory, and
only atomically renamed into place once every file has been produced
successfully. `experiment.run_calibration_experiment` (pure computation)
is fully complete before any file is written here.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import joblib

from backend.simulator.dataset.calibration.config import (
    MAX_MISSED_VALIDATION_FAULT_RUNS,
)
from backend.simulator.dataset.calibration.experiment import (
    CalibrationExperimentResult,
    run_calibration_experiment,
)
from backend.simulator.dataset.calibration.model_card import render_model_card
from backend.simulator.dataset.calibration.plots import generate_plots
from backend.simulator.dataset.calibration.report import (
    build_calibration_summary,
    build_decision_policy,
    build_policy_search_json,
    render_uncertainty_report,
)
from backend.simulator.dataset.models.data import load_experiment_dataset
from backend.simulator.dataset.models.runtime_metrics import artifact_size_bytes


class CalibrationOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class CalibrationGenerationResult:
    output_directory: Path
    selected_confidence_threshold: float
    selected_persistence_samples: int
    validation_missed_run_cap: int
    test_balanced_accuracy_covered: float
    test_coverage: float
    test_false_alarms_per_healthy_hour: float


def generate_calibration(
    features_dir: Path,
    output_directory: Path,
    *,
    dataset_directory: Path | None = None,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.calibration",
) -> CalibrationGenerationResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise CalibrationOutputExistsError(output_directory)

    dataset = load_experiment_dataset(features_dir, dataset_directory)
    result: CalibrationExperimentResult = run_calibration_experiment(dataset)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )

    try:
        artifacts_dir = tmp_dir / "artifacts"
        plots_dir = tmp_dir / "plots"
        artifacts_dir.mkdir(parents=True)

        pipeline_path = artifacts_dir / "calibrated_pipeline.joblib"
        joblib.dump(result.calibrated_model.calibrated_pipeline, pipeline_path)

        decision_policy = build_decision_policy(result)
        (artifacts_dir / "decision_policy.json").write_text(
            json.dumps(decision_policy, indent=2, default=str)
        )

        (artifacts_dir / "model_card.md").write_text(render_model_card(result))

        plots = generate_plots(result, plots_dir)

        calibration_summary = build_calibration_summary(
            result=result,
            training_seconds=result.training_seconds,
            artifact_size_bytes=artifact_size_bytes(pipeline_path),
            plots=plots,
            generation_command=generation_command,
        )
        (tmp_dir / "calibration_summary.json").write_text(
            json.dumps(calibration_summary, indent=2, default=str)
        )

        policy_search_json = build_policy_search_json(result)
        (tmp_dir / "policy_search.json").write_text(
            json.dumps(policy_search_json, indent=2, default=str)
        )

        uncertainty_report = render_uncertainty_report(
            result=result, generation_command=generation_command
        )
        (tmp_dir / "uncertainty_report.md").write_text(uncertainty_report)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    return CalibrationGenerationResult(
        output_directory=output_directory,
        selected_confidence_threshold=result.selected_confidence_threshold,
        selected_persistence_samples=result.selected_persistence_samples,
        validation_missed_run_cap=MAX_MISSED_VALIDATION_FAULT_RUNS,
        test_balanced_accuracy_covered=result.test_multiclass_metrics.balanced_accuracy,
        test_coverage=result.test_coverage.coverage,
        test_false_alarms_per_healthy_hour=result.test_alert_summary.false_alarms_per_healthy_hour,
    )
