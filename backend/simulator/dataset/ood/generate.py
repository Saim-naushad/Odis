"""Top-level PR171 orchestration: load frozen artifacts, load the pilot's
own test split and the OOD v1 cohort, score both through the identical
metric code path, compare, and write every output artifact atomically
(mirrors `models/generate.py`'s temp-dir-then-rename pattern).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.ood.alert_metrics import evaluate_alert_policy
from backend.simulator.dataset.ood.artifacts import (
    load_frozen_artifacts,
)
from backend.simulator.dataset.ood.comparison import compare_id_vs_ood
from backend.simulator.dataset.ood.data_loading import (
    filter_experiment_dataset,
    load_ood_experiment_dataset,
)
from backend.simulator.dataset.ood.diagnosis_metrics import (
    evaluate_row_diagnosis,
    predict,
)
from backend.simulator.dataset.ood.error_analysis import select_representative_cases
from backend.simulator.dataset.ood.feature_shift import compute_feature_shift
from backend.simulator.dataset.ood.plots import generate_plots
from backend.simulator.dataset.ood.report import (
    build_summary_json,
    render_markdown_report,
)
from backend.simulator.dataset.ood.verdict import determine_ood_verdict


class OodOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class OodEvaluationResult:
    output_directory: Path
    verdict: str
    ood_balanced_accuracy: float
    ood_false_alert_events_per_healthy_hour: float


def run_ood_evaluation(
    *,
    training_features_dir: Path,
    ood_features_dir: Path,
    models_dir: Path,
    alert_policy_dir: Path,
    output_directory: Path,
    training_dataset_dir: Path | None = None,
    ood_dataset_dir: Path | None = None,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.ood",
) -> OodEvaluationResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise OodOutputExistsError(output_directory)

    artifacts = load_frozen_artifacts(models_dir, alert_policy_dir)

    id_dataset_full, id_unscoreable = load_ood_experiment_dataset(
        training_features_dir, training_dataset_dir
    )
    id_dataset = filter_experiment_dataset(
        id_dataset_full, id_dataset_full.split_mask("test")
    )
    ood_dataset, ood_unscoreable = load_ood_experiment_dataset(
        ood_features_dir, ood_dataset_dir
    )

    id_predictions = predict(id_dataset, artifacts.pipeline, artifacts.feature_group)
    ood_predictions = predict(ood_dataset, artifacts.pipeline, artifacts.feature_group)

    id_diagnosis = evaluate_row_diagnosis(
        id_dataset, id_predictions, fault_classes=FAULT_CLASSES
    )
    ood_diagnosis = evaluate_row_diagnosis(
        ood_dataset, ood_predictions, fault_classes=FAULT_CLASSES
    )

    id_alerts = evaluate_alert_policy(
        id_dataset,
        id_predictions.proba,
        artifacts.class_order,
        artifacts.state_machine_config,
    )
    ood_alerts = evaluate_alert_policy(
        ood_dataset,
        ood_predictions.proba,
        artifacts.class_order,
        artifacts.state_machine_config,
    )

    comparison = compare_id_vs_ood(
        id_diagnosis=id_diagnosis,
        ood_diagnosis=ood_diagnosis,
        id_alerts=id_alerts,
        ood_alerts=ood_alerts,
        fault_classes=FAULT_CLASSES,
    )
    verdict = determine_ood_verdict(
        ood_diagnosis=ood_diagnosis,
        ood_alerts=ood_alerts,
        comparison=comparison,
        fault_classes=FAULT_CLASSES,
    )

    train_split_mask = id_dataset_full.split_mask("train")
    train_dataset = filter_experiment_dataset(id_dataset_full, train_split_mask)
    feature_shift = compute_feature_shift(train_dataset, ood_dataset)

    representative_cases = select_representative_cases(
        ood_dataset, ood_predictions, ood_alerts, artifacts.state_machine_config
    )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )
    try:
        plots_dir = tmp_dir / "plots"
        plots = generate_plots(
            ood_diagnosis=ood_diagnosis,
            comparison=comparison,
            feature_shift=feature_shift,
            id_alerts=id_alerts,
            ood_alerts=ood_alerts,
            representative_cases=representative_cases,
            output_dir=plots_dir,
        )

        summary = build_summary_json(
            generation_command=generation_command,
            artifacts=artifacts,
            id_dataset_run_count=len(id_dataset.run_metadata),
            ood_dataset_run_count=len(ood_dataset.run_metadata),
            id_unscoreable=id_unscoreable,
            ood_unscoreable=ood_unscoreable,
            id_diagnosis=id_diagnosis,
            ood_diagnosis=ood_diagnosis,
            id_alerts=id_alerts,
            ood_alerts=ood_alerts,
            comparison=comparison,
            verdict=verdict,
        )
        (tmp_dir / "ood_evaluation_summary.json").write_text(
            json.dumps(summary, indent=2, default=str)
        )
        (tmp_dir / "feature_shift.json").write_text(
            json.dumps(feature_shift.to_json_dict(), indent=2, default=str)
        )
        (tmp_dir / "error_cases.json").write_text(
            json.dumps(
                [c.to_json_dict() for c in representative_cases],
                indent=2,
                default=str,
            )
        )

        report_markdown = render_markdown_report(
            generation_command=generation_command,
            artifacts=artifacts,
            ood_unscoreable=ood_unscoreable,
            id_diagnosis=id_diagnosis,
            ood_diagnosis=ood_diagnosis,
            id_alerts=id_alerts,
            ood_alerts=ood_alerts,
            comparison=comparison,
            verdict=verdict,
            representative_cases=representative_cases,
            plots=plots,
        )
        (tmp_dir / "ood_evaluation_report.md").write_text(report_markdown)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    return OodEvaluationResult(
        output_directory=output_directory,
        verdict=verdict.verdict,
        ood_balanced_accuracy=ood_diagnosis.multiclass_metrics.balanced_accuracy,
        ood_false_alert_events_per_healthy_hour=(
            ood_alerts.false_alerts.false_alert_events_per_healthy_hour
        ),
    )
