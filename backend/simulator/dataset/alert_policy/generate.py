"""Writes every PR170 output artifact (spec section 9).

Output lifecycle mirrors `models/generate.py` and `calibration/
generate.py`: everything is written to a fresh temporary directory next
to the requested output directory, and only atomically renamed into
place once every file has been produced successfully.
`experiment.run_alert_policy_experiment` (pure computation) is fully
complete before any file is written here. No `.joblib` pipeline is
written — `alert_policy.json` references PR168's model instead of
duplicating it (spec section 9).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.simulator.dataset.alert_policy.experiment import (
    AlertPolicyExperimentResult,
    run_alert_policy_experiment,
)
from backend.simulator.dataset.alert_policy.plots import generate_plots
from backend.simulator.dataset.alert_policy.report import (
    build_alert_policy_artifact,
    build_alert_policy_search_json,
    render_alert_evaluation_report,
)
from backend.simulator.dataset.models.data import load_experiment_dataset


class AlertPolicyOutputExistsError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class AlertPolicyGenerationResult:
    output_directory: Path
    selected_entry_probability: float | None
    selected_entry_persistence: int | None
    selected_healthy_exit_probability: float | None
    selected_exit_persistence: int | None
    test_false_alert_events_per_healthy_hour: float | None
    test_correct_class_missed_run_count: int | None


def generate_alert_policy(
    features_dir: Path,
    output_directory: Path,
    *,
    dataset_directory: Path | None = None,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.alert_policy",
) -> AlertPolicyGenerationResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise AlertPolicyOutputExistsError(output_directory)

    dataset = load_experiment_dataset(features_dir, dataset_directory)
    result: AlertPolicyExperimentResult = run_alert_policy_experiment(dataset)

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

        alert_policy_artifact = build_alert_policy_artifact(result)
        (artifacts_dir / "alert_policy.json").write_text(
            json.dumps(alert_policy_artifact, indent=2, default=str)
        )

        plots = generate_plots(result, plots_dir, dataset)

        alert_policy_search = build_alert_policy_search_json(result)
        (tmp_dir / "alert_policy_search.json").write_text(
            json.dumps(alert_policy_search, indent=2, default=str)
        )

        report_markdown = render_alert_evaluation_report(
            result=result, plots=plots, generation_command=generation_command
        )
        (tmp_dir / "alert_evaluation_report.md").write_text(report_markdown)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    config = result.selected_config
    return AlertPolicyGenerationResult(
        output_directory=output_directory,
        selected_entry_probability=config.entry_probability if config else None,
        selected_entry_persistence=config.entry_persistence if config else None,
        selected_healthy_exit_probability=(
            config.healthy_exit_probability if config else None
        ),
        selected_exit_persistence=config.exit_persistence if config else None,
        test_false_alert_events_per_healthy_hour=(
            result.test_false_alerts.false_alert_events_per_healthy_hour
            if result.test_false_alerts
            else None
        ),
        test_correct_class_missed_run_count=(
            len(result.test_detection.correct_class_missed_runs)
            if result.test_detection
            else None
        ),
    )
